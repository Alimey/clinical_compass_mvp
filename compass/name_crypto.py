"""Шифрование имён и служебных копий с отдельным ключом хранения."""

import argparse
import base64
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import time

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app

PREFIX = "pcenc:v1:"
NAME_COLUMNS = {
    "name",
    "patient_name",
    "doctor_name",
    "sender_name",
    "actor_name",
    "author",
}
FIELDS = (
    ("users", "id", "name", "name"),
    ("notifications", "id", "body", "notice"),
    ("telegram_sessions", "chat_id", "data_json", "intake"),
    ("telegram_outbox", "id", "body", "outbox"),
    ("idempotency", "rowid", "response", "cache"),
)


class NameEncryptionError(RuntimeError):
    pass


class NameCipher:
    def __init__(self, key):
        try:
            self.master = base64.urlsafe_b64decode(key)
            if len(self.master) != 32:
                raise ValueError()
        except (ValueError, TypeError):
            raise NameEncryptionError(
                "COMPASS_NAME_KEY должен быть ключом Fernet из 32 байт в URL-safe Base64"
            ) from None
        self.ciphers = {}

    def cipher(self, purpose):
        if purpose not in self.ciphers:
            derived = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=("psicompass/storage/v1/" + purpose).encode(),
            ).derive(self.master)
            self.ciphers[purpose] = Fernet(base64.urlsafe_b64encode(derived))
        return self.ciphers[purpose]

    def seal(self, value, purpose):
        if not isinstance(value, str):
            raise TypeError("Защищённое поле должно содержать текст")
        return (
            PREFIX
            + purpose
            + ":"
            + self.cipher(purpose).encrypt(value.encode("utf-8")).decode("ascii")
        )

    def open(self, value, purpose):
        if not isinstance(value, str) or not value.startswith(PREFIX):
            return value
        prefix = PREFIX + purpose + ":"
        try:
            if not value.startswith(prefix):
                raise InvalidToken()
            return (
                self.cipher(purpose)
                .decrypt(value[len(prefix) :].encode("ascii"))
                .decode("utf-8")
            )
        except (InvalidToken, UnicodeError, ValueError):
            raise NameEncryptionError(
                "Не удалось расшифровать защищённое поле. Проверьте ключ хранения"
            ) from None


def seal(value, purpose="name"):
    return current_app.extensions["name_cipher"].seal(value, purpose)


def unseal(value, purpose="name"):
    return current_app.extensions["name_cipher"].open(value, purpose)


def name_row_factory(cursor, values):
    decoded = tuple(
        unseal(value) if column[0] in NAME_COLUMNS else value
        for column, value in zip(cursor.description, values)
    )
    return sqlite3.Row(cursor, decoded)


def _existing_state(database):
    if not database.is_file():
        return None, False
    with closing(sqlite3.connect(database)) as con:
        tables = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        state = (
            con.execute(
                "SELECT value FROM name_encryption_state WHERE key='key_check'"
            ).fetchone()
            if "name_encryption_state" in tables
            else None
        )
        encrypted = (
            bool(
                con.execute(
                    "SELECT 1 FROM users WHERE name LIKE ? LIMIT 1", (PREFIX + "%",)
                ).fetchone()
            )
            if "users" in tables
            else False
        )
    return state[0] if state else None, encrypted


