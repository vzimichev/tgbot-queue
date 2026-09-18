import json
import sqlite3


class Repository:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.db.commit()

    def get(self, key):
        row = self.db.execute(
            "SELECT value FROM records WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, value):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO records VALUES (?, ?)", (key, json.dumps(value))
            )

    def delete(self, key):
        with self.db:
            self.db.execute("DELETE FROM records WHERE key = ?", (key,))

    def list_bots(self):
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT value FROM records WHERE key LIKE 'bot:%'"
            )
        ]

    def list_pending(self):
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT value FROM records WHERE key LIKE 'pending:%'"
            )
        ]
