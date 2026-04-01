from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from Notifrss import cmdrss
from animations import cmdanim
from moderation import cmdmoderation
from utility import cmdutility


class DummyCtx:
    def __init__(self):
        self.send = AsyncMock()
        self.author = SimpleNamespace(id=1, mention="@u", name="u")
        self.channel = SimpleNamespace()
        self.guild = SimpleNamespace(
            id=123,
            default_role=SimpleNamespace(),
            get_role=lambda _id: None,
        )


@pytest.mark.asyncio
async def test_gend_no_participant_does_not_crash():
    bot = AsyncMock()
    cog = cmdanim(bot)
    ctx = DummyCtx()
    cog.giveaways[ctx.guild.id] = {"PRIZE": "x", "USERS": [], "RUNNING": True, "DURATION": 10}

    await cog.gend.callback(cog, ctx)

    assert ctx.guild.id not in cog.giveaways
    assert ctx.send.await_count >= 1


@pytest.mark.asyncio
async def test_utility_avatar_uses_display_avatar_url():
    bot = AsyncMock()
    cog = cmdutility(bot)
    ctx = DummyCtx()
    member = SimpleNamespace(display_avatar=SimpleNamespace(url="https://example.com/a.png"))

    await cog.avatar.callback(cog, ctx, member)

    assert ctx.send.await_count == 1


@pytest.mark.asyncio
async def test_moderation_slowmode_negative_value():
    bot = AsyncMock()
    cog = cmdmoderation(bot)
    ctx = DummyCtx()

    await cog.slowmode.callback(cog, ctx, -1)

    assert ctx.send.await_count == 1


@pytest.mark.asyncio
async def test_subscribe_rejects_non_numeric_choice():
    user = SimpleNamespace(id=1, mention="@u")
    channel = SimpleNamespace()

    first = SimpleNamespace(author=user, content="test show")
    second = SimpleNamespace(author=user, content="abc")

    bot = AsyncMock()
    bot.wait_for = AsyncMock(side_effect=[first, second])

    cog = cmdrss(bot)
    ctx = DummyCtx()
    ctx.author = user
    ctx.channel = channel

    class Resp:
        def __init__(self, payload):
            self.text = payload
            self.content = b""

    def fake_get(url):
        if "search/shows" in url:
            return Resp('[{"show": {"name": "Show", "network": null, "image": null}}]')
        if "singlesearch/shows" in url:
            return Resp('{"_embedded": {"episodes": []}}')
        return Resp("{}")

    import Notifrss as notif_module

    original_get = notif_module.requests.get
    notif_module.requests.get = fake_get
    try:
        await cog.subscribe.callback(cog, ctx)
    finally:
        notif_module.requests.get = original_get

    sent_texts = [
        call.kwargs.get("content") or (call.args[0] if call.args else "")
        for call in ctx.send.await_args_list
    ]
    assert any("Option invalide" in str(m) for m in sent_texts)
