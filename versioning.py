"""Version unique du bot : le hash du commit courant de la branche deployee."""

import os
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))


def git_commit_hash():
    """Retourne le hash complet du commit courant (HEAD)."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return proc.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def bot_version():
    """Retourne le hash du commit courant, ou \"inconnu\" si git est indisponible."""
    return git_commit_hash() or "inconnu"
