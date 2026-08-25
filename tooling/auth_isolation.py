#!/usr/bin/env python3
"""Shared-server auth/isolation primitives — R18 (master-ranking rank 18, C7/L55).

Structural enforcement, never advisory:
  * Launcher-minted OPAQUE bearer tokens (secrets.token_urlsafe(32)); the
    sqlite token table stores sha256 HASHES only — plaintext never persists.
    Timing-safe comparison is unnecessary by construction: tokens are
    256-bit random values with no low-entropy prefix to oracle.
  * Graph reads go through open_readonly(): SQLITE_OPEN_READONLY URI connect
    + PRAGMA query_only=ON + a set_authorizer hook denying every statement
    class except SELECT (two independent walls behind the URI flag).
  * require_token() wraps handlers with Authorization: Bearer verification.

Deployment-side blast-radius wall (owner-applied systemd unit notes):
  [Service]
  DynamicUser=yes
  MemoryMax=4G                              # guards the 3072 MiB host floor
  PrivateTmp=yes
  RestrictAddressFamilies=AF_UNIX AF_INET   # loopback posture only
OAuth/OIDC stays deferred per C7 until any egress requirement appears.
"""

import functools
import hashlib
import os
import secrets
import sqlite3
import time

TOKEN_BYTES = 32

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    token_hash TEXT PRIMARY KEY,
    created    TEXT NOT NULL,
    last_used  TEXT,
    scopes     TEXT NOT NULL DEFAULT 'read'
)
"""


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class TokenStore:
    """Launcher-side token registry (own read-write connection).

    `db_path` defaults to :memory: — the launcher typically keeps tokens for
    the server process lifetime only; pass a path to persist across restarts.
    """

    def __init__(self, db_path=":memory:"):
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)

    def mint(self, scopes="read"):
        """Create one opaque token; plaintext is returned exactly once."""
        token = secrets.token_urlsafe(TOKEN_BYTES)
        scope_csv = ",".join(scopes) if isinstance(scopes, (list, tuple)) else scopes
        self._conn.execute(
            "INSERT INTO tokens (token_hash, created, scopes) VALUES (?, ?, ?)",
            (_hash(token), _now(), scope_csv))
        self._conn.commit()
        return token

    def verify(self, token, scope="read"):
        """True iff the hash exists and (when given) scope is granted."""
        row = self._conn.execute(
            "SELECT scopes FROM tokens WHERE token_hash = ?",
            (_hash(token),)).fetchone()
        if row is None:
            return False
        self._conn.execute("UPDATE tokens SET last_used = ? WHERE token_hash = ?",
                           (_now(), _hash(token)))
        self._conn.commit()
        return scope is None or scope in row[0].split(",")

    def close(self):
        self._conn.close()


def _bearer(request):
    headers = {str(k).lower(): v for k, v in (request.get("headers") or {}).items()}
    scheme, _, value = str(headers.get("authorization", "")).partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def require_token(store, scope="read"):
    """Decorator: handler(request, ...) runs only on a valid bearer token;
    otherwise raises PermissionError('unauthorized')."""
    def decorate(fn):
        @functools.wraps(fn)
        def guarded(request, *args, **kwargs):
            supplied = _bearer(request)
            if not supplied or not store.verify(supplied, scope):
                raise PermissionError("unauthorized")
            return fn(request, *args, **kwargs)
        return guarded
    return decorate


def install_select_authorizer(conn):
    """Deny every statement class except plain SELECTs on `conn`."""
    def _deny_except_select(action, arg1, arg2, db_name, trigger):
        # A read path needs only: SQLITE_SELECT (statement), SQLITE_READ
        # (column access inside the select), SQLITE_FUNCTION (scalar fn use).
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                      sqlite3.SQLITE_FUNCTION):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY
    conn.set_authorizer(_deny_except_select)


def open_readonly(path):
    """Read-only connection to a graph store: ro-URI connect + query_only
    pragma + SELECT-only authorizer. (Paths containing '?'/'#' would need
    percent-encoding; corpus layout never produces those.)"""
    if path == ":memory:":
        conn = sqlite3.connect(path)
    else:
        conn = sqlite3.connect("file:" + os.path.abspath(path) + "?mode=ro",
                               uri=True)                 # SQLITE_OPEN_READONLY
    conn.execute("PRAGMA query_only = ON")               # wall 2: parser level
    install_select_authorizer(conn)                      # wall 3: stmt level
    return conn
