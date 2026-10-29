"""Browser migration — the door users walk through to switch browsers.

Imports bookmarks, history and passwords from Chrome/Chromium/Edge/Brave/
Vivaldi (Chromium family) and Firefox, and exports everything back out in
universal formats (Netscape HTML, JSON, CSV, password CSV). Pergel's own
profile is standard Chromium, so writing INTO it is just writing the
standard files (``Bookmarks`` JSON, ``History`` SQLite, ``Login Data`` SQLite).

Security: reports carry COUNTS only — never titles from password rows and
never secret values (red line in this project). Chrome epoch: µs since
1601-01-01; Firefox places: µs since unix epoch.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sqlite3
import time
from typing import Optional

CHROME_EPOCH_OFFSET = 11644473600

CHROMIUM_ROOTS = [
    ("chrome", "~/.config/google-chrome"),
    ("chromium", "~/.config/chromium"),
    ("edge", "~/.config/microsoft-edge"),
    ("brave", "~/.config/BraveSoftware/Brave-Browser"),
    ("vivaldi", "~/.config/vivaldi"),
]
FIREFOX_ROOT = "~/.mozilla/firefox"

# Chromium password store (Linux, no keyring): v10 = AES-128-CBC, key from
# PBKDF2-HMAC-SHA1("peanuts", "saltysalt", 1). This is Chromium's own
# documented fallback format — Pergel writes its own profile's store with it.
_V10_SALT = b"saltysalt"
_V10_IV = b" " * 16


# ---------- import: Chromium family ----------

def _bookmark_nodes(node: dict, folder: str, out: list) -> None:
    for child in node.get("children", []):
        if child.get("type") == "folder":
            _bookmark_nodes(child, child.get("name", ""), out)
        elif child.get("type") == "url" and child.get("url"):
            out.append({"title": child.get("name", ""),
                        "url": child["url"], "folder": folder})


def import_chromium_bookmarks(default_dir: str) -> list:
    path = os.path.join(default_dir, "Bookmarks")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out: list = []
    for key, folder in (("bookmark_bar", "Bookmarks bar"),
                        ("other", "Other bookmarks"),
                        ("synced", "Mobile bookmarks")):
        root = data.get("roots", {}).get(key)
        if root:
            _bookmark_nodes(root, folder, out)
    return out


def _chrome_ts_to_unix(micros: int) -> int:
    return int(micros / 1_000_000) - CHROME_EPOCH_OFFSET if micros else 0


def _unix_to_chrome_ts(secs: int) -> int:
    return int((secs + CHROME_EPOCH_OFFSET) * 1_000_000)


def import_chromium_history(default_dir: str, limit: int = 200_000) -> list:
    path = os.path.join(default_dir, "History")
    if not os.path.isfile(path):
        return []
    tmp = path + ".mig-copy"
    shutil.copyfile(path, tmp)          # never open a live browser's DB
    try:
        con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT url, title, last_visit_time FROM urls "
            "WHERE hidden = 0 ORDER BY last_visit_time DESC LIMIT ?",
            (limit,)).fetchall()
        con.close()
    finally:
        os.remove(tmp)
    return [{"url": u, "title": t or "", "ts": _chrome_ts_to_unix(ts or 0)}
            for u, t, ts in rows]


# ---------- import: Firefox ----------

def import_firefox_bookmarks_json(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out: list = []

    def walk(node: dict, folder: str) -> None:
        t = node.get("type", "")
        for child in node.get("children", []):
            if child.get("type", "").endswith("container") or "children" in child:
                walk(child, child.get("title", folder))
            elif child.get("uri"):
                out.append({"title": child.get("title", ""),
                            "url": child["uri"], "folder": folder})

    walk(data, "")
    return out


def import_firefox_places(profile_dir: str, limit: int = 200_000) -> list:
    path = os.path.join(profile_dir, "places.sqlite")
    if not os.path.isfile(path):
        return []
    tmp = path + ".mig-copy"
    shutil.copyfile(path, tmp)
    try:
        con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT url, title, last_visit_date FROM moz_places "
            "WHERE last_visit_date IS NOT NULL "
            "ORDER BY last_visit_date DESC LIMIT ?", (limit,)).fetchall()
        con.close()
    finally:
        os.remove(tmp)
    return [{"url": u, "title": t or "", "ts": int((d or 0) / 1_000_000)}
            for u, t, d in rows]


# ---------- import: universal formats ----------

def import_netscape_html(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        html = f.read()
    out: list = []
    folder = ""
    folder_stack: list = []
    for m in re.finditer(
            r"<DT>\s*(?:<H3[^>]*>(.*?)</H3>|<A\s[^>]*HREF=\"([^\"]+)\"[^>]*>(.*?)</A>)",
            html, re.I | re.S):
        if m.group(2):
            out.append({"title": re.sub(r"<[^>]+>", "", m.group(3) or "").strip(),
                        "url": m.group(2), "folder": folder})
        else:
            folder = re.sub(r"<[^>]+>", "", m.group(1) or "").strip()
    return out


def import_csv(path: str) -> list:
    out: list = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048); f.seek(0)
        dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
        for row in csv.reader(f, dialect):
            if not row or row[0].lower() in ("url", "uri"):
                continue
            url = row[0]
            title = row[1] if len(row) > 1 else ""
            folder = row[2] if len(row) > 2 else ""
            if url.startswith(("http", "file", "ftp")):
                out.append({"title": title, "url": url, "folder": folder})
    return out


def import_passwords_csv(path: str) -> list:
    """Standard interchange: url/name/origin, username, password.

    Header row (when present) selects the columns; headerless files fall
    back to ``url,username,password`` positionally.
    """
    out: list = []
    idx: Optional[dict] = None
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            head = [c.strip().lower() for c in row]
            if "password" in head:
                idx = {"origin": next((head.index(c) for c in
                                       ("url", "origin", "name")
                                       if c in head), 0),
                       "username": head.index("username")
                       if "username" in head else 1,
                       "password": head.index("password")}
                continue
            if idx is not None:
                def cell(key, default=""):
                    i = idx.get(key, -1)
                    return row[i] if 0 <= i < len(row) else default
                out.append({"origin": cell("origin"),
                            "username": cell("username"),
                            "password": cell("password")})
            elif len(row) >= 3 and row[0].startswith("http"):
                out.append({"origin": row[0], "username": row[1],
                            "password": row[2]})
    return out


# ---------- export ----------

def export_netscape_html(rows: list, path: str) -> str:
    parts = ['<!DOCTYPE NETSCAPE-Bookmark-file-1>',
             '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
             "<TITLE>Bookmarks</TITLE>", "<H1>Bookmarks</H1>",
             "<DL><p>"]
    for r in rows:
        folder = r.get("folder", "")
        if folder:
            parts.append(f"<DT><H3>{folder}</H3>")
            parts.append("<DL><p>")
        parts.append(f'<DT><A HREF="{r["url"]}">{r.get("title", "")}</A>')
        if folder:
            parts.append("</DL><p>")
    parts.append("</DL><p>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    return path


def export_json(data: object, path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def export_csv(rows: list, path: str) -> str:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "title", "folder"])
        for r in rows:
            w.writerow([r.get("url", ""), r.get("title", ""), r.get("folder", "")])
    return path


def export_passwords_csv(rows: list, path: str) -> str:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "username", "password"])
        for r in rows:
            w.writerow([r.get("origin", ""), r.get("username", ""),
                        r.get("password", "")])
    return path


# ---------- write into Pergel's own Chromium profile ----------

IMPORT_FOLDER = "İçe Aktarılanlar"


def write_chromium_bookmarks(rows: list, default_dir: str,
                             source: str = "import") -> int:
    """Merge rows into the profile's ``Bookmarks`` JSON (Chromium format).

    The checksum key is dropped after edit — Chromium accepts a missing
    checksum and recomputes on its next bookmark change.
    """
    os.makedirs(default_dir, exist_ok=True)
    path = os.path.join(default_dir, "Bookmarks")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"roots": {}, "version": 1}
    roots = data.setdefault("roots", {})
    bar = roots.setdefault("bookmark_bar",
                           {"type": "folder", "name": "Bookmarks bar",
                            "children": []})
    children = bar.setdefault("children", [])
    folder = None
    for c in children:
        if c.get("type") == "folder" and c.get("name") == IMPORT_FOLDER:
            folder = c
    if folder is None:
        folder = {"type": "folder", "name": IMPORT_FOLDER, "children": []}
        children.append(folder)
    existing = {c.get("url") for c in folder.get("children", [])
                if c.get("type") == "url"}
    added = 0
    for r in rows:
        if r["url"] in existing:
            continue
        folder["children"].append({"type": "url",
                                   "name": r.get("title", ""),
                                   "url": r["url"]})
        existing.add(r["url"])
        added += 1
    roots.setdefault("other", {"type": "folder", "name": "Other bookmarks",
                               "children": []})
    roots.setdefault("synced", {"type": "folder", "name": "Mobile bookmarks",
                                "children": []})
    data["version"] = 1
    data.pop("checksum", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return added


def write_chromium_history(rows: list, profile_dir: str) -> int:
    os.makedirs(profile_dir, exist_ok=True)
    path = os.path.join(profile_dir, "History")
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS urls (id INTEGER PRIMARY KEY,
            url LONGVARCHAR, title LONGVARCHAR,
            visit_count INTEGER DEFAULT 0, typed_count INTEGER DEFAULT 0,
            last_visit_time INTEGER, hidden INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS visits (id INTEGER PRIMARY KEY,
            url INTEGER, visit_time INTEGER, from_visit INTEGER,
            transition INTEGER DEFAULT 805306376, segment_id INTEGER,
            visit_duration INTEGER DEFAULT 0,
            incremented_omnibox_typed_score INTEGER DEFAULT 0);
    """)
    added = 0
    for r in rows:
        ts = _unix_to_chrome_ts(r.get("ts", 0))
        cur = con.execute(
            "INSERT INTO urls (url, title, visit_count, last_visit_time, hidden) "
            "VALUES (?,?,1,?,0)", (r["url"], r.get("title", ""), ts))
        con.execute(
            "INSERT INTO visits (url, visit_time, from_visit, segment_id) "
            "VALUES (?,?,0,0)", (cur.lastrowid, ts))
        added += 1
    con.commit()
    con.close()
    return added


