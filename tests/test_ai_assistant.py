"""Tests for ai_assistant fallback and output-filtering logic."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant import (
    BAD_OUTPUT_MARKERS,
    NO_KEY_PROVIDERS,
    PRIORITY_PROVIDER_BASE_URLS,
    PROVIDER_TIMEOUT_SECONDS,
    cmdai,
)


# ---------------------------------------------------------------------------
# _is_bad_provider_output
# ---------------------------------------------------------------------------


def make_cog():
    bot = MagicMock()
    return cmdai(bot)


@pytest.mark.parametrize(
    "content",
    [
        # HTML full page
        "<!doctype html><html><head></head><body>Hello</body></html>",
        "<html><body>page</body></html>",
        "<!doctype html something",
        # Only opening tag (no closing)
        "<html lang='fr'>some content without closing tag",
        # Stream error messages from the issue description
        'data: {"type":"error","errorText":"Authentication Error, No api key passed in."}',
        "data: [DONE]",
        "Authentication Error, No api key passed in.",
        # 403 / provider not found
        "403 Forbidden",
        "Provider not found",
        # SSE / metadata stream (provider parasite)
        'Received line: data: {"conversation_id":"abc","author":{"role":"user"},"recipient":"all"}',
        # Empty / whitespace
        "",
        "   ",
    ],
)
def test_is_bad_provider_output_rejects_invalid(content):
    cog = make_cog()
    assert cog._is_bad_provider_output(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "La reponse a ta question est 42.",
        "Voici un exemple de code Python :\n```python\nprint('hello')\n```",
        "La capitale de la France est Paris.",
        # Contains "error" but not in the bad patterns
        "Il n'y a pas d'erreur dans ce code.",
    ],
)
def test_is_bad_provider_output_accepts_valid(content):
    cog = make_cog()
    assert cog._is_bad_provider_output(content) is False


# ---------------------------------------------------------------------------
# NO_KEY_PROVIDERS list is the curated stable shortlist
# ---------------------------------------------------------------------------


def test_no_key_providers_is_stable_shortlist():
    expected = {"PollinationsAI", "OperaAria", "Perplexity", "Qwen", "WeWordle", "TeachAnything"}
    assert set(NO_KEY_PROVIDERS) == expected


def test_priority_provider_base_urls_order_is_curated():
    expected_first = [
        "https://share.wendabao.net",
                "https://chat4.free2gpt.com/",
                "https://free.oaibest.com/",
    ]
    assert PRIORITY_PROVIDER_BASE_URLS[:3] == expected_first
    assert len(PRIORITY_PROVIDER_BASE_URLS) == 11


def test_normalize_provider_content_extracts_useful_html_text():
        cog = make_cog()
        html_payload = """
        <html>
            <head><title>Test</title></head>
            <body>
                <div id=\"app\">Reponse detaillee: pour installer GLPI, commence par Debian + MariaDB + PHP.</div>
            </body>
        </html>
        """
        normalized = cog._normalize_provider_content(
                html_payload,
                source_hint="https://example.com",
        )
        assert normalized is not None
        assert "installer GLPI" in normalized


def test_normalize_provider_content_uses_domain_specific_pattern():
        cog = make_cog()
        html_payload = """
        <html>
            <body>
                <script>
                    window.__APP_STATE__ = {"finalResponse":"Procedure GLPI: installer Apache, MariaDB, PHP puis configurer le virtualhost."};
                </script>
            </body>
        </html>
        """
        normalized = cog._normalize_provider_content(
                html_payload,
                source_hint="https://free.oaibest.com/",
        )
        assert normalized is not None
        assert "Procedure GLPI" in normalized


def test_timeout_constants_are_reasonable():
    """Verify each provider gets 15 seconds max. If timeout, continue to next provider."""
    assert PROVIDER_TIMEOUT_SECONDS == 15


# ---------------------------------------------------------------------------
# _generate_ai_answer skips providers not found in g4f.Provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_ai_answer_skips_unknown_providers():
    """When no g4f provider object can be resolved, all providers are skipped
    and a RuntimeError is raised at the end."""
    import sys
    import types

    cog = make_cog()

    # Build minimal fake g4f modules so the import inside _generate_ai_answer works.
    fake_g4f = types.ModuleType("g4f")
    fake_provider_mod = types.ModuleType("g4f.Provider")
    # No provider attributes – getattr will return None via our override below.

    fake_client_mod = types.ModuleType("g4f.client")

    class FakeAsyncClient:
        class _completions:
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("provider auto KO")

        class _chat:
            completions = None

        def __init__(self, provider=None):
            self.chat = self._chat()
            self.chat.completions = self._completions()

    fake_client_mod.AsyncClient = FakeAsyncClient
    fake_g4f.client = fake_client_mod
    fake_g4f.Provider = fake_provider_mod

    saved = {k: sys.modules.get(k) for k in ("g4f", "g4f.Provider", "g4f.client")}
    sys.modules["g4f"] = fake_g4f
    sys.modules["g4f.Provider"] = fake_provider_mod
    sys.modules["g4f.client"] = fake_client_mod

    try:
        with pytest.raises(RuntimeError):
            await cog._generate_ai_answer("test")
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


@pytest.mark.asyncio
async def test_generate_ai_answer_returns_first_valid_response():
    """When a provider returns a valid answer it is returned immediately."""
    import sys
    import types

    cog = make_cog()

    fake_g4f = types.ModuleType("g4f")
    fake_provider_mod = types.ModuleType("g4f.Provider")
    # Make getattr on the module return a sentinel object for any name.
    sentinel_provider = object()
    fake_provider_mod.PollinationsAI = sentinel_provider

    fake_response = MagicMock()
    fake_response.choices[0].message.content = "Voici la reponse correcte."

    class FakeAsyncClient:
        class _completions:
            _response = None

            async def create(self, **kwargs):
                return FakeAsyncClient._completions._response

        class _chat:
            completions = None

        def __init__(self, provider=None):
            FakeAsyncClient._completions._response = fake_response
            self.chat = self._chat()
            self.chat.completions = self._completions()

    fake_client_mod = types.ModuleType("g4f.client")
    fake_client_mod.AsyncClient = FakeAsyncClient
    fake_g4f.client = fake_client_mod
    fake_g4f.Provider = fake_provider_mod

    saved = {k: sys.modules.get(k) for k in ("g4f", "g4f.Provider", "g4f.client")}
    sys.modules["g4f"] = fake_g4f
    sys.modules["g4f.Provider"] = fake_provider_mod
    sys.modules["g4f.client"] = fake_client_mod

    try:
        with patch("ai_assistant.NO_KEY_PROVIDERS", ["PollinationsAI"]):
            result = await cog._generate_ai_answer("une question")
        assert result == "Voici la reponse correcte."
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


# ---------------------------------------------------------------------------
# BAD_OUTPUT_MARKERS includes the new patterns from the issue
# ---------------------------------------------------------------------------


def test_bad_output_markers_includes_403_and_provider_not_found():
    lowered = [m.lower() for m in BAD_OUTPUT_MARKERS]
    assert "403 forbidden" in lowered
    assert "provider not found" in lowered
