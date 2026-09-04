from __future__ import annotations
import sqlite3
import time
from pathlib import Path
from .model import ControlRequest

class AuthError(RuntimeError):
    pass

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

class NonceStore:
    # Durable append-only replay protection; stores metadata only.
    def __init__(self, path, clock=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or time.time
        with self.connect() as db:
            db.executescript("""
CREATE TABLE IF NOT EXISTS used_nonce(
 nonce TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL,
 request_id TEXT NOT NULL UNIQUE, expires_at INTEGER NOT NULL, consumed_at INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS used_nonce_no_update BEFORE UPDATE ON used_nonce
BEGIN SELECT RAISE(ABORT,'append-only nonce store'); END;
CREATE TRIGGER IF NOT EXISTS used_nonce_no_delete BEFORE DELETE ON used_nonce
BEGIN SELECT RAISE(ABORT,'append-only nonce store'); END;
""")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        return db

    def consume(self, request: ControlRequest) -> None:
        now = int(self.clock())
        if request.expires_at < now:
            raise AuthError("expired control request")
        if request.expires_at - now > 600:
            raise AuthError("control request lifetime too long")
        try:
            with self.connect() as db:
                db.execute(
                    "INSERT INTO used_nonce VALUES(?,?,?,?,?)",
                    (request.nonce, request.owner_user_id, request.request_id, request.expires_at, now),
                )
                db.commit()
        except sqlite3.IntegrityError as exc:
            raise AuthError("replayed control request") from exc

class OwnerAuthenticator:
    def __init__(self, owner_user_id, guild_id, allowed_channels, nonce_store):
        if not owner_user_id or not guild_id or not allowed_channels:
            raise AuthError("owner authentication configuration incomplete")
        self.owner_user_id = str(owner_user_id)
        self.guild_id = str(guild_id)
        self.allowed_channels = frozenset(str(x) for x in allowed_channels)
        self.nonce_store = nonce_store

    def authorize(self, request: ControlRequest) -> ControlRequest:
        request.validate()
        if request.owner_user_id != self.owner_user_id:
            raise AuthError("unauthorized Discord user")
        if request.guild_id != self.guild_id:
            raise AuthError("unauthorized guild")
        if request.channel_id not in self.allowed_channels:
            raise AuthError("unauthorized channel")
        self.nonce_store.consume(request)
        return request
