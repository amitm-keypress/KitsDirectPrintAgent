"""Printer discovery AND print execution for Kits Direct Print Agent.

Windows -> win32print / ShellExecute
Linux/macOS -> pycups (CUPS)

NOTE: the previous version of this file only implemented printer
*discovery* (enumerating printers to sync to Odoo). There was no code
anywhere in the agent that actually sent a job's document to a printer.
That is the primary reason print jobs never physically printed: they
reached the agent (via /jobs/pending), but nothing consumed them.
PrintExecutor below is the missing piece.
"""

import base64
import binascii
import os
import platform
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)

# Common install locations for SumatraPDF on Windows, checked in order.
# We shell out to it directly (-print-to / -silent) instead of relying on
# ShellExecute's "printto" verb, because that verb is only registered by
# some installers/under some conditions -- even when SumatraPDF is set as
# the default .pdf handler, "printto" can be missing from the registry,
# causing SE_ERR_NOASSOC (WinError 31) even though printing would work
# fine via the command line. This is more deterministic and doesn't
# require touching the user's default-printer or file associations at all.
_SUMATRA_CANDIDATES = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe"),
    os.path.expandvars(r"%APPDATA%\SumatraPDF\SumatraPDF.exe"),
]


def _find_sumatra() -> Optional[str]:
    on_path = shutil.which("SumatraPDF.exe") or shutil.which("SumatraPDF")
    if on_path:
        return on_path
    for candidate in _SUMATRA_CANDIDATES:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None

# CUPS printer-state codes: 3=idle, 4=processing, 5=stopped
_CUPS_STATE_MAP = {3: "idle", 4: "printing", 5: "stopped"}

# win32 printer status bit flags of interest
_WIN32_STATUS_MAP = {
    0: "idle",
    1: "paused",
    2: "error",
    4: "pending_deletion",
    8: "paper_jam",
    16: "paper_out",
    32: "manual_feed",
    64: "paper_problem",
    128: "offline",
}


class PrinterDiscoveryError(Exception):
    """Raised when printer enumeration fails outright."""


class PrinterDiscovery:
    """Enumerates system printers into a normalized JSON-friendly list."""

    def __init__(self) -> None:
        self.system = platform.system()

    def discover(self) -> List[Dict[str, Any]]:
        """Return list of {name, driver, status, is_default} dicts."""
        if self.system == "Windows":
            return self._discover_windows()
        return self._discover_cups()

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------
    def _discover_windows(self) -> List[Dict[str, Any]]:
        try:
            import win32print
        except ImportError as exc:
            logger.error("pywin32 not available: %s", exc)
            raise PrinterDiscoveryError(
                "pywin32 is required on Windows but is not installed."
            ) from exc

        printers: List[Dict[str, Any]] = []
        try:
            default_name = win32print.GetDefaultPrinter()
        except Exception:
            default_name = None

        try:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            raw_printers = win32print.EnumPrinters(flags)
        except Exception as exc:
            logger.error("EnumPrinters failed: %s", exc)
            raise PrinterDiscoveryError(f"Failed to enumerate printers: {exc}") from exc

        for _flags, _desc, name, _comment in raw_printers:
            driver = ""
            status_code = 0
            try:
                handle = win32print.OpenPrinter(name)
                try:
                    info = win32print.GetPrinter(handle, 2)
                    driver = info.get("pDriverName", "")
                    status_code = info.get("Status", 0)
                finally:
                    win32print.ClosePrinter(handle)
            except Exception as exc:
                logger.warning("Could not read printer info for %s: %s", name, exc)

            status = self._decode_win32_status(status_code)

            printers.append(
                {
                    "name": name,
                    "driver": driver,
                    "status": status,
                    "is_default": name == default_name,
                }
            )

        logger.info("Discovered %d printer(s) via win32print", len(printers))
        return printers

    @staticmethod
    def _decode_win32_status(status_code: int) -> str:
        if status_code == 0:
            return "idle"
        active_flags = [
            label for bit, label in _WIN32_STATUS_MAP.items() if bit and (status_code & bit)
        ]
        return ",".join(active_flags) if active_flags else f"unknown({status_code})"

    # ------------------------------------------------------------------
    # Linux / macOS (CUPS)
    # ------------------------------------------------------------------
    def _discover_cups(self) -> List[Dict[str, Any]]:
        try:
            import cups
        except ImportError as exc:
            logger.error("pycups not available: %s", exc)
            raise PrinterDiscoveryError(
                "pycups is required on Linux/macOS but is not installed."
            ) from exc

        printers: List[Dict[str, Any]] = []
        try:
            conn = cups.Connection()
            raw_printers: Dict[str, Any] = conn.getPrinters()
        except Exception as exc:
            logger.error("CUPS getPrinters failed: %s", exc)
            raise PrinterDiscoveryError(f"Failed to enumerate CUPS printers: {exc}") from exc

        default_name = None
        try:
            default_name = conn.getDefault()
        except Exception:
            default_name = None

        for name, info in raw_printers.items():
            state_code = info.get("printer-state", 3)
            status = _CUPS_STATE_MAP.get(state_code, f"unknown({state_code})")
            driver = info.get("printer-make-and-model", "")

            printers.append(
                {
                    "name": name,
                    "driver": driver,
                    "status": status,
                    "is_default": name == default_name,
                }
            )

        logger.info("Discovered %d printer(s) via CUPS", len(printers))
        return printers


