"""Vault tests — encrypted secrets, sessions, rate limiting."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.vault import Vault, VaultError
from src.api.vault_api import VaultAPI


def _tmp_db():
    return os.path.join(tempfile.mkdtemp(), "test_vault.db")


def test_init_and_unlock():
    v = Vault(_tmp_db())
    assert not v.is_initialized()
    v.init("testpass123")
    assert v.is_initialized()
    assert v.is_unlocked()  # init auto-unlocks
    v.lock()
    assert not v.is_unlocked()
    assert v.unlock("testpass123")
    assert v.is_unlocked()
    assert not v.unlock("wrongpass")
    v.lock()
    assert not v.is_unlocked()
    print("PASS test_init_and_unlock")

def test_set_get_delete_secret():
    v = Vault(_tmp_db())
    v.init("testpass123")
    v.unlock("testpass123")
    v.set_secret("API_KEY", "sk-1234567890", category="api", description="Test key")
    assert v.get_secret("API_KEY") == "sk-1234567890"
    v.set_secret("API_KEY", "sk-new-key", category="api")
    assert v.get_secret("API_KEY") == "sk-new-key"
    v.delete_secret("API_KEY")
    try:
        v.get_secret("API_KEY")
        assert False, "should raise"
    except VaultError:
        pass
    print("PASS test_set_get_delete_secret")

def test_list_secrets():
    v = Vault(_tmp_db())
    v.init("testpass123")
    v.unlock("testpass123")
    v.set_secret("A", "1", category="system")
    v.set_secret("B", "2", category="api")
    v.set_secret("C", "3", category="system")
    lst = v.list_secrets()
    assert len(lst) == 3
    names = [s["name"] for s in lst]
    assert "A" in names and "B" in names and "C" in names
    assert lst[0]["category"] in ("system", "api")
    print("PASS test_list_secrets")

def test_export_env():
    v = Vault(_tmp_db())
    v.init("testpass123")
    v.unlock("testpass123")
    v.set_secret("FOO", "bar")
    v.set_secret("BAZ", "qux")
    env = v.export_env()
    assert "FOO=bar" in env
    assert "BAZ=qux" in env
    print("PASS test_export_env")

def test_sessions():
    v = Vault(_tmp_db())
    v.init("testpass123")
    v.unlock("testpass123")
    token = v.create_session()
    assert v.validate_session(token)
    v.revoke_session(token)
    assert not v.validate_session(token)
    print("PASS test_sessions")

def test_rate_limiting():
    v = Vault(_tmp_db())
    v.init("testpass123")
    for i in range(5):
        assert v.check_rate_limit("1.2.3.4")
        v.record_login_attempt("1.2.3.4")
    assert not v.check_rate_limit("1.2.3.4")
    assert v.check_rate_limit("5.6.7.8")
    print("PASS test_rate_limiting")

def test_audit_log():
    v = Vault(_tmp_db())
    v.init("testpass123")
    v.unlock("testpass123")
    v.set_secret("TEST", "value")
    v.delete_secret("TEST")
    log = v.get_audit_log()
    actions = [e["action"] for e in log]
    assert "init" in actions
    assert "unlock" in actions
    assert "set" in actions
    assert "delete" in actions
    print("PASS test_audit_log")

def test_api_flow():
    api = VaultAPI(_tmp_db())
    # Status
    code, resp = api.handle("GET", "/v1/vault/status", {}, {})
    assert code == 200 and resp["initialized"] == False
    # Init
    code, resp = api.handle("POST", "/v1/vault/init", {"password": "testpass123"}, {})
    assert code == 200 and "token" in resp
    token = resp["token"]
    # Set secret
    code, resp = api.handle("POST", "/v1/vault/secret", {"name": "KEY", "value": "val1"}, {"X-Vault-Token": token})
    assert code == 200
    # Get secret
    code, resp = api.handle("GET", "/v1/vault/secret/KEY", {}, {"X-Vault-Token": token})
    assert code == 200 and resp["value"] == "val1"
    # List
    code, resp = api.handle("GET", "/v1/vault/secrets", {}, {"X-Vault-Token": token})
    assert code == 200 and len(resp["secrets"]) == 1
    # Unauth
    code, resp = api.handle("GET", "/v1/vault/secrets", {}, {})
    assert code == 401
    # Export
    code, resp = api.handle("GET", "/v1/vault/export", {}, {"X-Vault-Token": token})
    assert code == 200 and "KEY=val1" in resp["env"]
    print("PASS test_api_flow")


if __name__ == "__main__":
    test_init_and_unlock()
    test_set_get_delete_secret()
    test_list_secrets()
    test_export_env()
    test_sessions()
    test_rate_limiting()
    test_audit_log()
    test_api_flow()
    print("=== ALL VAULT TESTS PASS (8/8) ===")
