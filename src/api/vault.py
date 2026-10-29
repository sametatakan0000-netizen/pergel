"""Secure secrets vault — encrypted at rest, remote-accessible.

Design:
- Secrets stored in SQLite with AES-256 encryption (Fernet)
- Master password → PBKDF2 key derivation → encryption key
- Master password NEVER stored; only a verification hash
- Session tokens for web access (time-limited)
- Rate limiting on login attempts
- No telemetry, no external calls

Usage:
    vault = Vault("/path/to/vault.db")
    vault.init(master_password="...")
    vault.unlock(master_password="...")
    vault.set_secret("SUDO_PASSWORD", "value")
    vault.get_secret("SUDO_PASSWORD")
"""
import hashlib
import hmac


import secrets as pysecrets
import sqlite3
import time


try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    import base64
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class VaultError(Exception):
    pass


class Vault:
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._fernet = None
        self._unlocked = False
        self._sessions = {}  # token -> {expires, created}
        self._login_attempts = {}  # ip -> [timestamps]
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vault_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS secrets (
                    name TEXT PRIMARY KEY,
                    encrypted_value BLOB NOT NULL,
                    category TEXT DEFAULT 'general',
                    description TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    action TEXT NOT NULL,
                    secret_name TEXT DEFAULT '',
                    detail TEXT DEFAULT ''
                )
            """)

    def init(self, master_password: str):
        """Initialize vault with master password (first time only)."""
        if self.is_initialized():
            raise VaultError("Vault already initialized")
        if len(master_password) < 8:
            raise VaultError("Master password must be at least 8 characters")

        salt = pysecrets.token_bytes(32)
        key = self._derive_key(master_password, salt)
        verification = hashlib.sha256(key + b"pergel-vault-verify").hexdigest()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO vault_meta (key, value) VALUES (?, ?)",
                        ("salt", base64.b64encode(salt).decode()))
            conn.execute("INSERT INTO vault_meta (key, value) VALUES (?, ?)",
                        ("verification", verification))
            conn.execute("INSERT INTO vault_meta (key, value) VALUES (?, ?)",
                        ("created_at", str(time.time())))

        # Auto-unlock after init
        self._fernet = Fernet(base64.urlsafe_b64encode(key))
        self._unlocked = True
        self._log_audit("init", "", "Vault initialized")
        return True

    def is_initialized(self) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM vault_meta WHERE key='verification'").fetchone()
        return row is not None

    def unlock(self, master_password: str) -> bool:
        """Unlock vault with master password."""
        if not HAS_CRYPTO:
            raise VaultError("cryptography package required: pip install cryptography")
        with sqlite3.connect(self.db_path) as conn:
            salt_row = conn.execute("SELECT value FROM vault_meta WHERE key='salt'").fetchone()
            verify_row = conn.execute("SELECT value FROM vault_meta WHERE key='verification'").fetchone()
        if not salt_row or not verify_row:
            raise VaultError("Vault not initialized")

        salt = base64.b64decode(salt_row[0])
        key = self._derive_key(master_password, salt)
        verification = hashlib.sha256(key + b"pergel-vault-verify").hexdigest()

        if not hmac.compare_digest(verification, verify_row[0]):
            self._log_audit("failed_unlock", "", "Invalid master password")
            return False

        self._fernet = Fernet(base64.urlsafe_b64encode(key))
        self._unlocked = True
        self._log_audit("unlock", "", "Vault unlocked")
        return True

    def lock(self):
        self._fernet = None
        self._unlocked = False
        self._sessions.clear()

    def is_unlocked(self) -> bool:
        return self._unlocked

    def set_secret(self, name: str, value: str, category: str = "general", description: str = ""):
        if not self._unlocked:
            raise VaultError("Vault is locked")
        encrypted = self._fernet.encrypt(value.encode())
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute("SELECT name FROM secrets WHERE name=?", (name,)).fetchone()
            if existing:
                conn.execute("UPDATE secrets SET encrypted_value=?, category=?, description=?, updated_at=? WHERE name=?",
                           (encrypted, category, description, now, name))
            else:
                conn.execute("INSERT INTO secrets (name, encrypted_value, category, description, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                           (name, encrypted, category, description, now, now))
        self._log_audit("set", name, f"Category: {category}")

    def get_secret(self, name: str) -> str:
        if not self._unlocked:
            raise VaultError("Vault is locked")
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT encrypted_value FROM secrets WHERE name=?", (name,)).fetchone()
        if not row:
            raise VaultError(f"Secret '{name}' not found")
        try:
            return self._fernet.decrypt(row[0]).decode()
        except InvalidToken:
            raise VaultError("Decryption failed — wrong master password?")

    def delete_secret(self, name: str):
        if not self._unlocked:
            raise VaultError("Vault is locked")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM secrets WHERE name=?", (name,))
        self._log_audit("delete", name, "")

    def list_secrets(self) -> list:
        if not self._unlocked:
            raise VaultError("Vault is locked")
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT name, category, description, created_at, updated_at FROM secrets ORDER BY category, name").fetchall()
        return [{"name": r[0], "category": r[1], "description": r[2], "created_at": r[3], "updated_at": r[4]} for r in rows]

    def get_all_for_env(self) -> dict:
        """Return all secrets as a dict (for env injection). Values are decrypted."""
        if not self._unlocked:
            raise VaultError("Vault is locked")
        result = {}
        for s in self.list_secrets():
            result[s["name"]] = self.get_secret(s["name"])
        return result

    def export_env(self) -> str:
        """Export secrets as .env format string (for backup/export)."""
        env = self.get_all_for_env()
        lines = [f"{k}={v}" for k, v in sorted(env.items())]
        return "\n".join(lines)

    # --- Sessions ---
    def create_session(self) -> str:
        token = pysecrets.token_urlsafe(32)
        self._sessions[token] = {"created": time.time(), "expires": time.time() + 3600}
        return token

    def validate_session(self, token: str) -> bool:
        s = self._sessions.get(token)
        if not s or s["expires"] < time.time():
            self._sessions.pop(token, None)
            return False
        return True

    def revoke_session(self, token: str):
        self._sessions.pop(token, None)

    # --- Rate limiting ---
    def check_rate_limit(self, ip: str) -> bool:
        """Returns True if login allowed, False if rate limited."""
        now = time.time()
        attempts = self._login_attempts.get(ip, [])
        attempts = [a for a in attempts if now - a < 300]  # 5 min window
        self._login_attempts[ip] = attempts
        return len(attempts) < 5

    def record_login_attempt(self, ip: str):
        self._login_attempts.setdefault(ip, []).append(time.time())

    def get_audit_log(self, limit: int = 50) -> list:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT timestamp, action, secret_name, detail FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"timestamp": r[0], "action": r[1], "secret_name": r[2], "detail": r[3]} for r in rows]

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
        return kdf.derive(password.encode())

    def _log_audit(self, action: str, name: str, detail: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO audit_log (timestamp, action, secret_name, detail) VALUES (?,?,?,?)",
                        (time.time(), action, name, detail))
