import sys
import os
import types
from unittest.mock import MagicMock

# Make the root project directory importable from within tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Build a comprehensive discord.py stub so cogs can be imported
# and instantiated without discord.py installed.
if "discord" not in sys.modules:

    class _StubClass:
        """Generic stub that returns itself for any attribute access or call."""
        def __getattr__(self, name):
            return _StubClass()
        def __call__(self, *a, **kw):
            return self
        def __bool__(self):
            return False
        def __iter__(self):
            return iter([])

    def _make_stub(*args, **kwargs):
        return _StubClass()

    # discord module
    discord = types.ModuleType("discord")
    discord.__all__ = []

    # Common types used at import time
    for attr in [
        "Embed", "Color", "Colour", "File", "Permissions", "AllowedMentions",
        "Guild", "Member", "User", "Role", "Message", "TextChannel",
        "CategoryChannel", "VoiceChannel", "Interaction", "Invite",
        "Webhook", "SelectOption", "ButtonStyle", "Intents", "Game",
        "NotFound", "HTTPException", "DiscordException", "PermissionOverwrite",
    ]:
        setattr(discord, attr, _StubClass())

    # discord.errors
    errors_mod = types.ModuleType("discord.errors")
    errors_mod.NotFound = type("NotFound", (Exception,), {})
    errors_mod.HTTPException = type("HTTPException", (Exception,), {})
    errors_mod.Forbidden = type("Forbidden", (Exception,), {})
    discord.errors = errors_mod
    sys.modules["discord.errors"] = errors_mod

    # discord.app_commands
    app_commands = types.ModuleType("discord.app_commands")
    app_commands.command = lambda *a, **kw: (lambda f: f)
    app_commands.describe = lambda *a, **kw: (lambda f: f)
    app_commands.check = lambda *a, **kw: (lambda f: f) if not callable(a[0] if a else None) else a[0]
    app_commands.guild_only = lambda f: f
    app_commands.default_permissions = lambda **kw: (lambda f: f)
    app_commands.Choice = _StubClass()
    app_commands.transform = types.ModuleType("discord.app_commands.transform")
    discord.app_commands = app_commands
    sys.modules["discord.app_commands"] = app_commands

    # discord.ui
    ui = types.ModuleType("discord.ui")

    class _View:
        def __init__(self, *args, **kwargs):
            self.timeout = 300
        async def interaction_check(self, interaction):
            return True
        async def on_timeout(self):
            pass

    ui.View = _View
    ui.button = lambda *a, **kw: (lambda f: f)
    ui.select = lambda *a, **kw: (lambda f: f)
    ui.Button = _StubClass
    ui.Select = _StubClass
    ui.RoleSelect = _StubClass
    ui.UserSelect = _StubClass
    ui.Modal = type("Modal", (), {"__init__": lambda self, *a, **kw: None})
    ui.TextInput = _StubClass
    ui.ActionRow = _StubClass
    discord.ui = ui
    sys.modules["discord.ui"] = ui

    # discord.ext.commands
    ext = types.ModuleType("discord.ext")

    commands = types.ModuleType("discord.ext.commands")

    class _Cog:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def listener(name=None):
            def decorator(func):
                return func
            return decorator

    commands.Cog = _Cog
    commands.CogMeta = type("CogMeta", (), {})
    commands.command = lambda *a, **kw: (lambda f: f)
    commands.group = lambda *a, **kw: (lambda f: f)
    commands.hybrid_command = lambda *a, **kw: (lambda f: f)
    commands.hybrid_group = lambda *a, **kw: (lambda f: f)
    commands.has_permissions = lambda **kw: (lambda f: f)
    commands.has_guild_permissions = lambda **kw: (lambda f: f)
    commands.has_role = lambda *a: (lambda f: f)
    commands.bot_has_permissions = lambda **kw: (lambda f: f)
    commands.is_owner = lambda f: f
    commands.guild_only = lambda f: f
    commands.dm_only = lambda f: f
    commands.check = lambda *a, **kw: (lambda f: f) if not callable(a[0] if a else None) else a[0]
    commands.get = lambda *a, **kw: None
    commands.BadArgument = type("BadArgument", (Exception,), {})
    commands.MissingRequiredArgument = type("MissingRequiredArgument", (Exception,), {})
    commands.CommandNotFound = type("CommandNotFound", (Exception,), {})
    commands.CommandInvokeError = type("CommandInvokeError", (Exception,), {})
    commands.CommandOnCooldown = type("CommandOnCooldown", (Exception,), {})
    commands.ConversionError = type("ConversionError", (Exception,), {})
    commands.Bot = MagicMock
    commands.BotBase = MagicMock
    commands.Context = MagicMock
    commands.CogConverter = MagicMock
    ext.commands = commands

    # discord.ext.tasks
    tasks = types.ModuleType("discord.ext.tasks")
    tasks.loop = lambda *a, **kw: (lambda f: f)
    discord.ext = ext
    sys.modules["discord"] = discord
    sys.modules["discord.ext"] = ext
    sys.modules["discord.ext.commands"] = commands
    sys.modules["discord.ext.tasks"] = tasks
    sys.modules["discord.utils"] = types.ModuleType("discord.utils")
