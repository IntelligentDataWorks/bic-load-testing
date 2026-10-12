"""Background process management for test runs.

Responsibilities:

* run a test as a detached child process so the Streamlit script can keep
  rerunning while it executes;
* stream stdout+stderr into an in-memory ring buffer *and* a per-run log file,
  redacting secrets on the way through;
* stop a single run -- and only that run -- including its whole child tree;
* express a combined run (Locust load with a Playwright journey layered on it)
  as one run id with two child processes.

Stopping prefers a graceful interrupt so Locust still writes its CSV/HTML
report, and only escalates to a hard tree kill if the child ignores it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import psutil

from control_centre.models import RunStatus
from control_centre.paths import PROJECT_ROOT
from control_centre.redaction import preview_command, redact
from control_centre.runs import RunManifest, log_path, run_dir

IS_WINDOWS = os.name == "nt"
GRACEFUL_STOP_SECONDS = 20
MAX_LOG_LINES = 5000


@dataclass
class Step:
    """One child process inside a run."""

    name: str
    argv: list[str]
    env: dict[str, str]
    cwd: Path = PROJECT_ROOT
    timeout_seconds: int | None = None
    # Non-zero exit does not fail the run (used for the Locust half of a combined
    # run, which is intentionally interrupted once the UI journey finishes).
    tolerate_failure: bool = False


@dataclass
class StepResult:
    name: str
    exit_code: int | None = None
    timed_out: bool = False
    cancelled: bool = False
    error: str = ""


@dataclass
class ManagedRun:
    """Live state of one run. Read by the UI on every rerun."""

    manifest: RunManifest
    steps: list[Step]
    supervisor: Callable[["ManagedRun"], None]
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    results: list[StepResult] = field(default_factory=list)
    _processes: dict[str, subprocess.Popen[str]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _stop_requested: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _log_file: Path | None = None

    # ---- log ---------------------------------------------------------------

    def log(self, message: str, prefix: str = "control-centre") -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] [{prefix}] {redact(message)}"
        with self._lock:
            self.lines.append(line)
            if self._log_file is not None:
                try:
                    with self._log_file.open("a", encoding="utf-8") as handle:
                        handle.write(line + "\n")
                except OSError:
                    pass

    def tail(self, count: int = 400) -> list[str]:
        with self._lock:
            if count >= len(self.lines):
                return list(self.lines)
            return list(self.lines)[-count:]

    # ---- status ------------------------------------------------------------

    @property
    def status(self) -> RunStatus:
        return self.manifest.status_enum

    @property
    def is_running(self) -> bool:
        return self.status is RunStatus.RUNNING

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    @property
    def elapsed_seconds(self) -> float | None:
        return self.manifest.duration_seconds

    # ---- process control ---------------------------------------------------

    def _spawn(self, step: Step) -> subprocess.Popen[str]:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
        popen = subprocess.Popen(  # noqa: S603 - argv list, shell=False by construction
            step.argv,
            cwd=str(step.cwd),
            env=step.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
            creationflags=creationflags,
            start_new_session=not IS_WINDOWS,
        )
        with self._lock:
            self._processes[step.name] = popen
        return popen

    def _pump(self, step_name: str, popen: subprocess.Popen[str]) -> None:
        assert popen.stdout is not None
        try:
            for raw in popen.stdout:
                self.log(raw.rstrip("\r\n"), prefix=step_name)
        except (OSError, ValueError):
            pass

    def run_step(self, step: Step) -> StepResult:
        """Launch one step, stream its output, and wait for it to finish."""
        result = StepResult(name=step.name)
        self.log(f"$ {preview_command(step.argv)}", prefix=step.name)
        try:
            popen = self._spawn(step)
        except OSError as exc:
            result.error = str(exc)
            self.log(f"failed to start: {exc}", prefix=step.name)
            return result

        pump = threading.Thread(target=self._pump, args=(step.name, popen), daemon=True)
        pump.start()

        deadline = time.monotonic() + step.timeout_seconds if step.timeout_seconds else None
        while True:
            try:
                result.exit_code = popen.wait(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                pass
            if self._stop_requested.is_set():
                self.log("stop requested -- interrupting", prefix=step.name)
                self._terminate(popen, step.name)
                result.exit_code = popen.wait()
                result.cancelled = True
                break
            if deadline is not None and time.monotonic() > deadline:
                self.log(
                    f"hard timeout after {step.timeout_seconds}s -- interrupting", prefix=step.name
                )
                self._terminate(popen, step.name)
                result.exit_code = popen.wait()
                result.timed_out = True
                break

        pump.join(timeout=5)
        with self._lock:
            self._processes.pop(step.name, None)
        self.log(f"exit code {result.exit_code}", prefix=step.name)
        self.results.append(result)
        return result

    def _terminate(self, popen: subprocess.Popen[str], step_name: str) -> None:
        """Graceful interrupt first (so Locust flushes its report), then a tree kill."""
        if popen.poll() is not None:
            return
        try:
            if IS_WINDOWS:
                os.kill(popen.pid, signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(popen.pid), signal.SIGINT)
        except (OSError, ProcessLookupError, ValueError) as exc:
            self.log(f"graceful interrupt unavailable ({exc}); killing tree", prefix=step_name)

        waited = 0.0
        while waited < GRACEFUL_STOP_SECONDS:
            if popen.poll() is not None:
                return
            time.sleep(0.5)
            waited += 0.5
        self.log("still running after graceful stop -- killing process tree", prefix=step_name)
        kill_process_tree(popen.pid)

    def request_stop(self) -> None:
        self._stop_requested.set()
        self.log("stop requested by user")
        with self._lock:
            processes = list(self._processes.items())
        for name, popen in processes:
            self._terminate(popen, name)

    def active_pids(self) -> list[int]:
        with self._lock:
            return [p.pid for p in self._processes.values() if p.poll() is None]


def kill_process_tree(pid: int, timeout: float = 10.0) -> None:
    """Terminate ``pid`` and every descendant -- and nothing else."""
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    try:
        victims = parent.children(recursive=True) + [parent]
    except psutil.NoSuchProcess:
        return
    for proc in victims:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    _, alive = psutil.wait_procs(victims, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


# --------------------------------------------------------------------------
# Supervisors
# --------------------------------------------------------------------------


def sequential_supervisor(run: ManagedRun) -> None:
    """Run every step in order; stop early on failure or cancellation."""
    for step in run.steps:
        if run.stop_requested:
            break
        result = run.run_step(step)
        if result.cancelled or result.timed_out:
            break
        if result.exit_code not in (0, None) and not step.tolerate_failure:
            break


def make_combined_supervisor(warmup_seconds: int, stop_locust_after_ui: bool) -> Callable[[ManagedRun], None]:
    """Locust first, then the Playwright journey while the load is live.

    ``run.steps`` must be exactly ``[locust_step, playwright_step]``.
    """

    def supervisor(run: ManagedRun) -> None:
        locust_step, playwright_step = run.steps[0], run.steps[1]
        locust_result = StepResult(name=locust_step.name)

        def run_locust() -> None:
            nonlocal locust_result
            locust_result = run.run_step(locust_step)

        locust_thread = threading.Thread(target=run_locust, daemon=True)
        locust_thread.start()

        run.log(f"warming up load for {warmup_seconds}s before the UI journey starts")
        waited = 0.0
        while waited < warmup_seconds and not run.stop_requested:
            time.sleep(0.5)
            waited += 0.5

        if not run.stop_requested:
            run.log("warm-up complete -- starting the Playwright journey under load")
            run.run_step(playwright_step)

        if stop_locust_after_ui and not run.stop_requested:
            run.log("UI journey finished -- interrupting Locust so it writes its report")
            with run._lock:  # noqa: SLF001 - same module, deliberate
                popen = run._processes.get(locust_step.name)  # noqa: SLF001
            if popen is not None:
                run._terminate(popen, locust_step.name)  # noqa: SLF001
        else:
            run.log("waiting for the Locust run to finish on its own schedule")

        locust_thread.join()

    return supervisor


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


class RunRegistry:
    """Process-wide registry of runs. One instance per Streamlit server."""

    def __init__(self) -> None:
        self._runs: dict[str, ManagedRun] = {}
        self._lock = threading.RLock()

    def start(
        self,
        manifest: RunManifest,
        steps: Iterable[Step],
        supervisor: Callable[[ManagedRun], None] = sequential_supervisor,
    ) -> ManagedRun:
        """Register and launch a run. Raises if another run is already active."""
        step_list = list(steps)
        with self._lock:
            active = self.active_runs()
            if active:
                raise RuntimeError(
                    f"A run is already active ({active[0].manifest.run_id}). "
                    "Stop it before starting another."
                )
            if manifest.run_id in self._runs:
                raise RuntimeError(f"Run {manifest.run_id} has already been started.")

            directory = run_dir(manifest.run_id, create=True)
            run = ManagedRun(manifest=manifest, steps=step_list, supervisor=supervisor)
            run._log_file = directory / log_path(manifest.run_id).name  # noqa: SLF001
            manifest.redacted_commands = [preview_command(step.argv) for step in step_list]
            manifest.redacted_command = manifest.redacted_commands[0] if step_list else ""
            manifest.mark_started()
            manifest.save()
            self._runs[manifest.run_id] = run

        run.log(f"run {manifest.run_id} started ({manifest.kind}) against {manifest.environment}")
        thread = threading.Thread(target=self._supervise, args=(run,), daemon=True, name=f"run-{manifest.run_id}")
        run._thread = thread  # noqa: SLF001
        thread.start()
        return run

    def _supervise(self, run: ManagedRun) -> None:
        try:
            run.supervisor(run)
        except Exception as exc:  # noqa: BLE001 - surfaced in the run log and status
            run.log(f"supervisor error: {exc}")
            run.manifest.mark_finished(RunStatus.ERROR, None)
            run.manifest.save()
            return
        run.manifest.mark_finished(*self._final_status(run))
        run.manifest.save()
        run.log(f"run finished with status {run.manifest.status}")

    @staticmethod
    def _final_status(run: ManagedRun) -> tuple[RunStatus, int | None]:
        relevant = [r for r in run.results if not _tolerated(run, r)]
        exit_code = next((r.exit_code for r in relevant if r.exit_code not in (0, None)), 0)
        if any(r.cancelled for r in run.results) or run.stop_requested:
            return RunStatus.CANCELLED, exit_code
        if any(r.timed_out for r in run.results):
            return RunStatus.TIMED_OUT, exit_code
        if any(r.error for r in run.results):
            return RunStatus.ERROR, exit_code
        if not run.results:
            return RunStatus.ERROR, None
        return (RunStatus.PASSED, 0) if exit_code == 0 else (RunStatus.FAILED, exit_code)

    def get(self, run_id: str) -> ManagedRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def all_runs(self) -> list[ManagedRun]:
        with self._lock:
            return list(self._runs.values())

    def active_runs(self) -> list[ManagedRun]:
        return [r for r in self.all_runs() if r.is_running]

    def stop(self, run_id: str) -> bool:
        run = self.get(run_id)
        if run is None or not run.is_running:
            return False
        run.request_stop()
        return True

    def stop_all(self) -> int:
        stopped = 0
        for run in self.active_runs():
            run.request_stop()
            stopped += 1
        return stopped


def _tolerated(run: ManagedRun, result: StepResult) -> bool:
    step = next((s for s in run.steps if s.name == result.name), None)
    return bool(step and step.tolerate_failure)


def run_blocking(argv: list[str], env: dict[str, str] | None = None, timeout: int = 120) -> tuple[int, str]:
    """Small helper for quick, non-test commands (version probes, report opening).

    Output is redacted before it is returned to the caller.
    """
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, shell=False
            argv,
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as exc:
        return 127, str(exc)
    return proc.returncode, redact((proc.stdout or "") + (proc.stderr or ""))


def spawn_detached(argv: list[str], env: dict[str, str] | None = None) -> int | None:
    """Launch a long-lived helper (report server, codegen) without waiting for it."""
    try:
        popen = subprocess.Popen(  # noqa: S603 - argv list, shell=False
            argv,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            shell=False,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0,
            start_new_session=not IS_WINDOWS,
        )
    except OSError:
        return None
    return popen.pid


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
