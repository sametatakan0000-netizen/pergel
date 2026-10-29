"""Pergel Session Manager - crash recovery and session restore.

Persists open tabs to disk so a crash or restart can restore them.
SOTA reference: Chrome/Firefox/Edge all auto-restore on crash.
"""
import json
import time
from pathlib import Path
from typing import Optional


class SessionManager:
    """Persists browser session state (open tabs) to disk."""

    def __init__(self, profile_dir: str):
        self.profile_dir = Path(profile_dir)
        self.session_file = self.profile_dir / "pergel_session.json"
        self.backup_file = self.profile_dir / "pergel_session.backup.json"

    def save_session(self, tabs: list) -> bool:
        """Save current session state.

        tabs: [{"url": str, "title": str, "pinned": bool, "index": int}, ...]
        """
        try:
            if self.session_file.exists():
                self.session_file.rename(self.backup_file)
            state = {
                "version": 1,
                "timestamp": time.time(),
                "tabs": tabs,
            }
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self.session_file.write_text(
                json.dumps(state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def load_session(self) -> Optional[dict]:
        """Load saved session. Returns None if no session or corrupt."""
        for path in (self.session_file, self.backup_file):
            try:
                if path.exists():
                    state = json.loads(path.read_text(encoding="utf-8"))
                    if state.get("version") == 1 and state.get("tabs"):
                        return state
            except Exception:
                continue
        return None

    def clear_session(self) -> None:
        """Clear saved session (user chose not to restore)."""
        for path in (self.session_file, self.backup_file):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def has_crashed_session(self) -> bool:
        """Check if there is a session that was not cleanly closed."""
        return self.load_session() is not None

    def get_restore_urls(self) -> list:
        """Get URLs to restore from saved session."""
        state = self.load_session()
        if state:
            return [t.get("url", "") for t in state.get("tabs", []) if t.get("url")]
        return []