# Job file_types that should be spooled as RAW bytes straight to the printer
# (thermal/ESC-POS receipt printers, Zebra label printers, plain text) rather
# than handed to a document renderer.
_RAW_FILE_TYPES = {"txt", "zpl", "escpos"}


class PrintError(Exception):
    """Raised when a print job cannot be sent to the printer."""


class PrintExecutor:
    """Takes a job payload (as returned by Odoo's /jobs/pending) and sends
    it to the target printer on the local machine.

    This is the component that was completely missing from the agent:
    printer.py previously only *discovered* printers, it never *used* one.
    """

    def __init__(self) -> None:
        self.system = platform.system()

    def print_job(self, job: Dict[str, Any]) -> float:
        """Prints a single job payload. Returns execution time in seconds.
        Raises PrintError on any failure (decoding, spooling, missing
        printer, etc.) with a human-readable message suitable for
        reporting back to Odoo via /jobs/fail.
        """
        started = time.monotonic()
        job_id = job.get("job_id")
        printer_name = job.get("printer_system_name")
        file_type = (job.get("file_type") or "pdf").lower()
        filename = job.get("filename") or f"job_{job_id}"
        copies = max(1, int(job.get("copies") or 1))
        content_b64 = job.get("content_base64")

        logger.info(
            "PrintExecutor: starting job_id=%s printer=%r file_type=%s copies=%s filename=%s",
            job_id, printer_name, file_type, copies, filename,
        )

        if not printer_name:
            raise PrintError("Job payload has no printer_system_name; cannot print.")
        if not content_b64:
            raise PrintError("Job payload has no content_base64; nothing to print.")

        try:
            raw_bytes = base64.b64decode(content_b64)
        except (binascii.Error, ValueError) as exc:
            raise PrintError(f"Failed to decode job content: {exc}") from exc

        if not raw_bytes:
            raise PrintError("Decoded job content is empty.")

        logger.info("PrintExecutor: job_id=%s decoded %d bytes", job_id, len(raw_bytes))

        try:
            if file_type in _RAW_FILE_TYPES:
                self._print_raw(printer_name, raw_bytes, copies)
            else:
                self._print_document(printer_name, raw_bytes, filename, file_type, copies)
        except PrintError:
            raise
        except Exception as exc:
            logger.exception("PrintExecutor: unexpected error printing job_id=%s", job_id)
            raise PrintError(f"Unexpected printing error: {exc}") from exc

        execution_time = time.monotonic() - started
        logger.info(
            "PrintExecutor: job_id=%s sent to printer %r successfully in %.2fs",
            job_id, printer_name, execution_time,
        )
        return execution_time

    # ------------------------------------------------------------------
    # Raw passthrough (ESC/POS, ZPL, plain text)
    # ------------------------------------------------------------------
    def _print_raw(self, printer_name: str, data: bytes, copies: int) -> None:
        if self.system == "Windows":
            self._print_raw_windows(printer_name, data, copies)
        else:
            self._print_raw_cups(printer_name, data, copies)

    def _print_raw_windows(self, printer_name: str, data: bytes, copies: int) -> None:
        try:
            import win32print
        except ImportError as exc:
            raise PrintError("pywin32 is required on Windows but is not installed.") from exc

        for i in range(copies):
            try:
                handle = win32print.OpenPrinter(printer_name)
            except Exception as exc:
                raise PrintError(f"Could not open printer {printer_name!r}: {exc}") from exc
            try:
                job_info = ("Kits Direct Print", None, "RAW")
                job_id = win32print.StartDocPrinter(handle, 1, job_info)
                try:
                    win32print.StartPagePrinter(handle)
                    win32print.WritePrinter(handle, data)
                    win32print.EndPagePrinter(handle)
                finally:
                    win32print.EndDocPrinter(handle)
                logger.info("PrintExecutor: raw win32 job %s sent (copy %d/%d)", job_id, i + 1, copies)
            except Exception as exc:
                raise PrintError(f"win32print raw spool failed: {exc}") from exc
            finally:
                win32print.ClosePrinter(handle)

    def _print_raw_cups(self, printer_name: str, data: bytes, copies: int) -> None:
        try:
            import cups
        except ImportError as exc:
            raise PrintError("pycups is required on Linux/macOS but is not installed.") from exc

        tmp_path = self._write_temp_file(data, suffix=".raw")
        try:
            conn = cups.Connection()
            for i in range(copies):
                job_id = conn.printFile(
                    printer_name, tmp_path, "Kits Direct Print", {"raw": "true"}
                )
                logger.info("PrintExecutor: raw CUPS job %s sent (copy %d/%d)", job_id, i + 1, copies)
        except Exception as exc:
            raise PrintError(f"CUPS raw print failed: {exc}") from exc
        finally:
            self._cleanup_temp_file(tmp_path)

    # ------------------------------------------------------------------
    # Rendered documents (PDF, PNG, JPEG)
    # ------------------------------------------------------------------
    def _print_document(
        self, printer_name: str, data: bytes, filename: str, file_type: str, copies: int
    ) -> None:
        suffix = "." + (file_type or "pdf")
        tmp_path = self._write_temp_file(data, suffix=suffix)
        try:
            if self.system == "Windows":
                self._print_document_windows(printer_name, tmp_path, copies)
            else:
                self._print_document_cups(printer_name, tmp_path, copies)
        finally:
            self._cleanup_temp_file(tmp_path)

    def _print_document_windows(self, printer_name: str, filepath: str, copies: int) -> None:
        sumatra = _find_sumatra()
        if sumatra:
            self._print_document_windows_sumatra(sumatra, printer_name, filepath, copies)
        else:
            logger.warning(
                "PrintExecutor: SumatraPDF not found on this machine; falling back to "
                "ShellExecute 'printto' verb, which requires that verb to be registered "
                "for the file's default handler. Install SumatraPDF for reliable silent "
                "printing: https://www.sumatrapdfreader.org/download-free-pdf-viewer"
            )
            self._print_document_windows_shellexecute(printer_name, filepath, copies)

    def _print_document_windows_sumatra(
        self, sumatra_path: str, printer_name: str, filepath: str, copies: int
    ) -> None:
        try:
            for i in range(copies):
                cmd = [
                    sumatra_path,
                    "-print-to", printer_name,
                    "-print-settings", "1x",
                    "-silent",
                    filepath,
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60
                )
                if result.returncode != 0:
                    raise PrintError(
                        f"SumatraPDF print failed (exit {result.returncode}): "
                        f"{result.stderr.strip() or result.stdout.strip()}"
                    )
                logger.info(
                    "PrintExecutor: document print dispatched via SumatraPDF (copy %d/%d)",
                    i + 1, copies,
                )
                time.sleep(0.5)
        except PrintError:
            raise
        except subprocess.TimeoutExpired as exc:
            raise PrintError("SumatraPDF print timed out") from exc
        except Exception as exc:
            raise PrintError(f"Windows document print failed: {exc}") from exc

    def _print_document_windows_shellexecute(self, printer_name: str, filepath: str, copies: int) -> None:
        try:
            import win32api
            import win32print
        except ImportError as exc:
            raise PrintError("pywin32 is required on Windows but is not installed.") from exc

        previous_default = None
        try:
            previous_default = win32print.GetDefaultPrinter()
        except Exception:
            previous_default = None

        try:
            # ShellExecute's "printto" verb needs the target printer set as
            # the default for the associated application to honour it
            # reliably across PDF viewers; restore the previous default
            # afterwards so we don't leave the user's system changed.
            win32print.SetDefaultPrinter(printer_name)
            for i in range(copies):
                rc = win32api.ShellExecute(
                    0, "printto", filepath, f'"{printer_name}"', ".", 0
                )
                if rc <= 32:
                    raise PrintError(
                        f"ShellExecute printto failed (code {rc}); no PDF-capable handler "
                        f"registered, or printer {printer_name!r} unavailable."
                    )
                logger.info("PrintExecutor: document print dispatched via ShellExecute (copy %d/%d)", i + 1, copies)
                # ShellExecute is async (hands off to the associated app);
                # give it a moment between copies so jobs don't collide.
                time.sleep(1.5)
        except PrintError:
            raise
        except Exception as exc:
            raise PrintError(f"Windows document print failed: {exc}") from exc
        finally:
            if previous_default:
                try:
                    win32print.SetDefaultPrinter(previous_default)
                except Exception:
                    logger.warning("PrintExecutor: could not restore previous default printer")

    def _print_document_cups(self, printer_name: str, filepath: str, copies: int) -> None:
        try:
            import cups
        except ImportError as exc:
            raise PrintError("pycups is required on Linux/macOS but is not installed.") from exc

        try:
            conn = cups.Connection()
            job_id = conn.printFile(
                printer_name, filepath, "Kits Direct Print", {"copies": str(copies)}
            )
            logger.info("PrintExecutor: CUPS document job %s sent (%d copies)", job_id, copies)
        except Exception as exc:
            raise PrintError(f"CUPS document print failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _write_temp_file(data: bytes, suffix: str) -> str:
        tmp_dir = tempfile.gettempdir()
        tmp_path = os.path.join(tmp_dir, f"kits_print_{uuid.uuid4().hex}{suffix}")
        with open(tmp_path, "wb") as f:
            f.write(data)
        return tmp_path

    @staticmethod
    def _cleanup_temp_file(path: Optional[str]) -> None:
        if not path:
            return
        try:
            os.remove(path)
        except OSError:
            logger.warning("PrintExecutor: could not remove temp file %s", path)