import asyncio
import html
import io
import re
import time

import discord
import nest_asyncio
import requests
from discord.ext import commands

nest_asyncio.apply()

PROVIDER_TIMEOUT = 20
#last file edit: 2024-06-17

class cmdai(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._easyocr_reader = None

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
        except ModuleNotFoundError:
            return "OCR manquant: pip install easyocr torch torchvision"
        except Exception:
            return "Erreur extraction texte."

    def _improve_image_quality(self, image_source):
        try:
            import cv2
            import numpy as np
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"CV2 manquant: {exc}") from exc

        if isinstance(image_source, (bytes, bytearray)):
            raw_bytes = bytes(image_source)
        else:
            response = requests.get(image_source, timeout=30)
            response.raise_for_status()
            raw_bytes = response.content

        img = np.array(bytearray(raw_bytes), dtype=np.uint8)
        img = cv2.imdecode(img, cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("Image invalide")
        img = cv2.bilateralFilter(img, 9, 75, 75)
        _, jpeg = cv2.imencode(".jpg", img)
        return jpeg.tobytes()

    def _extract_useful_content(self, content: str) -> str | None:
        """Extrait le contenu utile d'une réponse."""
        if not content or not content.strip():
            return None

        lowered = content.lower()

        # Rejet des erreurs évidentes
        if any(
            x in lowered
            for x in [
                "error",
                "<!doctype",
                "<html",
                "api key",
                "403",
                "authentication",
                "[done]",
                "no .har",
            ]
        ):
            return None

        # Nettoie le texte
        text = content.strip()

        # Enlève le HTML si présent
        if "<" in text:
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

        return text if len(text) > 20 else None

    async def _generate_ai_answer(self, prompt_text: str, on_answer_sent=None):
        try:
            from g4f.client import AsyncClient
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"g4f manquant: {exc}") from exc

        messages = [{"role": "user", "content": prompt_text}]

        # Providers sans clé API qui marchent bien
        models_and_providers = [
            ("gpt-4", None),  # Auto-select
            ("gpt-3.5-turbo", None),
            ("text-davinci-003", None),
            ("llama-2-7b", None),
        ]

        for model_name, provider in models_and_providers:
            try:
                print(f"[AI] Tentative avec {model_name}...")
                client = AsyncClient(timeout=PROVIDER_TIMEOUT)

                kwargs = {
                    "model": model_name,
                    "messages": messages,
                }

                response = await asyncio.wait_for(
                    client.chat.completions.create(**kwargs),
                    timeout=PROVIDER_TIMEOUT,
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    extracted = self._extract_useful_content(content)

                    if extracted:
                        print(f"[AI] ✓ {model_name} OK!")
                        if on_answer_sent:
                            await on_answer_sent(extracted)
                        return extracted

            except asyncio.TimeoutError:
                print(f"[AI] ⏱️ Timeout {model_name}")
                continue
            except Exception as exc:
                print(f"[AI] ✗ {model_name}: {str(exc)[:80]}")
                continue

        raise RuntimeError("Aucun provider gratuit n'a fonctionné. Réessaye plus tard.")

    async def _send_markdown_chunks(self, ctx, content: str):
        """Envoie le contenu par chunks de 1900 chars."""
        char_limit = 1900
        for i in range(0, len(content), char_limit):
            chunk = content[i : i + char_limit]
            embed = discord.Embed(description=f"\n{chunk}\n", color=0x00FF00)
            await ctx.send(embed=embed)

    @commands.command()
    async def devoir(self, ctx):
        """Résout un devoir à partir d'une image."""
        print(f"[DEVOIR] Lancé par {ctx.author}")
        await ctx.send("Envoie une image ou un lien valide.")

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel

        try:
            message = await self.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Timeout - aucune image envoyée.")
            return

        if message.attachments:
            image_source = await message.attachments[0].read()
        elif message.content:
            image_source = message.content.strip()
        else:
            await ctx.send("Image ou lien invalide.")
            return

        loop = asyncio.get_running_loop()

        # Amélioration image
        await ctx.send("Amélioration image...")
        try:
            improved_bytes = await loop.run_in_executor(
                None,
                self._improve_image_quality,
                image_source,
            )
        except Exception as exc:
            await ctx.send(f"Erreur image: {exc}")
            return

        # OCR
        await ctx.send("Extraction texte...")
        text = await loop.run_in_executor(
            None, self._extract_text_from_image, improved_bytes
        )
        if not text or len(text.strip()) < 10:
            await ctx.send("Aucun texte détecté.")
            return

        # IA
        await ctx.send("Génération réponse...")
        try:
            answer = await self._generate_ai_answer(text)
            await self._send_markdown_chunks(ctx, answer)
        except Exception as exc:
            await ctx.send(f"Erreur IA: {exc}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Répond aux mentions."""
        if (
            message.author.bot
            or not message.guild
            or self.bot.user is None
        ):
            return

        if self.bot.user not in message.mentions:
            return

        content = re.sub(rf"<@!?{self.bot.user.id}>", "", message.content).strip()
        if not content or content.startswith(","):
            return

        await message.channel.send("Je réfléchis...")

        async def send_answer(text: str):
            await self._send_markdown_chunks(message.channel, text)

        try:
            await self._generate_ai_answer(content, on_answer_sent=send_answer)
        except Exception as exc:
            await message.channel.send(f"Erreur: {exc}")


def setup(bot):
    bot.add_cog(cmdai(bot))
