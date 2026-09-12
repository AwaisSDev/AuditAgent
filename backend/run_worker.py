"""Runs the arq worker regardless of the process's actual working directory.

Running `python backend/run_worker.py` (from anywhere) puts this script's own
directory — backend/ — at the front of sys.path automatically, which is all
`import app...` needs. This exists only because arq has no `--app-dir`
equivalent to uvicorn's, and the launch-config tool has no `cwd` option.
"""

import logging.config

from arq.logs import default_log_config
from arq.worker import run_worker

from app.worker.worker_settings import WorkerSettings

if __name__ == "__main__":
    logging.config.dictConfig(default_log_config(verbose=True))
    run_worker(WorkerSettings)
