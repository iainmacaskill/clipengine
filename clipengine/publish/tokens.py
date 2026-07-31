"""OAuth token persistence shared by the publishing clients.

Each platform account gets a JSON token file holding the current access token,
its expiry, and the long-lived refresh token. Clients call ``valid_access_token``
which transparently refreshes when the access token is stale.
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: float  # unix epoch seconds

    @property
    def expired(self) -> bool:
        return time.time() > self.expires_at - 60  # refresh a minute early


class TokenStore:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> TokenSet | None:
        if not os.path.exists(self.path):
            return None
        with open(self.path) as f:
            return TokenSet(**json.load(f))

    def save(self, tokens: TokenSet) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(asdict(tokens), f)


def valid_access_token(
    store: TokenStore, refresh: Callable[[str], TokenSet]
) -> str:
    """Return a live access token, refreshing (and persisting) if needed.

    ``refresh`` receives the current refresh token and must return a new TokenSet
    (platforms that rotate refresh tokens return the new one; keep it).
    """
    tokens = store.load()
    if tokens is None:
        raise RuntimeError(
            f"no tokens at {store.path} - run the matching 'clipengine auth' command first"
        )
    if tokens.expired:
        tokens = refresh(tokens.refresh_token)
        store.save(tokens)
    return tokens.access_token
