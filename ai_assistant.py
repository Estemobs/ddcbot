import asyncio
import io
import re

import discord
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
        except ModuleNotFoundError as exc:
            missing = str(exc)
            return f"Dependance OCR manquante ({missing}). Installez: pip install easyocr torch torchvision"
        except Exception:
            return "Une erreur s'est produite lors de l'extraction du texte."

    def _improve_image_quality(self, image_url: str):
        try:
            import cv2
            import numpy as np
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Dependance image manquante: {exc}") from exc

        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        img = np.array(bytearray(response.content), dtype=np.uint8)
        img = cv2.imdecode(img, cv2.IMREAD_COLOR)
        img = cv2.bilateralFilter(img, 9, 75, 75)
        _, jpeg = cv2.imencode(".jpg", img)
        return jpeg.tobytes()

    async def _generate_ai_answer(self, prompt_text: str):
        try:
            from g4f.client import AsyncClient as AIAsyncClient
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Dependance IA manquante: {exc}") from exc

        last_error = None
        for provider_name in NO_KEY_PROVIDERS:
            try:
                ai_client = AIAsyncClient(provider=provider_name)
                response = await ai_client.chat.completions.create(
                    model="",
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Repondez aux exercices ou questions qui suivent : "
                                f"{prompt_text}"
                            ),
                        }
                    ],
                )
                content = response.choices[0].message.content
                if content and content.strip():
                    return content
            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError(
            "Aucun provider g4f sans cle n'a fonctionne. "
            f"Derniere erreur: {last_error}"
        )

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
        await ctx.send("Veuillez envoyer une image ou un lien vers une image valide.")

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            message = await self.bot.wait_for("message", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Vous n'avez pas envoye d'image dans le delai imparti.")
            return

        if message.attachments:
            image_url = message.attachments[0].url
        elif message.content:
            image_url = message.content.strip()
        else:
            await ctx.send("Veuillez envoyer une image ou un lien vers une image valide.")
            return

        loop = asyncio.get_running_loop()

        await ctx.send("Amelioration de l'image ...")
        try:
            improved_image_bytes = await loop.run_in_executor(
                None,
                self._improve_image_quality,
                image_url,
            )
        except Exception:
            await ctx.send("Une erreur s'est produite lors de l'amelioration de l'image.")
            return

        await ctx.send("Extraction du texte en cours ...")
        text = await loop.run_in_executor(None, self._extract_text_from_image, improved_image_bytes)
        if not text or text.strip() == "":
            await ctx.send("Aucun texte detecte dans l'image.")
            return

        await ctx.send("Generation de reponses en cours ...")
        try:
            markdown_content = await self._generate_ai_answer(text)
        except Exception:
            await ctx.send("Erreur IA: aucun provider sans cle n'a repondu. Reessayez plus tard.")
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

        content = re.sub(rf"<@!?{self.bot.user.id}>", "", message.content).strip()
        if not content:
            await message.channel.send("Oui ? Ecris ta question apres ma mention.")
            return

        if content.startswith(","):
            return

        await message.channel.send("Je reflechis ...")
        try:
            answer = await self._generate_ai_answer(content)
        except Exception:
            await message.channel.send("Je ne peux pas repondre pour le moment. Reessaie dans quelques minutes.")
            return

        fake_ctx = type("Ctx", (), {"send": message.channel.send})
        await self._send_markdown_chunks(fake_ctx, answer)


def setup(bot):
    bot.add_cog(cmdai(bot))