def init_name_cipher(app):
    database = Path(app.config["DATABASE"]).resolve()
    state, encrypted = _existing_state(database)
    key = os.environ.get("COMPASS_NAME_KEY", "").strip()
    key_path = Path(
        os.environ.get("COMPASS_NAME_KEY_FILE") or database.parent / "patient-names.key"
    )
    if not key:
        if not key_path.exists():
            if state or encrypted:
                raise NameEncryptionError(
                    "Ключ имён отсутствует. Восстановите patient-names.key или задайте COMPASS_NAME_KEY; новый ключ не подходит к этой базе"
                )
            key_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(
                    key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(Fernet.generate_key())
                    output.flush()
                    os.fsync(output.fileno())
        # A second startup may see the exclusively created file just before its write.
        for _ in range(50):
            try:
                key = key_path.read_text(encoding="ascii").strip()
            except (OSError, UnicodeError):
                raise NameEncryptionError(
                    "Не удалось прочитать файл ключа имён"
                ) from None
            if key:
                break
            time.sleep(0.02)
    store = NameCipher(key)
    if state and store.open(state, "check") != "psicompass-name-key-v1":
        raise NameEncryptionError("Ключ хранения не соответствует базе")
    if encrypted and not state:
        with closing(sqlite3.connect(database)) as con:
            value = con.execute(
                "SELECT name FROM users WHERE name LIKE ? LIMIT 1", (PREFIX + "%",)
            ).fetchone()[0]
            store.open(value, "name")
    app.extensions["name_cipher"] = store
    app.config["NAME_KEY_FILE"] = (
        str(key_path) if not os.environ.get("COMPASS_NAME_KEY", "").strip() else None
    )


def _encrypted_migration_backup(database, store):
    with closing(sqlite3.connect(database)) as source, closing(
        sqlite3.connect(":memory:")
    ) as target:
        source.backup(target)
        if hasattr(target, "serialize"):
            snapshot = target.serialize()
        else:
            # Python 3.10 has no serialize(); keep its snapshot in memory too.
            snapshot = b"psicompass-sqlite-dump-v1\n" + "\n".join(
                target.iterdump()
            ).encode("utf-8")
        encrypted = store.cipher("migration-backup").encrypt(snapshot)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = database.with_name(database.name + ".before-names-" + stamp + ".enc")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(encrypted)
        file.flush()
        os.fsync(file.fileno())
    return output.name


def restore_migration_backup(source, output, store):
    data = store.cipher("migration-backup").decrypt(Path(source).read_bytes())
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    dump_prefix = b"psicompass-sqlite-dump-v1\n"
    if data.startswith(dump_prefix):
        os.close(fd)
        try:
            with closing(sqlite3.connect(output)) as con:
                con.executescript(data[len(dump_prefix) :].decode("utf-8"))
        except Exception:
            Path(output).unlink(missing_ok=True)
            raise
    else:
        with os.fdopen(fd, "wb") as file:
            file.write(data)


def migrate_names():
    from compass.db import db

    con = db()
    con.commit()
    with con:
        con.execute("BEGIN IMMEDIATE")
        raw = con.cursor()
        raw.row_factory = None
        changes = []
        try:
            for table, primary, field, purpose in FIELDS:
                for ident, value in raw.execute(
                    f"SELECT {primary},{field} FROM {table}"
                ).fetchall():
                    if not isinstance(value, str):
                        continue
                    if value.startswith(PREFIX):
                        unseal(value, purpose)
                    else:
                        changes.append((table, primary, field, purpose, ident, value))
        finally:
            raw.close()
        backup = None
        if changes:
            backup = _encrypted_migration_backup(
                Path(current_app.config["DATABASE"]).resolve(),
                current_app.extensions["name_cipher"],
            )
        con.execute("PRAGMA secure_delete=ON")
        con.execute(
            "CREATE TABLE IF NOT EXISTS name_encryption_state(key TEXT PRIMARY KEY,value TEXT NOT NULL)"
        )
        for table, primary, field, purpose, ident, value in changes:
            con.execute(
                f"UPDATE {table} SET {field}=? WHERE {primary}=?",
                (seal(value, purpose), ident),
            )
        con.execute(
            "INSERT OR REPLACE INTO name_encryption_state VALUES('key_check',?)",
            (seal("psicompass-name-key-v1", "check"),),
        )
        if backup:
            con.execute(
                "INSERT OR REPLACE INTO name_encryption_state VALUES('migration_backup',?)",
                (backup,),
            )
        if changes:
            con.execute(
                "INSERT OR REPLACE INTO name_encryption_state VALUES('cleanup_pending','1')"
            )
    pending = con.execute(
        "SELECT value FROM name_encryption_state WHERE key='cleanup_pending'"
    ).fetchone()
    if changes or (pending and pending[0] == "1"):
        if con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
            raise NameEncryptionError(
                "Миграция записана; для очистки старых страниц остановите другие процессы приложения и повторите запуск"
            )
        con.execute("VACUUM")
        if con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
            raise NameEncryptionError(
                "Очистка журнала базы занята другим процессом; повторите запуск после его остановки"
            )
        with con:
            con.execute(
                "INSERT OR REPLACE INTO name_encryption_state VALUES('cleanup_pending','0')"
            )
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Print a new key; never use it to replace a key for an existing encrypted database",
    )
    parser.add_argument("--restore-backup", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    if args.generate_key:
        print(Fernet.generate_key().decode("ascii"))
        return
    if args.restore_backup and args.output:
        key = os.environ.get("COMPASS_NAME_KEY", "").strip() or (
            args.key_file.read_text(encoding="ascii").strip() if args.key_file else ""
        )
        restore_migration_backup(args.restore_backup, args.output, NameCipher(key))
        return
    parser.error("Use --generate-key or --restore-backup with --output and a key")


if __name__ == "__main__":
    main()
