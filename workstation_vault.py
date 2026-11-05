import base64
import csv
import json
import os
import secrets
import string
import uuid
from datetime import datetime

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "all-in-one-workstation")
VAULT_FILE = os.path.join(CONFIG_DIR, "vault.json")
# scrypt with 128 MiB of memory: about half a second per unlock, expensive to brute force offline.
KDF = {"name": "scrypt", "n": 2 ** 17, "r": 8, "p": 1}
FIELDS = ["name", "url", "username", "password", "totp", "notes", "folder"]
MIN_MASTER = 10


class VaultError(Exception):
    pass


def b64(data):
    return base64.b64encode(data).decode()


def unb64(text):
    return base64.b64decode(text)


def derive_key(master, salt, kdf):
    return Scrypt(salt=salt, length=32, n=kdf["n"], r=kdf["r"], p=kdf["p"]).derive(master.encode())


def generate_password(length=20):
    alphabet = string.ascii_letters + string.digits + "!@#$%&*-_=+?"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password) and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password) and any(c in "!@#$%&*-_=+?" for c in password)):
            return password


def new_entry(**fields):
    entry = {"id": uuid.uuid4().hex, **{f: "" for f in FIELDS}, **fields}
    entry["updated"] = datetime.now().isoformat(timespec="seconds")
    return entry


def read_lastpass_csv(path):
    """Entries from a LastPass export (url,username,password,totp,extra,name,grouping,fav)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if rows and "password" not in rows[0]:
        raise VaultError("This doesn't look like a LastPass CSV export")
    entries = []
    for row in rows:
        url = (row.get("url") or "").strip()
        if url == "http://sn":  # LastPass secure notes carry this placeholder URL
            url = ""
        name = (row.get("name") or "").strip() or url or (row.get("username") or "").strip()
        if not name and not row.get("password") and not row.get("extra"):
            continue
        entries.append(new_entry(name=name, url=url, username=(row.get("username") or "").strip(),
                                 password=row.get("password") or "", totp=(row.get("totp") or "").strip(),
                                 notes=row.get("extra") or "", folder=(row.get("grouping") or "").strip()))
    return entries


class Vault:
    def __init__(self, path=VAULT_FILE):
        self.path = path
        self.key = None
        self.salt = None
        self.entries = []

    def exists(self):
        return os.path.exists(self.path)

    @property
    def unlocked(self):
        return self.key is not None

    def create(self, master):
        if len(master) < MIN_MASTER:
            raise VaultError(f"The master password needs at least {MIN_MASTER} characters")
        self.salt = os.urandom(16)
        self.key = derive_key(master, self.salt, KDF)
        self.entries = []
        self.save()

    def unlock(self, master):
        with open(self.path) as f:
            blob = json.load(f)
        kdf = blob["kdf"]
        salt = unb64(blob["salt"])
        key = derive_key(master, salt, kdf)
        try:
            plain = AESGCM(key).decrypt(unb64(blob["nonce"]), unb64(blob["data"]), b"vault-v1")
        except InvalidTag as error:
            raise VaultError("Wrong master password") from error
        self.key, self.salt = key, salt
        self.entries = json.loads(plain)["entries"]

    def lock(self):
        self.key = None
        self.entries = []

    def save(self):
        if not self.unlocked:
            raise VaultError("The vault is locked")
        nonce = os.urandom(12)
        data = AESGCM(self.key).encrypt(nonce, json.dumps({"entries": self.entries}).encode(), b"vault-v1")
        blob = {"version": 1, "kdf": KDF, "salt": b64(self.salt), "nonce": b64(nonce), "data": b64(data)}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(blob, f)
        os.replace(tmp, self.path)

    def change_master(self, current, new):
        if len(new) < MIN_MASTER:
            raise VaultError(f"The master password needs at least {MIN_MASTER} characters")
        self.unlock(current)
        self.salt = os.urandom(16)
        self.key = derive_key(new, self.salt, KDF)
        self.save()

    def put(self, entry):
        entry["updated"] = datetime.now().isoformat(timespec="seconds")
        if entry not in self.entries:
            self.entries.append(entry)
        self.save()

    def delete(self, entry):
        self.entries.remove(entry)
        self.save()

    def import_entries(self, entries):
        """Add entries, skipping the ones already in the vault; returns how many were added."""
        known = {(e["name"], e["url"], e["username"], e["password"]) for e in self.entries}
        fresh = [e for e in entries if (e["name"], e["url"], e["username"], e["password"]) not in known]
        self.entries += fresh
        self.save()
        return len(fresh)

    def search(self, text):
        needle = text.strip().lower()
        found = [e for e in self.entries
                 if not needle or any(needle in e[f].lower() for f in ("name", "url", "username", "folder"))]
        return sorted(found, key=lambda e: (e["folder"].lower(), e["name"].lower()))
