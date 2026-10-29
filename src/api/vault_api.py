"""Vault HTTP API — RESTful endpoints for secrets management.

Endpoints:
    GET  /v1/vault/status          — vault initialized? (no auth needed)
    POST /v1/vault/init            — initialize with master password
    POST /v1/vault/unlock          — unlock with master password
    POST /v1/vault/lock            — lock vault
    GET  /v1/vault/check           — check session validity
    GET  /v1/vault/secrets         — list all secret names
    GET  /v1/vault/secret/:name    — get secret value
    POST /v1/vault/secret          — create/update secret
    DELETE /v1/vault/secret/:name  — delete secret
    GET  /v1/vault/audit           — audit log
    GET  /v1/vault/export          — export as .env
"""
import json
import os
from pathlib import Path

from src.api.vault import Vault, VaultError


class VaultAPI:
    def __init__(self, db_path: str = None):
        if db_path is None:
            config_home = os.path.expanduser("~/.config/pergel")
            os.makedirs(config_home, exist_ok=True)
            db_path = os.path.join(config_home, "vault.db")
        self.vault = Vault(db_path)

    def handle(self, method: str, path: str, body: dict, headers: dict, client_ip: str = "127.0.0.1") -> tuple:
        """Returns (status_code, response_dict)."""
        path = path.rstrip("/")

        # Public endpoints (no auth)
        if method == "GET" and path == "/v1/vault/status":
            return 200, {"initialized": self.vault.is_initialized(), "unlocked": self.vault.is_unlocked()}

        if method == "POST" and path == "/v1/vault/init":
            pw = body.get("password", "")
            try:
                self.vault.init(pw)
                token = self.vault.create_session()
                return 200, {"token": token, "message": "Vault initialized"}
            except VaultError as e:
                return 400, {"error": str(e)}

        if method == "POST" and path == "/v1/vault/unlock":
            if not self.vault.check_rate_limit(client_ip):
                return 429, {"error": "Too many attempts. Try again in 5 minutes."}
            self.vault.record_login_attempt(client_ip)
            pw = body.get("password", "")
            if self.vault.unlock(pw):
                token = self.vault.create_session()
                return 200, {"token": token, "message": "Vault unlocked"}
            return 401, {"error": "Invalid master password"}

        # Authenticated endpoints
        token = headers.get("X-Vault-Token", headers.get("x-vault-token", ""))
        if not self.vault.validate_session(token):
            return 401, {"error": "Not authenticated or session expired"}

        if method == "POST" and path == "/v1/vault/lock":
            self.vault.lock()
            return 200, {"message": "Vault locked"}

        if method == "GET" and path == "/v1/vault/check":
            return 200, {"valid": True}

        if method == "GET" and path == "/v1/vault/secrets":
            return 200, {"secrets": self.vault.list_secrets()}

        if method == "GET" and path.startswith("/v1/vault/secret/"):
            name = path.split("/v1/vault/secret/", 1)[1]
            try:
                value = self.vault.get_secret(name)
                return 200, {"name": name, "value": value}
            except VaultError as e:
                return 404, {"error": str(e)}

        if method == "POST" and path == "/v1/vault/secret":
            name = body.get("name", "")
            value = body.get("value", "")
            category = body.get("category", "general")
            description = body.get("description", "")
            if not name:
                return 400, {"error": "Name is required"}
            try:
                if value:
                    self.vault.set_secret(name, value, category, description)
                else:
                    # Update metadata only (keep existing value)
                    existing = self.vault.get_secret(name)
                    self.vault.set_secret(name, existing, category, description)
                return 200, {"message": f"Secret '{name}' saved"}
            except VaultError as e:
                return 400, {"error": str(e)}

        if method == "DELETE" and path.startswith("/v1/vault/secret/"):
            name = path.split("/v1/vault/secret/", 1)[1]
            self.vault.delete_secret(name)
            return 200, {"message": f"Secret '{name}' deleted"}

        if method == "GET" and path == "/v1/vault/audit":
            return 200, {"log": self.vault.get_audit_log()}

        if method == "GET" and path == "/v1/vault/export":
            try:
                env = self.vault.export_env()
                return 200, {"env": env}
            except VaultError as e:
                return 400, {"error": str(e)}

        return 404, {"error": "Not found"}
