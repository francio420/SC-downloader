import json
import os

from .constants import HISTORY_FILE

# ─── HistoryManager ──────────────────────────────────────────────────────────


class HistoryManager:
    """Gestisce la storia dei download in un file JSON."""

    def __init__(self, filepath=HISTORY_FILE):
        self.filepath = filepath
        self.entries = self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)

    def add(self, entry):
        self.entries.insert(0, entry)
        self._save()

    def get_all(self):
        return self.entries

    def clear(self):
        self.entries = []
        self._save()
