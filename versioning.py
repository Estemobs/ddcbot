"""Version unique du bot, partagee par ,help, ,version et ,changelog."""

import hashlib
import os
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
VERSION_FILE = os.path.join(PROJECT_ROOT, "VERSION")


def read_version_file():
    try:
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    except OSError:
        return "1.0.0"


def git_short_hash():
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return proc.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return None


def _file_digest():
    digest = hashlib.sha1()
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for filename in sorted(files):
            if not filename.endswith(".py"):
                continue
            file_path = os.path.join(root, filename)
            relative_path = os.path.relpath(file_path, PROJECT_ROOT)
            digest.update(relative_path.encode("utf-8"))
            with open(file_path, "rb") as file_handle:
                digest.update(file_handle.read())
    return digest.hexdigest()[:7]


def bot_version():
    """Retourne la version semver suivie du hash git (ou digest fichier)."""
    base = read_version_file()
    commit = git_short_hash()
    if commit:
        return f"{base}+{commit}"
    return f"{base}+{_file_digest()}"
