import asyncio
import io
import re

import discord
import nest_asyncio
import requests
from discord.ext import commands


NO_KEY_PROVIDERS = [
    "PollinationsAI",
    "OperaAria",
    "Perplexity",
    "Qwen",
    "WeWordle",
    "TeachAnything",
]

FALLBACK_MODELS = ["gpt-4o-mini", ""]
REQUEST_TIMEOUT_SECONDS = 18

BAD_OUTPUT_MARKERS = [
    "<!doctype html",
    "<html",
    "<head>",
    "<body",
    "astro-island",
    "free2gpt",
    "data: {\"type\":\"error\"",
    "authentication error",
    "no api key passed in",
    "api key",
    "errortext",
    "data: [done]",
    "403 forbidden",
    "provider not found",
    "error:",
]


class cmdai(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._easyocr_reader = None
        nest_asyncio.apply()

    def _get_easyocr_reader(self):
        try:
            import easyocr
        except ModuleNotFoundError:
            raise

        if self._easyocr_reader is None:
            self._easyocr_reader = easyocr.Reader(["fr"], gpu=False)
        return self._easyocr_reader

    def _extract_text_from_image(self, image_bytes: bytes):
        try:
            import numpy as np
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            reader = self._get_easyocr_reader()
            result = reader.readtext(np.array(img))
            return " ".join([item[1] for item in result])
        except ModuleNotFoundError as exc:
            missing = str(exc)
            return f"Dependance OCR manquante ({missing}). Installez: pip install easyocr torch torchvision"
        except Exception:
            return "Une erreur s'est produite lors de l'extraction du texte."

    def _improve_image_quality(self, image_source):
        try:
            import cv2
            import numpy as np
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Dependance image manquante: {exc}") from exc

        if isinstance(image_source, (bytes, bytearray)):
            raw_bytes = bytes(image_source)
        else:
            response = requests.get(image_source, timeout=30)
            response.raise_for_status()
            raw_bytes = response.content

        img = np.array(bytearray(raw_bytes), dtype=np.uint8)
        img = cv2.imdecode(img, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Format d'image invalide ou non supporte")
        img = cv2.bilateralFilter(img, 9, 75, 75)
        _, jpeg = cv2.imencode(".jpg", img)
        return jpeg.tobytes()

    async def _generate_ai_answer(self, prompt_text: str):
        try:
            import g4f.Provider as g4f_providers
            from g4f.client import AsyncClient as AIAsyncClient
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Dependance IA manquante: {exc}") from exc

        last_error = None
        for provider_name in NO_KEY_PROVIDERS:
            try:
                print(f"[DEBUG][AI] Tentative provider: {provider_name}")
                provider_obj = getattr(g4f_providers, provider_name, None)
                if provider_obj is None:
                    print(f"[DEBUG][AI] Provider inconnu dans g4f: {provider_name}")
                    continue
                ai_client = AIAsyncClient(provider=provider_obj)
                for model_name in FALLBACK_MODELS:
                    response = await asyncio.wait_for(
                        ai_client.chat.completions.create(
                            model=model_name,
                            messages=[
                                {
                                    "role": "user",
                                    "content": (
                                        "Repondez aux exercices ou questions qui suivent : "
                                        f"{prompt_text}"
                                    ),
                                }
                            ],
                        ),
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    )
                    content = response.choices[0].message.content
                    if content and content.strip():
                        if self._is_bad_provider_output(content):
                            raise RuntimeError("Sortie provider invalide (HTML/landing page)")
                        print(f"[DEBUG][AI] Provider OK: {provider_name} | model={model_name}")
                        return content
            except Exception as exc:
                print(f"[DEBUG][AI] Provider KO: {provider_name} -> {exc}")
                last_error = exc
                continue

        # Fallback final: laisser g4f choisir son provider automatiquement.
        try:
            print("[DEBUG][AI] Tentative provider automatique g4f")
            ai_client = AIAsyncClient()
            for model_name in FALLBACK_MODELS:
                response = await asyncio.wait_for(
                    ai_client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt_text}],
                    ),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                content = response.choices[0].message.content
                if content and content.strip():
                    if self._is_bad_provider_output(content):
                        raise RuntimeError("Sortie provider invalide (HTML/landing page)")
                    print(f"[DEBUG][AI] Provider auto OK | model={model_name}")
                    return content
        except Exception as exc:
            print(f"[DEBUG][AI] Provider auto KO -> {exc}")
            last_error = exc

        raise RuntimeError(f"Aucun provider g4f n'a fonctionne. Derniere erreur: {last_error}")

    def _is_bad_provider_output(self, content: str) -> bool:
        lowered = content.strip().lower()
        if not lowered:
            return True

        # Formats de flux renvoyant des erreurs textuelles au lieu d'une vraie reponse.
        if "data:" in lowered and ("error" in lowered or "api key" in lowered):
            return True

        if "authentication error" in lowered or "no api key passed in" in lowered:
            return True

        if "errortext" in lowered and "type" in lowered:
            return True

        # Provider introuvable ou acces refuse.
        if "provider not found" in lowered or "403 forbidden" in lowered:
            return True

        # Fin de flux SSE sans contenu reel.
        if "data: [done]" in lowered:
            return True

        marker_hits = sum(1 for marker in BAD_OUTPUT_MARKERS if marker in lowered)
        if marker_hits >= 2:
            return True

        # Rejet si le contenu commence par une balise HTML meme sans fermeture.
        if lowered.startswith("<html") or lowered.startswith("<!doctype"):
            return True

        return False

    async def _send_markdown_chunks(self, ctx, markdown_content: str):
        char_limit = 1900
        chunks = []
        start = 0
        while start < len(markdown_content):
            end = start + char_limit
            chunk = markdown_content[start:end]
            if end < len(markdown_content):
                last_newline = chunk.rfind("\n")
                if last_newline != -1:
                    chunk = chunk[: last_newline + 1]
            chunks.append(chunk)
            start += len(chunk)

        for chunk in chunks:
            embed = discord.Embed(description=f"\n{chunk}\n", color=0x00FF00)
            await ctx.send(embed=embed)

    @commands.command()
    async def devoir(self, ctx):
        print(f"[DEBUG][DEVOIR] Lance par {ctx.author}")
        await ctx.send("Veuillez envoyer une image ou un lien vers une image valide.")

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            message = await self.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Vous n'avez pas envoye d'image dans le delai imparti.")
            return

        if message.attachments:
            print("[DEBUG][DEVOIR] Piece jointe recue")
            image_source = await message.attachments[0].read()
        elif message.content:
            print("[DEBUG][DEVOIR] URL/lien recu")
            image_source = message.content.strip()
        else:
            await ctx.send("Veuillez envoyer une image ou un lien vers une image valide.")
            return

        loop = asyncio.get_running_loop()

        await ctx.send("Amelioration de l'image ...")
        try:
            improved_image_bytes = await loop.run_in_executor(
                None,
                self._improve_image_quality,
                image_source,
            )
        except Exception as exc:
            print(f"[DEBUG][DEVOIR] Erreur amelioration image: {exc}")
            await ctx.send(f"Une erreur s'est produite lors de l'amelioration de l'image: {exc}")
            return

        await ctx.send("Extraction du texte en cours ...")
        text = await loop.run_in_executor(None, self._extract_text_from_image, improved_image_bytes)
        print(f"[DEBUG][DEVOIR] Longueur texte OCR: {len(text) if text else 0}")
        if not text or text.strip() == "":
            await ctx.send("Aucun texte detecte dans l'image.")
            return

        await ctx.send("Generation de reponses en cours ...")
        try:
            markdown_content = await self._generate_ai_answer(text)
        except Exception as exc:
            print(f"[DEBUG][DEVOIR] Erreur IA: {exc}")
            await ctx.send(f"Erreur IA: {exc}")
            return

        await self._send_markdown_chunks(ctx, markdown_content)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        if self.bot.user is None:
            return

        if self.bot.user not in message.mentions:
            return

        print(f"[DEBUG][MENTION] Message mention recu de {message.author}: {message.content}")

        content = re.sub(rf"<@!?{self.bot.user.id}>", "", message.content).strip()
        if not content:
            await message.channel.send("Oui ? Ecris ta question apres ma mention.")
            return

        if content.startswith(","):
            return

        await message.channel.send("Je reflechis ...")
        try:
            answer = await self._generate_ai_answer(content)
        except Exception as exc:
            print(f"[DEBUG][MENTION] Erreur IA mention: {exc}")
            await message.channel.send(f"Je ne peux pas repondre pour le moment ({exc}).")
            return

        fake_ctx = type("Ctx", (), {"send": message.channel.send})
        await self._send_markdown_chunks(fake_ctx, answer)


def setup(bot):
    bot.add_cog(cmdai(bot))
