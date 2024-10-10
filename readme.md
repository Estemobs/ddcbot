# DDCBot

DDCBot est un bot Discord personnalisé conçu pour gérer des fonctionnalités variées dans les serveurs Discord. Il est développé en Python et utilise l'API discord.py.

## Fonctionnalités principales

### Commandes générales

- `,help` : Affiche une liste des commandes disponibles
- `,rss` : Gère la lecture RSS
- `,utility` : Utilitaires divers
- `,moderation` : Gestion des permissions et modération
- `,animations` : Crée et gère des animations
- `,income` : Gestion des revenus
- `,economy` : Système économique
- `,work` : Gestion des tâches
- `,jeu` : Jeux et divertissements

### Configuration

Pour utiliser ce bot, vous devez créer un fichier `secrets.json` avec votre token Discord :

```json
{
  "ddc_token": "votre_token_discord_ici"
}
```

### Installation

1. Clonez ce dépôt :
   ```
   git clone https://github.com/estemobs/ddcbot.git
   ```
2. Installez les dépendances :
   ```
   pip install -r requirements.txt
   ```
3. Placez le fichier `secrets.json` à la racine du projet
4. Lancez le bot avec :
   ```
   python main.py
   ```

## Développement

Ce bot utilise plusieurs modules personnalisés :

- `cmdrss.py` : Gestion de la lecture RSS
- `cmdutility.py` : Utilitaires divers
- `cmdmoderation.py` : Permissions et modération
- `cmdanim.py` : Animations
- `cmdincome.py` : Gestion des revenus
- `cmdeco.py` : Système économique
- `cmdwork.py` : Tâches
- `cmdjeu.py` : Jeux et divertissements

Chaque module contient ses propres commandes et fonctionnalités spécifiques.

## Contributeurs

Vous pouvez contribuer au développement de ce bot en soumettant des pull requests ou en participant aux discussions sur GitHub.


