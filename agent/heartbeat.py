"""Background heartbeat thread for Kits Direct Print Agent."""

import threading
import time
from typing import Callable, Optional

from api import OdooApiClient, ApiError
from config import ConfigManager
from logger import get_logger

logger = get_logger(__name__)


class HeartbeatWorker:
    """Runs heartbeat calls on a background thread until stopped."""

    def __init__(
        self,
        client: OdooApiClient,
        config: ConfigManager,
        on_success: Optional[Callable[[dict], None]] = None,
        on_failure: Optional[Callable[[str], None]] = None,
        on_auth_failure: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.client = client
        self.config = config
        self.on_success = on_success
        self.on_failure = on_failure
        self.on_auth_failure = on_auth_failure

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.info("Heartbeat already running, ignoring start()")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Heartbeat thread started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("Heartbeat thread stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            jwt_token = self.config.get("jwt", "")
            interval = self.config.get("heartbeat_interval", 30) or 30

            if not jwt_token:
                logger.warning("Heartbeat skipped: no JWT stored")
                self._stop_event.wait(interval)
                continue

            try:
                result = self.client.heartbeat(jwt_token)
                logger.info("Heartbeat OK: %s", result)
                if self.on_success:
                    self.on_success(result)
            except ApiError as exc:
                logger.error("Heartbeat failed: %s", exc.message)
                if exc.status_code == 401:
                    logger.error("JWT rejected (401), stopping heartbeat and clearing token")
                    self.config.update({"jwt": ""})
                    if self.on_auth_failure:
                        self.on_auth_failure(exc.message)
                    return  # stop thread, don't retry with dead jwt
                if self.on_failure:
                    self.on_failure(exc.message)
            except Exception as exc:  # pragma: no cover - defensive
                # A bug in a callback or an unforeseen error must not
                # silently kill the heartbeat thread (which would make the
                # machine look "offline" in Odoo with no indication why).
                logger.exception("Heartbeat loop: unexpected error")
                if self.on_failure:
                    self.on_failure(str(exc))

            # wait for interval, but wake early if stop() is called
            self._stop_event.wait(interval)