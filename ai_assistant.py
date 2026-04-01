import asyncio
import html
import inspect
import io
import re
import time
from urllib.parse import urlparse

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

PRIORITY_PROVIDER_BASE_URLS = [
    "https://share.wendabao.net",
    "https://chat4.free2gpt.com/",
    "https://free.oaibest.com/",
    "https://share.swt-ai.com/list",
    "https://link.fuckicoding.com/#/",
    "https://www.gptshunter.com/alternative-to-chatgpt-claude-poe",
    "https://app.textie.ai/app/chats/demo-chat",
    "https://chat.tinycms.xyz:3002",
    "https://chatnio.liujiarong.top/",
    "https://newpc.icoding.ink/?debug=true",
    "https://www.promptboom.com/",
]

FALLBACK_MODELS = ["gpt-4o-mini", ""]
PROVIDER_TIMEOUT_SECONDS = 15

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
    "received line: data:",
    '"conversation_id"',
    '"input_message"',
]

DOMAIN_RESPONSE_PATTERNS = {
    "free.oaibest.com": [
        r'"finalResponse"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        r'"answerText"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        r'"assistant_response"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
    ],
    "chat4.free2gpt.com": [
        r'"assistant"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        r'"reply"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
    ],
    "chatnio.liujiarong.top": [
        r'"completion"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        r'"generated"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
    ],
}


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

    def _extract_domain_specific_content(self, content: str, domain: str):
        patterns = []
        for known_domain, domain_patterns in DOMAIN_RESPONSE_PATTERNS.items():
            if known_domain in domain:
                patterns.extend(domain_patterns)

        if not patterns:
            return None

        candidates = []
        for pattern in patterns:
            for match in re.findall(pattern, content, flags=re.IGNORECASE):
                candidate = html.unescape(match.replace("\\n", "\n").replace("\\t", "\t")).strip()
                if len(candidate) >= 25:
                    candidates.append(candidate)

        if not candidates:
            return None

        return max(candidates, key=len)

    def _extract_text_from_html_payload(self, content: str, source_hint: str | None = None):
        if not content:
            return None

        lowered = content.lower()
        domain = ""
        if source_hint and "://" in source_hint:
            domain = urlparse(source_hint).netloc.lower()

        domain_specific = self._extract_domain_specific_content(content, domain)
        if domain_specific:
            return domain_specific

        json_candidates = []
        json_patterns = [
            r'"answer"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
            r'"content"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
            r'"message"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
            r'"output"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
            r'"text"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        ]
        for pattern in json_patterns:
            for match in re.findall(pattern, content, flags=re.IGNORECASE):
                candidate = html.unescape(match.replace("\\n", "\n").replace("\\t", "\t")).strip()
                if len(candidate) >= 25:
                    json_candidates.append(candidate)

        if json_candidates:
            return max(json_candidates, key=len)

        # Nettoyage HTML générique pour récupérer le texte visible.
        cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", content)
        cleaned = re.sub(r"(?is)<!--.*?-->", " ", cleaned)
        cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return None

        boilerplate_tokens = [
            "enable javascript",
            "privacy",
            "terms",
            "cookies",
            "sign in",
            "login",
            "register",
            "free.oaibest.com",
        ]

        if any(token in cleaned.lower() for token in boilerplate_tokens):
            # Pour certains fronts (ex: free.oaibest), le texte brut est souvent du boilerplate.
            if domain == "free.oaibest.com":
                return None

        if len(cleaned) >= 25:
            return cleaned

        return None

    def _normalize_provider_content(self, content: str, source_hint: str | None = None):
        if not content or not content.strip():
            return None

        stripped = content.strip()
        if not self._is_bad_provider_output(stripped):
            return stripped

        if "<" in stripped or "{" in stripped:
            extracted = self._extract_text_from_html_payload(stripped, source_hint=source_hint)
            if extracted and not self._is_bad_provider_output(extracted):
                return extracted.strip()

        return None

    async def _generate_ai_answer(self, prompt_text: str, on_answer_sent=None):
        try:
            import g4f.Provider as g4f_providers
            from g4f.client import AsyncClient as AIAsyncClient
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Dependance IA manquante: {exc}") from exc

        prepared_messages = [
            {
                "role": "user",
                "content": prompt_text,
            }
        ]

        def build_async_client(*, provider_obj=None, base_url=None):
            kwargs = {}
            try:
                params = inspect.signature(AIAsyncClient.__init__).parameters
            except (TypeError, ValueError):
                params = {}

            if provider_obj is not None and "provider" in params:
                kwargs["provider"] = provider_obj

            if base_url:
                for arg_name in ("base_url", "api_base", "api_endpoint"):
                    if arg_name in params:
                        kwargs[arg_name] = base_url
                        break

            return AIAsyncClient(**kwargs)

        async def request_completion(ai_client, model_name: str, timeout_seconds: float):
            create_fn = ai_client.chat.completions.create
            kwargs = {
                "model": model_name,
                "messages": prepared_messages,
            }

            # Certains providers exposent create en sync (bloquant), d'autres en async.
            if inspect.iscoroutinefunction(create_fn):
                return await asyncio.wait_for(
                    create_fn(**kwargs),
                    timeout=timeout_seconds,
                )

            return await asyncio.wait_for(
                asyncio.to_thread(create_fn, **kwargs),
                timeout=timeout_seconds,
            )

        last_error = None
        total_attempts = len(PRIORITY_PROVIDER_BASE_URLS) + len(NO_KEY_PROVIDERS) + 1
        attempt_index = 0

        for base_url in PRIORITY_PROVIDER_BASE_URLS:
            attempt_index += 1
            try:
                print(
                    f"[DEBUG][AI] Tentative {attempt_index}/{total_attempts} | "
                    f"endpoint prioritaire: {base_url}"
                )
                ai_client = build_async_client(base_url=base_url)
                attempt_deadline = time.monotonic() + PROVIDER_TIMEOUT_SECONDS
                for model_name in FALLBACK_MODELS:
                    remaining = attempt_deadline - time.monotonic()
                    if remaining <= 0:
                        raise asyncio.TimeoutError("Timeout provider atteint avant reponse")
                    response = await request_completion(ai_client, model_name, remaining)
                    content = response.choices[0].message.content
                    normalized = self._normalize_provider_content(content, source_hint=base_url)
                    if normalized:
                        if on_answer_sent is not None:
                            remaining = attempt_deadline - time.monotonic()
                            if remaining <= 0:
                                raise asyncio.TimeoutError("Timeout avant envoi Discord")
                            await asyncio.wait_for(on_answer_sent(normalized), timeout=remaining)
                        print(f"[DEBUG][AI] Endpoint prioritaire OK: {base_url} | model={model_name}")
                        return normalized
            except asyncio.TimeoutError:
                print(
                    f"[DEBUG][AI] Tentative {attempt_index}/{total_attempts} TIMEOUT "
                    f"apres {PROVIDER_TIMEOUT_SECONDS}s: {base_url}, passage au suivant"
                )
                last_error = asyncio.TimeoutError(f"Timeout sur {base_url}")
                continue
            except Exception as exc:
                print(
                    f"[DEBUG][AI] Tentative {attempt_index}/{total_attempts} KO: "
                    f"{base_url} -> {exc}"
                )
                last_error = exc
                continue

        for provider_name in NO_KEY_PROVIDERS:
            attempt_index += 1
            try:
                print(
                    f"[DEBUG][AI] Tentative {attempt_index}/{total_attempts} | "
                    f"provider: {provider_name}"
                )
                provider_obj = getattr(g4f_providers, provider_name, None)
                if provider_obj is None:
                    print(f"[DEBUG][AI] Provider inconnu dans g4f: {provider_name}")
                    continue
                ai_client = build_async_client(provider_obj=provider_obj)
                attempt_deadline = time.monotonic() + PROVIDER_TIMEOUT_SECONDS
                for model_name in FALLBACK_MODELS:
                    remaining = attempt_deadline - time.monotonic()
                    if remaining <= 0:
                        raise asyncio.TimeoutError("Timeout provider atteint avant reponse")
                    response = await request_completion(ai_client, model_name, remaining)
                    content = response.choices[0].message.content
                    normalized = self._normalize_provider_content(content, source_hint=provider_name)
                    if normalized:
                        if on_answer_sent is not None:
                            remaining = attempt_deadline - time.monotonic()
                            if remaining <= 0:
                                raise asyncio.TimeoutError("Timeout avant envoi Discord")
                            await asyncio.wait_for(on_answer_sent(normalized), timeout=remaining)
                        print(f"[DEBUG][AI] Provider OK: {provider_name} | model={model_name}")
                        return normalized
            except asyncio.TimeoutError:
                print(
                    f"[DEBUG][AI] Tentative {attempt_index}/{total_attempts} TIMEOUT "
                    f"apres {PROVIDER_TIMEOUT_SECONDS}s: {provider_name}, passage au suivant"
                )
                last_error = asyncio.TimeoutError(f"Timeout sur {provider_name}")
                continue
            except Exception as exc:
                print(
                    f"[DEBUG][AI] Tentative {attempt_index}/{total_attempts} KO: "
                    f"{provider_name} -> {exc}"
                )
                last_error = exc
                continue

        # Fallback final: laisser g4f choisir son provider automatiquement.
        attempt_index += 1
        try:
            print(
                f"[DEBUG][AI] Tentative {attempt_index}/{total_attempts} | "
                "provider automatique g4f"
            )
            ai_client = AIAsyncClient()
            attempt_deadline = time.monotonic() + PROVIDER_TIMEOUT_SECONDS
            for model_name in FALLBACK_MODELS:
                remaining = attempt_deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError("Timeout provider auto atteint avant reponse")
                response = await request_completion(ai_client, model_name, remaining)
                content = response.choices[0].message.content
                normalized = self._normalize_provider_content(content, source_hint="auto")
                if normalized:
                    if on_answer_sent is not None:
                        remaining = attempt_deadline - time.monotonic()
                        if remaining <= 0:
                            raise asyncio.TimeoutError("Timeout avant envoi Discord")
                        await asyncio.wait_for(on_answer_sent(normalized), timeout=remaining)
                    print(f"[DEBUG][AI] Provider auto OK | model={model_name}")
                    return normalized
        except asyncio.TimeoutError:
            print(
                f"[DEBUG][AI] Tentative {attempt_index}/{total_attempts} TIMEOUT "
                f"apres {PROVIDER_TIMEOUT_SECONDS}s"
            )
            last_error = asyncio.TimeoutError("Timeout provider auto")
        except Exception as exc:
            print(f"[DEBUG][AI] Tentative {attempt_index}/{total_attempts} KO -> {exc}")
            last_error = exc

        raise RuntimeError(f"Aucun provider g4f n'a fonctionne. Derniere erreur: {last_error}")

    def _is_bad_provider_output(self, content: str) -> bool:
        lowered = content.strip().lower()
        if not lowered:
            return True

        # Certains endpoints renvoient un flux SSE/JSON de debug au lieu de la reponse finale.
        if "received line: data:" in lowered:
            return True

        if '"conversation_id"' in lowered and '"author"' in lowered and '"recipient"' in lowered:
            return True

        if lowered.startswith("data: {"):
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
        fake_ctx = type("Ctx", (), {"send": message.channel.send})

        async def send_answer_callback(answer_text: str):
            await self._send_markdown_chunks(fake_ctx, answer_text)

        try:
            await self._generate_ai_answer(content, on_answer_sent=send_answer_callback)
        except Exception as exc:
            print(f"[DEBUG][MENTION] Erreur IA mention: {exc}")
            await message.channel.send(f"Je ne peux pas repondre pour le moment ({exc}).")
            return


def setup(bot):
    bot.add_cog(cmdai(bot))