def _v10_encrypt(plaintext: str) -> bytes:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=_V10_SALT,
                     iterations=1)
    key = kdf.derive(b"peanuts")
    padder = padding.PKCS7(128).padder()
    data = padder.update(plaintext.encode()) + padder.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(_V10_IV)).encryptor()
    return b"v10" + enc.update(data) + enc.finalize()


def _v10_decrypt(blob: bytes) -> str:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    if not blob.startswith(b"v10"):
        return ""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=_V10_SALT,
                     iterations=1)
    key = kdf.derive(b"peanuts")
    dec = Cipher(algorithms.AES(key), modes.CBC(_V10_IV)).decryptor()
    data = dec.update(blob[3:]) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plain = unpadder.update(data) + unpadder.finalize()
    return plain.decode(errors="replace")


def write_chromium_passwords(rows: list, default_dir: str) -> int:
    """Best-effort: writes Chromium's ``Login Data`` store (v10 format).
    Some builds may still ask for one re-login; import is never a security
    boundary. No secret value is ever logged."""
    os.makedirs(default_dir, exist_ok=True)
    path = os.path.join(default_dir, "Login Data")
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS logins (origin_url TEXT NOT NULL,
            action_url TEXT, username_element TEXT, username_value TEXT,
            password_element TEXT, password_value BLOB, submit_element TEXT,
            signon_realm TEXT NOT NULL, date_created INTEGER NOT NULL,
            blacklisted_by_user INTEGER DEFAULT 0, scheme INTEGER DEFAULT 0,
            password_type INTEGER DEFAULT 0, times_used INTEGER DEFAULT 0);
    """)
    now = int(time.time() * 1_000_000) + CHROME_EPOCH_OFFSET * 1_000_000
    added = 0
    for r in rows:
        con.execute(
            "INSERT INTO logins (origin_url, action_url, username_value, "
            "password_value, signon_realm, date_created) VALUES (?,?,?,?,?,?)",
            (r["origin"], r["origin"], r.get("username", ""),
             _v10_encrypt(r.get("password", "")), r["origin"] + "/", now))
        added += 1
    con.commit()
    con.close()
    return added


def read_chromium_passwords(default_dir: str) -> list:
    path = os.path.join(default_dir, "Login Data")
    if not os.path.isfile(path):
        return []
    tmp = path + ".mig-copy"
    shutil.copyfile(path, tmp)
    try:
        con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT origin_url, username_value, password_value FROM logins"
        ).fetchall()
        con.close()
    finally:
        os.remove(tmp)
    return [{"origin": o, "username": u, "password": _v10_decrypt(p or b"")}
            for o, u, p in rows]


# ---------- orchestration ----------

def detect_sources(home: Optional[str] = None) -> dict:
    home = home or os.environ.get("MIGRATE_HOME") or os.path.expanduser("~")
    chromium: list = []
    for name, rel in CHROMIUM_ROOTS:
        root = os.path.join(home, rel.split("~/", 1)[-1])
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            p = os.path.join(root, entry)
            if os.path.isdir(p) and (os.path.isfile(os.path.join(p, "Bookmarks"))
                                     or os.path.isfile(os.path.join(p, "History"))):
                chromium.append((name, p))
    firefox: list = []
    ffroot = os.path.join(home, ".mozilla", "firefox")
    if os.path.isdir(ffroot):
        for entry in sorted(os.listdir(ffroot)):
            p = os.path.join(ffroot, entry)
            if os.path.isdir(p) and os.path.isfile(os.path.join(p, "places.sqlite")):
                firefox.append(p)
    return {"chromium": chromium, "firefox": firefox}


def migrate(profile_dir: str, home: Optional[str] = None,
            passwords_csv: Optional[str] = None,
            extra_files: Optional[list] = None) -> dict:
    """One-call migration into Pergel's ``profile_dir`` (the Default dir's
    parent, i.e. the Chromium user-data dir). Returns COUNTS only."""
    default_dir = os.path.join(profile_dir, "Default")
    os.makedirs(default_dir, exist_ok=True)
    bookmarks: list = []
    history: list = []
    for _name, src in detect_sources(home)["chromium"]:
        bookmarks += import_chromium_bookmarks(src)
        history += import_chromium_history(src)
    for src in detect_sources(home)["firefox"]:
        history += import_firefox_places(src)
    for f in extra_files or []:
        if f.endswith(".html") or f.endswith(".htm"):
            bookmarks += import_netscape_html(f)
        elif f.endswith(".json"):
            bookmarks += import_firefox_bookmarks_json(f)
        elif f.endswith(".csv"):
            bookmarks += import_csv(f)
    # dedupe
    seen = set()
    bookmarks = [b for b in bookmarks
                 if not (b["url"] in seen or seen.add(b["url"]))]
    passwords = import_passwords_csv(passwords_csv) if passwords_csv else []
    return {
        "bookmarks": write_chromium_bookmarks(bookmarks, default_dir),
        "history": write_chromium_history(history, profile_dir),
        "passwords": write_chromium_passwords(passwords, default_dir),
    }
