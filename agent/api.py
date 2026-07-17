"""API client for Kits Direct Print Odoo endpoints."""

from typing import Any, Dict, Optional
import requests

from logger import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT = 10  # seconds


class ApiError(Exception):
    """Raised for any API-level failure (network, HTTP, JSON, auth)."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class OdooApiClient:
    """Thin REST client for the Kits Direct Print Odoo controllers."""

    def __init__(self, base_url: str) -> None:
        self.base_url = self._normalize_url(base_url)

    @staticmethod
    def _normalize_url(base_url: str) -> str:
        """Accept URLs with or without a scheme; default to http:// if missing.
        Works with both http:// and https:// as typed by the user.
        """
        url = base_url.strip().rstrip("/")
        if not url:
            return url
        if not url.lower().startswith(("http://", "https://")):
            url = f"http://{url}"
        return url

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    def _redact(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Returns a copy of payload with secret fields masked, for safe logging."""
        redacted = dict(payload)
        for key in ("jwt", "token"):
            if key in redacted and redacted[key]:
                redacted[key] = "***redacted***"
        return redacted

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST JSON to Odoo, raise ApiError on any failure, return parsed JSON."""
        url = self._url(path)
        logger.info("REQUEST %s payload=%s", url, self._redact(payload))
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=DEFAULT_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
        except requests.exceptions.Timeout as exc:
            logger.error("Timeout calling %s: %s", url, exc)
            raise ApiError(f"Connection timeout calling {path}") from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error("Network failure calling %s: %s", url, exc)
            raise ApiError(f"Network failure calling {path}") from exc
        except requests.exceptions.RequestException as exc:
            logger.error("Request error calling %s: %s", url, exc)
            raise ApiError(f"Request error calling {path}: {exc}") from exc

        logger.info("RESPONSE %s status=%s body=%s", url, response.status_code, response.text)

        if response.status_code == 401:
            raise ApiError("Unauthorized (401): invalid or expired JWT/token", 401)
        if response.status_code == 500:
            raise ApiError("Odoo internal server error (500)", 500)
        if not response.ok:
            raise ApiError(
                f"Unexpected HTTP status {response.status_code}: {response.text}",
                response.status_code,
            )

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Invalid JSON from %s: %s", url, exc)
            raise ApiError(f"Invalid JSON response from {path}") from exc

    def register(
        self,
        machine_uuid: str,
        token: str,
        hostname: str,
        os_type: str,
        os_version: str,
        agent_version: str,
    ) -> Dict[str, Any]:
        payload = {
            "uuid": machine_uuid,
            "token": token,
            "hostname": hostname,
            "os_type": os_type,
            "os_version": os_version,
            "agent_version": agent_version,
        }
        return self._post("/kits/direct_print/v1/register", payload)

    def heartbeat(self, jwt_token: str) -> Dict[str, Any]:
        payload = {"jwt": jwt_token}
        return self._post("/kits/direct_print/v1/heartbeat", payload)

    def sync_printers(self, jwt_token: str, printers: list) -> Dict[str, Any]:
        payload = {"jwt": jwt_token, "printers": printers}
        return self._post("/kits/direct_print/v1/printers/sync", payload)

    def jobs_pending(self, jwt_token: str) -> Dict[str, Any]:
        payload = {"jwt": jwt_token}
        return self._post("/kits/direct_print/v1/jobs/pending", payload)

    def jobs_ack(self, jwt_token: str, job_id: Any) -> Dict[str, Any]:
        payload = {"jwt": jwt_token, "job_id": job_id}
        return self._post("/kits/direct_print/v1/jobs/ack", payload)

    def jobs_complete(self, jwt_token: str, job_id: Any) -> Dict[str, Any]:
        payload = {"jwt": jwt_token, "job_id": job_id}
        return self._post("/kits/direct_print/v1/jobs/complete", payload)

    def jobs_fail(self, jwt_token: str, job_id: Any, reason: str) -> Dict[str, Any]:
        # BUGFIX: the Odoo controller (/jobs/fail) reads body.get('error'),
        # not 'reason'. Sending "reason" meant the failure message was
        # silently dropped and every failed job was recorded in Odoo as
        # "Unknown agent error" regardless of what actually went wrong.
        payload = {"jwt": jwt_token, "job_id": job_id, "error": reason}
        return self._post("/kits/direct_print/v1/jobs/fail", payload)