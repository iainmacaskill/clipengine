"""Minimal Twitch IRC chat reader (anonymous, read-only).

Twitch serves live chat over IRC at irc.chat.twitch.tv; anonymous read access
uses a ``justinfan``-prefixed nick with no auth. This is the same live signal
the offline detector consumes from chat replays, arriving in real time.
"""
from __future__ import annotations

import socket
import time
from collections.abc import Iterator

HOST = "irc.chat.twitch.tv"
PORT = 6667
ANON_NICK = "justinfan826774"  # any justinfan* nick is accepted for read-only access


def parse_privmsg(line: str) -> tuple[str, str] | None:
    """Parse an IRC PRIVMSG line -> (user, message text), else None."""
    if " PRIVMSG #" not in line:
        return None
    prefix, _, rest = line.partition(" PRIVMSG #")
    user = prefix.lstrip(":").split("!")[0]
    _, _, text = rest.partition(" :")
    return user, text.rstrip("\r\n")


def chat_messages(
    channel: str,
    sock=None,
    clock=time.time,
) -> Iterator[tuple[float, str, str]]:
    """Yield (timestamp, user, text) for a channel's live chat, forever.

    ``sock`` is injectable for tests; the default connects to Twitch IRC.
    Handles PING keepalives. The caller is responsible for reconnecting if
    the generator ends (connection closed).
    """
    channel = channel.strip().lower().lstrip("#")
    own_sock = sock is None
    if sock is None:
        sock = socket.create_connection((HOST, PORT), timeout=360)
    try:
        sock.sendall(f"NICK {ANON_NICK}\r\n".encode())
        sock.sendall(f"JOIN #{channel}\r\n".encode())
        buffer = b""
        while True:
            data = sock.recv(4096)
            if not data:
                return
            buffer += data
            while b"\r\n" in buffer:
                raw, _, buffer = buffer.partition(b"\r\n")
                line = raw.decode("utf-8", errors="replace")
                if line.startswith("PING"):
                    sock.sendall(("PONG" + line[4:] + "\r\n").encode())
                    continue
                parsed = parse_privmsg(line)
                if parsed:
                    yield clock(), parsed[0], parsed[1]
    finally:
        if own_sock:
            sock.close()
