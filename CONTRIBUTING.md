# Contribution

Merci de vouloir contribuer à DDCBot !

## Développement

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Vérifications avant PR

```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
python -m compileall -q .
pytest -q
```

## Architecture

- Les cogs vivent dans `cogs/`, la base SQLite et ses migrations dans `data/`, `main.py` reste à la racine.
- Voir `CLAUDE.md` pour le détail de l'architecture (cogs, persistance SQLite, gate admin, diagnostics).

## Pull requests

1. Décrivez le problème résolu.
2. Lancez les vérifications ci-dessus.
3. Testez le bot dans un serveur de test Discord.
4. Référencez l'issue concernée dans la description.

## Licence

Ce projet est sous licence PolyForm Noncommercial 1.0.0 : l'utilisation commerciale est interdite.
