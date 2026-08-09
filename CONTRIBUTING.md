# Contribution

Merci de vouloir contribuer à DDCBot !

## Développement

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dashboard.txt
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

Ce projet est sous licence GNU General Public License v3.0 (GPL-3.0). Toute contribution est acceptée sous cette licence ; toute version modifiée ou redistribuée doit rester sous GPL-3.0 avec le code source.
