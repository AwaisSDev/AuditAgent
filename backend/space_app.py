"""Entry point for running the backend as a Hugging Face *Gradio* Space.

Docker Spaces are paid; Gradio Spaces are free but only run one Python file.
So this file does what start.sh does for containers: it starts Redis and the
arq worker as subprocesses, then serves the API on the Space's port.

Gradio owns the server. ZeroGPU Spaces expect the app to come up through
Blocks.launch() and tear the container down otherwise, so the one-screen
status page is launched normally and the FastAPI app is attached to
Gradio's server: anything Gradio doesn't handle (/healthz, /v1/..., /docs)
falls through to the API, middleware included.

Locally you would never run this; use uvicorn + run_worker.py.
"""

# On ZeroGPU Spaces, `spaces` must be imported before anything touches
# torch/CUDA (spaCy's backend imports torch when it is installed), or
# Gradio's reload watcher fails at startup. Not installed elsewhere.
try:
    import spaces  # noqa: F401
except ImportError:
    pass

import atexit
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import gradio as gr
import gradio.http_server

# On Spaces, Gradio starts a dev-only hot-reload watcher that scans every
# loaded Python object; it trips over lazy imports in third-party SDKs.
# Nothing here needs reloading, so make the watcher a no-op.
gradio.http_server.watchfn_spaces = lambda reloader: None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "7860"))
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379")


def _port_in_use(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


# Some Space runtimes execute the entry file more than once. If another
# instance already serves the port, this one just stays alive so the
# container isn't torn down, instead of fighting over Redis and the port.
if _port_in_use(PORT):
    print(f"[space_app] port {PORT} already served by another instance; idling", file=sys.stderr)
    while True:
        time.sleep(3600)

_procs: list[subprocess.Popen] = []


def _start(cmd: list[str]) -> None:
    try:
        _procs.append(subprocess.Popen(cmd, cwd=HERE))
    except FileNotFoundError:
        # Keep the API up even if a helper is missing (e.g. no redis-server
        # locally); the Space logs will show which one.
        print(f"[space_app] could not start {cmd[0]!r}: not found", file=sys.stderr)


# Redis is only a job queue (durable state lives in Supabase): no persistence,
# no pid file, nothing that needs root.
_start(["redis-server", "--save", "", "--appendonly", "no", "--bind", "127.0.0.1",
        "--port", "6379", "--loglevel", "warning", "--pidfile", ""])
_start([sys.executable, str(HERE / "run_worker.py")])
atexit.register(lambda: [p.terminate() for p in _procs])

from app.main import app as api  # noqa: E402  (after REDIS_URL is set)

with gr.Blocks(title="AuditAgent API") as status:
    gr.Markdown(
        "# AuditAgent API\n"
        "This Space hosts the AuditAgent backend (API + worker).\n\n"
        "Health: [/healthz](healthz) · OpenAPI: [/docs](docs)"
    )

if __name__ == "__main__":
    # ssr_mode=False: Gradio's SSR mode would start a Node front-end on this
    # port and move Python elsewhere, which the platform's port check dislikes.
    gradio_app, _, _ = status.launch(
        server_name="0.0.0.0",
        server_port=PORT,
        prevent_thread_lock=True,
        ssr_mode=False,
        quiet=True,
    )
    gradio_app.mount("/", api)
    status.block_thread()
