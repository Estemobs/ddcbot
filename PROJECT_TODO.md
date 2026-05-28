# PROJECT TODO — DDCBot

Ce fichier centralise les tâches, priorités et instructions pour reprendre le projet.
Mettez à jour ce fichier et la TODO list (outil) quand vous marquez une tâche comme faite.

## Principe
- Les tâches sont regroupées par priorité. Les actions marquées "déjà fait" sont cochées.
- Pour chaque tâche, indiquer un petit descriptif, dépendances (si nécessaire), et comment valider (tests, commandes).
- Respecter la compatibilité Docker : toute nouvelle fonctionnalité dépendante d'un service (ex: FastAPI) doit être optionnelle ou documentée dans la section Docker.

## Statut actuel (résumé rapide)
- Logging centralisé et lecture du token via `DDC_TOKEN` : fait.
- `ai_assistant.py` : prints remplacés par logger : fait.
- `.gitignore` étendu : fait.
- `README.md` : documenté pour `DDC_TOKEN` : fait.

## Tâches prioritaires (A faire en premier)
1. Ajouter CI GitHub Actions (pytest, lint, format)
   - Description : Créer `.github/workflows/ci.yml` qui installe deps et exécute `pytest`, `ruff` et `black --check`.
   - Validation : workflow passe sur push/PR.
   - Compatibilité Docker : aucune.

2. Scanner et remplacer tous les `print()` restants par `logger`
   - Description : parcourir les cogs et modules (`utility.py`, `Notifrss.py`, `notifications`, etc.).
   - Validation : lancement local du bot (ou tests) sans affichage `print()` non désiré. Code review.

3. Créer `requirements-dev.txt` (pytest, black, ruff, mypy)
   - Description : lister les dépendances de dev pour faciliter l'installation locale et CI.
   - Validation : `pip install -r requirements-dev.txt` ok.

4. Pinner `requirements.txt` ou migrer vers `pyproject.toml`/`poetry`
   - Description : assurer reproductibilité. Option: créer `pyproject.toml` minimal pour poetry.
   - Validation : build reproducible en CI.

5. Faire tourner les tests et corriger régressions (local & CI)
   - Commandes locales recommandées:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     python -m pip install --upgrade pip
     python -m pip install -r requirements.txt
     python -m pip install -r requirements-dev.txt
     pytest -q
     ```
   - Validation : `pytest` passe.

## Tâches moyennes
6. Ajouter script d'export/import (backup) pour JSON
   - Description : script `tools/backup_json.py` qui zippe les fichiers JSON et notifie la présence d'un backup.
   - Validation : backup créé et import possible.

7. Plan de migration JSON → SQLite
   - Description : créer scripts pour migration, wrapper d'accès DB et verrous.
   - Validation : tests d'intégrité, rollback possible.

8. Ajouter validation config centralisée (`config.py` + pydantic)
   - Description : centraliser chemins et options, valider à l'import.
   - Validation : projet lève des erreurs claires si la config est invalide.

9. Ajouter docs d'installation Docker & variables d'environnement dans `README.md`
   - Description : documenter `DDC_TOKEN`, volumes pour données, et recommandations (restart on push).
   - Validation : README à jour.

## Fonctionnalités avancées (optionnelles)
10. Commandes interactives pour gérer `permission_config.json`
11. Options IA avancées: provider selection, API key support, sanitisation
12. Monitoring / health endpoint (FastAPI minimal)
13. Backup automatique (cron / scheduled task)
14. Tests unitaires supplémentaires pour cogs manquants
15. Documenter processus de contribution et checklist PR

## Processus de validation & contributions
- Avant de merger une PR :
  - Tous les tests passent en CI.
  - `black --check` passe et `ruff` ne signale pas d'erreurs bloquantes.
  - Le maintainers examine les changements qui impactent Docker.
- Pour marquer une tâche comme réalisée :
  1. Mettre à jour `PROJECT_TODO.md` (cocher la tâche).
  2. Mettre à jour la TODO list centrale (outil de suivi si présent).
  3. Ouvrir une PR avec une description et tests associés.

## Notes Docker / Déploiement
- Par défaut, les modifications apportées ici sont compatibles avec un container qui redémarre au push (ne changez pas l'entrypoint sans le documenter).
- Pour toute tâche nécessitant un service additionnel (ex: FastAPI, PostgreSQL), ajouter un flag d'activation et des instructions Docker/compose.

## Prochaine étape proposée
- Je peux créer immédiatement :
  - A) Le workflow GitHub Actions CI (fichier prêt).
  - B) Un script qui scanne le repo et remplace automatiquement les `print()` par `logger` (présentation avant commit).

Indiquez A, B ou "les deux" et j'implémente cela.

---

*Fichier généré automatiquement par l'assistant — mettre à jour manuellement si besoin.*
