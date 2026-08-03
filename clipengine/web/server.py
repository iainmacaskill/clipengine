"""stdlib HTTP server that routes to api.py and serves the static UI.

Deliberately dependency-free: a single-user local tool shouldn't pull in a web
framework. ThreadingHTTPServer handles the poll-while-a-job-runs pattern (the
job threads are separate from request threads). Bound to localhost only.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from ..config import Config
from . import api
from .jobs import JobRegistry
from .store import SourceStore

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class AppState:
    """Shared, thread-safe-enough handles for the handler (single process)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.jobs = JobRegistry()
        self.sources_path = api.sources_db_path(cfg)
        os.makedirs(os.path.dirname(self.sources_path) or ".", exist_ok=True)

    def sources(self) -> SourceStore:
        # a fresh connection per use - sqlite connections aren't shareable
        # across threads, and every request/job thread opens its own
        return SourceStore(self.sources_path)


# route table: (method, compiled-path) -> handler(state, match, body)
_ROUTES: list[tuple[str, re.Pattern, str]] = []


def route(method: str, pattern: str):
    def deco(fn):
        _ROUTES.append((method, re.compile(f"^{pattern}$"), fn.__name__))
        _HANDLERS[fn.__name__] = fn
        return fn
    return deco


_HANDLERS: dict = {}


# ---- routes ----------------------------------------------------------------


@route("GET", r"/api/campaigns")
def _list_campaigns(state, m, body):
    return api.list_campaigns(state.cfg)


@route("POST", r"/api/campaigns")
def _add_campaign(state, m, body):
    return api.add_campaign(state.cfg, body or {})


@route("GET", r"/api/campaigns/([^/]+)")
def _get_campaign(state, m, body):
    return api.get_campaign(state.cfg, m.group(1))


@route("GET", r"/api/campaigns/([^/]+)/sources")
def _list_sources(state, m, body):
    with _closing(state.sources()) as s:
        return api.list_sources(state.cfg, s, m.group(1))


@route("POST", r"/api/sources")
def _add_source(state, m, body):
    with _closing(state.sources()) as s:
        return api.add_source(state.cfg, s, body or {})


@route("POST", r"/api/sources/(\d+)/prepare")
def _prepare_source(state, m, body):
    job = state.jobs.create("prepare")
    fn = api.job_prepare_source(state.cfg, state.sources_path, int(m.group(1)))
    state.jobs.run(job, fn)
    return 202, job.to_dict()


@route("POST", r"/api/sources/(\d+)/detect")
def _detect_source(state, m, body):
    top = int((body or {}).get("top", 8))
    job = state.jobs.create("detect")
    fn = api.job_detect(state.cfg, state.sources_path, int(m.group(1)), top)
    state.jobs.run(job, fn)
    return 202, job.to_dict()


@route("POST", r"/api/render")
def _render(state, m, body):
    clips = (body or {}).get("clips") or []
    if not clips:
        return 400, {"error": "no clips to render"}
    job = state.jobs.create("render")
    fn = api.job_render(state.cfg, state.sources_path, clips)
    state.jobs.run(job, fn)
    return 202, job.to_dict()


@route("GET", r"/api/jobs/([^/]+)")
def _get_job(state, m, body):
    return api.get_job(state.jobs, m.group(1))


@route("GET", r"/api/submissions")
def _list_submissions(state, m, body):
    return api.list_submissions(state.cfg)


@route("POST", r"/api/submissions")
def _add_submission(state, m, body):
    return api.add_submission(state.cfg, body or {})


@route("GET", r"/api/presets")
def _presets(state, m, body):
    return api.list_presets()


# ---- helpers ---------------------------------------------------------------


class _closing:
    def __init__(self, store):
        self._store = store

    def __enter__(self):
        return self._store

    def __exit__(self, *exc):
        self._store.close()


def dispatch(state: AppState, method: str, path: str, body: dict | None):
    """Match a route and return (status, body). Public for tests."""
    for rmethod, pattern, handler_name in _ROUTES:
        if rmethod != method:
            continue
        match = pattern.match(path)
        if match:
            return _HANDLERS[handler_name](state, match, body)
    return 404, {"error": f"no route for {method} {path}"}


class _Handler(BaseHTTPRequestHandler):
    state: AppState = None  # set on the server instance's handler class

    def log_message(self, *args):  # quieter default logging
        pass

    def _send_json(self, status: int, payload: dict):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, path: str):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            self._send_json(404, {"error": "not found"})
            return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _path(self) -> str:
        # decode %3A etc and drop any query string; ids like "disc:frida"
        # arrive percent-encoded and must be matched/looked-up decoded
        return unquote(urlsplit(self.path).path)

    def do_GET(self):
        path = self._path()
        if path.startswith("/api/"):
            status, body = dispatch(self.state, "GET", path, None)
            self._send_json(status, body)
        else:
            self._serve_static(path)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return
        status, out = dispatch(self.state, "POST", self._path(), body)
        self._send_json(status, out)


def serve(cfg: Config, host: str = "127.0.0.1", port: int = 8765) -> None:
    state = AppState(cfg)
    handler = type("BoundHandler", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"Clip Studio running at {url}")
    print("Open that in your browser. Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
