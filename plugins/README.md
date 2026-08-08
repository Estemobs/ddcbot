# Plugins DDCBot

Les plugins sont des extensions chargees au demarrage en plus des cogs du
bot.

## Structure

Un plugin est un dossier dans `plugins/` contenant au minimum un module
`plugin.py` :

```
plugins/
  mon_plugin/
    plugin.py        # obligatoire
    manifest.json    # optionnel (name, version, description)
    ...
```

`plugin.py` doit exposer :

- `setup(bot, db)` — obligatoire. Enregistre les cogs : `bot.add_cog(...)`
  (peut etre asynchrone).
- `teardown(bot, db)` — optionnel. Cleanup (les cogs ajoutes par le plugin
  sont retires automatiquement).

Exemple minimal :

```python
from discord.ext import commands


class MonCog(commands.Cog):
    @commands.command()
    async def ping(self, ctx):
        await ctx.send("pong!")


def setup(bot, db):
    bot.add_cog(MonCog(bot, db))
```

`manifest.json` (optionnel) :

```json
{
  "name": "mon_plugin",
  "version": "1.0.0",
  "description": "Description courte"
}
```

## Gestion

- `,plugins list` — liste les plugins et leur statut (admin).
- `,plugins enable <nom>` — active et charge un plugin (admin).
- `,plugins disable <nom>` — desactive et decharge un plugin (admin).
- `,plugins reload [nom]` — recharge tous les plugins ou un seul (admin).

L'etat (actif/inactif) est persiste dans la table `plugins`. Un plugin non
reference est active par defaut au demarrage.

Note : si un plugin ajoute des commandes Discord, elles se retrouveront
dans le registre du bot ; commandez-les via `,plugins` / `,selftest`,
mais `EXPECTED_COMMANDS` (selftest) ne les attend pas et ne signalera pas
d'erreur pour des commandes supplementaires.