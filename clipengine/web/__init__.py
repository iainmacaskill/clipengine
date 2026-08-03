"""Local web UI: a thin, single-user shim over the existing Python API so the
campaign-to-clips workflow can be driven without a terminal (docs/ui/).

Nothing here re-implements pipeline logic - it calls campaigns/, pipeline,
submissions, and the gate directly, and serves a static page that talks to a
small JSON API. Kept dependency-free (stdlib http.server) so it installs and
runs on a laptop with no extra packages beyond what a render already needs.
"""
