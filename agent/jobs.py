"""Background job polling AND execution for Kits Direct Print Agent.

Previous version of this file only polled /jobs/pending and logged the
response - it explicitly did not ack, print, or complete/fail jobs
("Phase scope: poll for pending jobs and log/print them. Does NOT
ack/complete/fail or actually print anything yet."). That is the root
cause of "no print job reaches the printer": jobs were fetched from Odoo
but then simply discarded. This version implements the full lifecycle:

    poll -> ack -> print (PrintExecutor) -> complete/fail

Two threads are used:
  * _poll_loop   - polls /jobs/pending on POLL_INTERVAL and pushes each
                    job payload onto an internal queue.
  * _worker_loop - pulls jobs off that queue one at a time and executes
                    them, so a slow/stuck print job cannot block polling
                    (and so jobs are processed strictly in the order they
                    were received).
"""

import queue
import threading
from typing import Any, Callable, Dict, Optional

from api import OdooApiClient, ApiError
from config import ConfigManager
from logger import get_logger
from printer import PrintExecutor, PrintError

logger = get_logger(__name__)

POLL_INTERVAL = 5  # seconds
MAX_QUEUE_SIZE = 200


class JobManager:
    """Polls for pending jobs and executes them (ack -> print -> complete/fail)."""

    def __init__(
        self,
        client: OdooApiClient,
        config: ConfigManager,
        on_job_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_auth_failure: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.client = client
        self.config = config
        self.on_job_event = on_job_event
        self.on_auth_failure = on_auth_failure
        self.executor = PrintExecutor()

        self._job_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        self._seen_job_ids: set = set()
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._worker_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.is_running():
            logger.info("Job manager already running, ignoring start()")
            return
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._poll_thread.start()
        self._worker_thread.start()
        logger.info("Job manager started (poll + worker threads)")

    def stop(self) -> None:
        self._stop_event.set()
        for t in (self._poll_thread, self._worker_thread):
            if t and t is not threading.current_thread():
                t.join(timeout=3)
        logger.info("Job manager stopped")

    def is_running(self) -> bool:
        return bool(
            (self._poll_thread and self._poll_thread.is_alive())
            or (self._worker_thread and self._worker_thread.is_alive())
        )

    def queue_size(self) -> int:
        return self._job_queue.qsize()

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            jwt_token = self.config.get("jwt", "")

            if not jwt_token:
                logger.warning("Job poll skipped: no JWT stored")
                self._stop_event.wait(POLL_INTERVAL)
                continue

            try:
                result = self.client.jobs_pending(jwt_token)
                jobs = result.get("jobs", []) if isinstance(result, dict) else (result or [])
                logger.info("Job poll: received %d job(s) from server", len(jobs))

                for job in jobs:
                    job_id = job.get("job_id")
                    if job_id in self._seen_job_ids:
                        # Defensive: server already marked this job 'sent',
                        # avoid double-processing on overlapping polls.
                        logger.warning("Job poll: job_id=%s already queued locally, skipping duplicate", job_id)
                        continue
                    self._seen_job_ids.add(job_id)
                    try:
                        self._job_queue.put_nowait(job)
                        self._emit({"job_id": job_id, "status": "received", "message": "Job received from server"})
                    except queue.Full:
                        logger.error("Job poll: local queue full, dropping job_id=%s", job_id)
                        self._emit({"job_id": job_id, "status": "dropped", "message": "Local queue full"})

            except ApiError as exc:
                logger.error("Job poll failed: %s", exc.message)
                if exc.status_code == 401:
                    logger.error("JWT rejected (401) during job poll, stopping poller")
                    self.config.update({"jwt": ""})
                    if self.on_auth_failure:
                        self.on_auth_failure(exc.message)
                    return

            self._stop_event.wait(POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._job_queue.get(timeout=1)
            except queue.Empty:
                continue

            job_id = job.get("job_id")
            try:
                self._process_job(job)
            except Exception:
                logger.exception("Job worker: unexpected error processing job_id=%s", job_id)
            finally:
                self._seen_job_ids.discard(job_id)
                self._job_queue.task_done()

    def _process_job(self, job: Dict[str, Any]) -> None:
        job_id = job.get("job_id")
        jwt_token = self.config.get("jwt", "")
        if not jwt_token:
            logger.error("Job worker: no JWT stored, cannot process job_id=%s", job_id)
            self._emit({"job_id": job_id, "status": "failed", "message": "No JWT stored"})
            return

        # Step 1: acknowledge - tells Odoo this agent has taken ownership
        # of the job (status -> 'printing') before we actually spool it.
        try:
            self.client.jobs_ack(jwt_token, job_id)
            logger.info("Job worker: job_id=%s acknowledged", job_id)
            self._emit({"job_id": job_id, "status": "printing", "message": "Sending to printer"})
        except ApiError as exc:
            logger.error("Job worker: ack failed for job_id=%s: %s", job_id, exc.message)
            self._emit({"job_id": job_id, "status": "error", "message": f"Ack failed: {exc.message}"})
            # Ack failing (e.g. network blip) shouldn't stop us trying to
            # print - but if it's an auth failure, stop everything so we
            # don't spool jobs we can no longer report back on.
            if exc.status_code == 401:
                self.config.update({"jwt": ""})
                if self.on_auth_failure:
                    self.on_auth_failure(exc.message)
                return

        # Step 2: actually print.
        try:
            execution_time = self.executor.print_job(job)
        except PrintError as exc:
            logger.error("Job worker: print failed for job_id=%s: %s", job_id, exc)
            self._report_fail(jwt_token, job_id, str(exc))
            return
        except Exception as exc:
            logger.exception("Job worker: unexpected print error for job_id=%s", job_id)
            self._report_fail(jwt_token, job_id, f"Unexpected error: {exc}")
            return

        # Step 3: report success.
        try:
            self.client.jobs_complete(jwt_token, job_id)
            logger.info("Job worker: job_id=%s completed in %.2fs", job_id, execution_time)
            self._emit({
                "job_id": job_id, "status": "done",
                "message": f"Printed in {execution_time:.2f}s",
            })
        except ApiError as exc:
            logger.error("Job worker: complete-report failed for job_id=%s: %s", job_id, exc.message)
            self._emit({"job_id": job_id, "status": "error", "message": f"Complete report failed: {exc.message}"})

    def _report_fail(self, jwt_token: str, job_id: Any, reason: str) -> None:
        self._emit({"job_id": job_id, "status": "failed", "message": reason})
        try:
            self.client.jobs_fail(jwt_token, job_id, reason)
        except ApiError as exc:
            logger.error("Job worker: fail-report itself failed for job_id=%s: %s", job_id, exc.message)

    def _emit(self, event: Dict[str, Any]) -> None:
        if self.on_job_event:
            try:
                self.on_job_event(event)
            except Exception:
                logger.exception("Job event callback raised an exception")
JobPoller = JobManager