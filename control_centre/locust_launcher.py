"""Thin launcher that runs Locust with a stoppable Windows console handler.

Why this exists: Locust writes its HTML report from the ``KeyboardInterrupt`` and
``SIGTERM`` paths in ``locust.main``. On Windows there is no way to send SIGTERM
to another process, and the only safe cross-process interrupt -- a
``CTRL_BREAK_EVENT`` sent to the child's own process group -- maps to ``SIGBREAK``,
whose default action kills the process outright (exit code 0xC000013A) before any
report is written.

Installing a ``SIGBREAK`` handler that raises ``KeyboardInterrupt`` puts the child
back on Locust's own graceful-shutdown path, so stopping a run from the control
centre still produces the CSV *and* HTML report.

It delegates to ``locust.main`` untouched -- argument parsing, configuration
discovery and behaviour are exactly the same as ``python -m locust``.
"""

from __future__ import annotations

import signal
import sys


def _raise_keyboard_interrupt(signum, frame):  # noqa: ANN001, ARG001 - signal handler signature
    raise KeyboardInterrupt


def main() -> None:
    # Importing locust applies gevent's monkey patching, which also wraps
    # signal.signal -- install the handler afterwards so it survives.
    from locust.main import main as locust_main

    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _raise_keyboard_interrupt)

    locust_main()


if __name__ == "__main__":
    sys.exit(main())
