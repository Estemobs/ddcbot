# DDCBot

Bot Discord multi-commandes pour gestion serveur, economie, mini-jeux et notifications RSS.

## Prerequis

- Python 3.10+
- Un token de bot Discord

## Installation propre (venv)

1. Cloner le depot:

```bash
git clone https://github.com/Estemobs/ddcbot.git
cd ddcbot
```

2. Creer un environnement virtuel:

```bash
python3 -m venv .venv
```

3. Activer l'environnement:

```bash
source .venv/bin/activate
```

4. Mettre pip a jour (recommande):

```bash
python -m pip install --upgrade pip
```

5. Installer les dependances:

```bash
pip install -r requirements.txt
```

## Configuration

Creer un fichier `secrets.json` a la racine du projet:

```json
{
  "ddc_token": "VOTRE_TOKEN_DISCORD"
}

Alternative (recommandée pour Docker):

Vous pouvez fournir le token via une variable d'environnement plutôt que `secrets.json`. Cela permet des déploiements Docker/CI plus sûrs et évite d'écrire des secrets sur le disque.

Exemples d'usage:

```bash
export DDC_TOKEN="VOTRE_TOKEN_DISCORD"
python main.py
```

Le code prend prioritairement `DDC_TOKEN` (ou `DDC_BOT_TOKEN`) depuis l'environnement et retombe sur `secrets.json` si la variable n'existe pas.
```

## Lancement du bot

Depuis la racine du projet, avec le venv actif:

```bash
python main.py
```

## Notes utiles

- Le prefixe de commande est configure dans le code (`main.py`).
- Les fichiers JSON de configuration et de donnees (`balances.json`, `income.json`, etc.) doivent rester a la racine.

## Licence

Ce projet est sous licence [CC BY-NC-SA 4.0](http://creativecommons.org/licenses/by-nc-sa/4.0/).
Utilisation commerciale interdite. Voir le fichier [LICENSE](LICENSE) pour plus de details.

