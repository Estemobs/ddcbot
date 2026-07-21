import os
import re
import sqlite3
import threading

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), 'migrations')
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), 'ddcbot.sqlite3')


class Database:
    """Wrapper sqlite3 partagé par tous les cogs (injecté depuis main.py)."""

    def __init__(self, path=None, migrations_dir=None):
        self.path = path or DEFAULT_DB_PATH
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._apply_migrations(migrations_dir or MIGRATIONS_DIR)

    def _apply_migrations(self, migrations_dir):
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        self._conn.commit()
        applied = {row["version"] for row in self._conn.execute("SELECT version FROM schema_migrations")}
        if not os.path.isdir(migrations_dir):
            return
        for filename in sorted(os.listdir(migrations_dir)):
            if not filename.endswith(".sql"):
                continue
            match = re.match(r"^(\d+)_", filename)
            if not match:
                continue
            version = int(match.group(1))
            if version in applied:
                continue
            with open(os.path.join(migrations_dir, filename)) as f:
                script = f.read()
            self._conn.executescript(script)
            self._conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (version,),
            )
            self._conn.commit()

    def execute(self, sql, params=()):
        with self._lock, self._conn:
            return self._conn.execute(sql, params)

    def executemany(self, sql, seq_of_params):
        with self._lock, self._conn:
            return self._conn.executemany(sql, seq_of_params)

    def fetchone(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def fetchall(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self):
        self._conn.close()
