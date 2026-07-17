"""Tkinter GUI for Kits Direct Print Agent.

Redesigned for a modern, professional desktop-app look (dark sidebar-free
top bar, card-style status panel, tabbed layout) and to surface the full
job lifecycle (received -> printing -> done/failed) that jobs.py now
implements, plus a live tail of the agent log for on-the-spot debugging.
"""

import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox
import requests

from config import ConfigManager
from api import OdooApiClient, ApiError
from heartbeat import HeartbeatWorker
from jobs import JobManager
from printer import PrinterDiscovery, PrinterDiscoveryError
from logger import get_logger, tail_log

logger = get_logger(__name__)

# ---------------------------------------------------------------------
# Palette - a small, consistent professional theme (no external theme
# packages required, just ttk.Style tweaks on top of the 'clam' base).
# ---------------------------------------------------------------------
COLOR_BG = "#1f2430"
COLOR_BG_CARD = "#262c3b"
COLOR_BG_INPUT = "#2f3644"
COLOR_FG = "#e6e9ef"
COLOR_FG_MUTED = "#9aa4b8"
COLOR_ACCENT = "#4f8cff"
COLOR_GREEN = "#3ecf8e"
COLOR_RED = "#f0576b"
COLOR_ORANGE = "#f5a623"
COLOR_BORDER = "#39415433"

STATUS_COLORS = {
    "received": COLOR_FG_MUTED,
    "printing": COLOR_ORANGE,
    "done": COLOR_GREEN,
    "failed": COLOR_RED,
    "error": COLOR_RED,
    "dropped": COLOR_RED,
}


class AgentGUI:
    """Main application window."""

    def __init__(self, root: tk.Tk, config: ConfigManager) -> None:
        self.root = root
        self.config = config
        self.client: OdooApiClient | None = None
        self.heartbeat: HeartbeatWorker | None = None
        self.job_manager: JobManager | None = None
        self._log_autorefresh = True

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.title("Kits Direct Print Agent")
        self.root.geometry("860x600")
        self.root.minsize(780, 540)
        self.root.configure(bg=COLOR_BG)

        self._setup_style()
        self._build_layout()
        self._load_fields_from_config()
        self._start_log_autorefresh()

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=COLOR_BG, foreground=COLOR_FG, font=("Segoe UI", 10))
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Card.TFrame", background=COLOR_BG_CARD)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_FG)
        style.configure("Card.TLabel", background=COLOR_BG_CARD, foreground=COLOR_FG)
        style.configure("Muted.TLabel", background=COLOR_BG, foreground=COLOR_FG_MUTED)
        style.configure("CardMuted.TLabel", background=COLOR_BG_CARD, foreground=COLOR_FG_MUTED)
        style.configure("Title.TLabel", background=COLOR_BG, foreground=COLOR_FG,
                         font=("Segoe UI", 16, "bold"))
        style.configure("Badge.TLabel", background=COLOR_BG_CARD, font=("Segoe UI", 10, "bold"))

        style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=COLOR_BG_CARD, foreground=COLOR_FG_MUTED,
                         padding=(16, 8), font=("Segoe UI", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", COLOR_ACCENT)],
                  foreground=[("selected", "#ffffff")])

        style.configure("TEntry", fieldbackground=COLOR_BG_INPUT, foreground=COLOR_FG,
                         insertcolor=COLOR_FG, borderwidth=1)
        style.configure("TButton", background=COLOR_ACCENT, foreground="#ffffff",
                         borderwidth=0, padding=(12, 7), font=("Segoe UI", 10, "bold"))
        style.map("TButton", background=[("active", "#3d75db"), ("disabled", "#4a5266")])
        style.configure("Secondary.TButton", background=COLOR_BG_INPUT, foreground=COLOR_FG,
                         borderwidth=0, padding=(12, 7))
        style.map("Secondary.TButton", background=[("active", "#3a4256")])

        style.configure("Treeview", background=COLOR_BG_CARD, fieldbackground=COLOR_BG_CARD,
                         foreground=COLOR_FG, borderwidth=0, rowheight=26)
        style.configure("Treeview.Heading", background=COLOR_BG_INPUT, foreground=COLOR_FG,
                         borderwidth=0, font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", COLOR_ACCENT)])

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        top = ttk.Frame(self.root, padding=(20, 16, 20, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Kits Direct Print Agent", style="Title.TLabel").pack(side="left")

        badge_frame = ttk.Frame(top)
        badge_frame.pack(side="right")
        self.status_dot = tk.Canvas(badge_frame, width=10, height=10, bg=COLOR_BG,
                                     highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 6))
        self._dot = self.status_dot.create_oval(1, 1, 9, 9, fill=COLOR_RED, outline="")
        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(badge_frame, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        self.tab_connection = ttk.Frame(notebook, padding=16)
        self.tab_printers = ttk.Frame(notebook, padding=16)
        self.tab_queue = ttk.Frame(notebook, padding=16)
        self.tab_logs = ttk.Frame(notebook, padding=16)

        notebook.add(self.tab_connection, text="Connection")
        notebook.add(self.tab_printers, text="Printers")
        notebook.add(self.tab_queue, text="Job Queue")
        notebook.add(self.tab_logs, text="Logs")

        self._build_connection_tab()
        self._build_printers_tab()
        self._build_queue_tab()
        self._build_logs_tab()

    def _card(self, parent) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        return card

    # -- Connection tab --------------------------------------------------
    def _build_connection_tab(self) -> None:
        card = self._card(self.tab_connection)
        card.pack(fill="x")

        fields = ttk.Frame(card, style="Card.TFrame")
        fields.pack(fill="x")
        fields.columnconfigure(1, weight=1)

        def row(label, r):
            ttk.Label(fields, text=label, style="Card.TLabel").grid(
                row=r, column=0, sticky="w", padx=(0, 12), pady=6)

        row("Odoo URL", 0)
        self.odoo_url_var = tk.StringVar()
        ttk.Entry(fields, textvariable=self.odoo_url_var).grid(row=0, column=1, sticky="ew", pady=6)

        row("Token", 1)
        self.token_var = tk.StringVar()
        ttk.Entry(fields, textvariable=self.token_var, show="*").grid(row=1, column=1, sticky="ew", pady=6)

        row("Machine UUID", 2)
        self.uuid_var = tk.StringVar()
        ttk.Entry(fields, textvariable=self.uuid_var, state="readonly").grid(row=2, column=1, sticky="ew", pady=6)

        row("JWT Token", 3)
        self.jwt_var = tk.StringVar()
        ttk.Entry(fields, textvariable=self.jwt_var, state="readonly", show="*").grid(
            row=3, column=1, sticky="ew", pady=6)

        btns = ttk.Frame(card, style="Card.TFrame")
        btns.pack(fill="x", pady=(14, 0))
        self.connect_btn = ttk.Button(btns, text="Connect", command=self.on_connect)
        self.connect_btn.pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Save", style="Secondary.TButton", command=self.on_save).pack(
            side="left", padx=(0, 8))
        ttk.Button(btns, text="Test Connection", style="Secondary.TButton",
                   command=self.on_test_connection).pack(side="left")

        info_card = self._card(self.tab_connection)
        info_card.pack(fill="both", expand=True, pady=(16, 0))
        ttk.Label(info_card, text="Activity", style="Badge.TLabel").pack(anchor="w")
        self.message_box = tk.Text(info_card, height=12, bg=COLOR_BG_INPUT, fg=COLOR_FG,
                                    insertbackground=COLOR_FG, borderwidth=0, wrap="word",
                                    state="disabled", font=("Consolas", 9))
        self.message_box.pack(fill="both", expand=True, pady=(8, 0))

    # -- Printers tab ------------------------------------------------------
    def _build_printers_tab(self) -> None:
        card = self._card(self.tab_printers)
        card.pack(fill="both", expand=True)

        header = ttk.Frame(card, style="Card.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Discovered Printers", style="Badge.TLabel").pack(side="left")
        self.sync_btn = ttk.Button(header, text="Sync Printers", command=self.on_sync_printers,
                                    state="disabled")
        self.sync_btn.pack(side="right")

        columns = ("name", "driver", "status", "default")
        self.printers_tree = ttk.Treeview(card, columns=columns, show="headings", height=14)
        for col, label, width in (
            ("name", "Printer Name", 260), ("driver", "Driver", 220),
            ("status", "Status", 120), ("default", "Default", 80),
        ):
            self.printers_tree.heading(col, text=label)
            self.printers_tree.column(col, width=width, anchor="w")
        self.printers_tree.pack(fill="both", expand=True, pady=(12, 0))

    # -- Job Queue tab -----------------------------------------------------
    def _build_queue_tab(self) -> None:
        card = self._card(self.tab_queue)
        card.pack(fill="both", expand=True)

        header = ttk.Frame(card, style="Card.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Recent Print Jobs", style="Badge.TLabel").pack(side="left")
        self.queue_summary_var = tk.StringVar(value="No jobs yet")
        ttk.Label(header, textvariable=self.queue_summary_var, style="CardMuted.TLabel").pack(side="right")

        columns = ("time", "job_id", "status", "message")
        self.queue_tree = ttk.Treeview(card, columns=columns, show="headings", height=16)
        for col, label, width in (
            ("time", "Time", 90), ("job_id", "Job ID", 80),
            ("status", "Status", 100), ("message", "Detail", 380),
        ):
            self.queue_tree.heading(col, text=label)
            self.queue_tree.column(col, width=width, anchor="w")
        self.queue_tree.pack(fill="both", expand=True, pady=(12, 0))

        for status, color in STATUS_COLORS.items():
            self.queue_tree.tag_configure(status, foreground=color)

        self._job_row_by_id: dict = {}

    # -- Logs tab -----------------------------------------------------------
    def _build_logs_tab(self) -> None:
        card = self._card(self.tab_logs)
        card.pack(fill="both", expand=True)

        header = ttk.Frame(card, style="Card.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Agent Log (live)", style="Badge.TLabel").pack(side="left")
        ttk.Button(header, text="Refresh Now", style="Secondary.TButton",
                   command=self._refresh_logs).pack(side="right")

        self.log_box = tk.Text(card, bg=COLOR_BG_INPUT, fg=COLOR_FG, insertbackground=COLOR_FG,
                                borderwidth=0, wrap="none", state="disabled", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True, pady=(12, 0))

    # ------------------------------------------------------------------
    # Config <-> fields
    # ------------------------------------------------------------------
    def _load_fields_from_config(self) -> None:
        self.odoo_url_var.set(self.config.get("odoo_url", ""))
        self.token_var.set(self.config.get("token", ""))
        self.uuid_var.set(self.config.get("uuid", ""))
        self.jwt_var.set(self.config.get("jwt", ""))
        if self.config.get("jwt"):
            self._set_status("Connected", COLOR_GREEN)
            self.sync_btn.config(state="normal")
            url = self.config.get("odoo_url", "")
            if url:
                self.client = OdooApiClient(url)
                self._start_heartbeat()
                self._start_job_manager()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _log_message(self, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.message_box.config(state="normal")
        self.message_box.insert("end", f"[{timestamp}] {text}\n")
        self.message_box.see("end")
        self.message_box.config(state="disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status_var.set(text)
        self.status_dot.itemconfig(self._dot, fill=color)

    def _get_client(self) -> OdooApiClient:
        url = self.odoo_url_var.get().strip()
        if not url:
            raise ApiError("Odoo URL is empty. Enter a URL first.")
        return OdooApiClient(url)

    def _start_log_autorefresh(self) -> None:
        self._refresh_logs()
        self.root.after(3000, self._start_log_autorefresh)

    def _refresh_logs(self) -> None:
        content = tail_log(400)
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("end", content)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # ------------------------------------------------------------------
    # Button handlers - Connection
    # ------------------------------------------------------------------
    def on_save(self) -> None:
        self.config.update(
            {
                "odoo_url": self.odoo_url_var.get().strip(),
                "token": self.token_var.get().strip(),
            }
        )
        logger.info("Configuration saved via GUI")
        self._log_message("Configuration saved.")

    def on_test_connection(self) -> None:
        url = self.odoo_url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Enter an Odoo URL first.")
            return
        url = OdooApiClient._normalize_url(url)
        try:
            logger.info("Test Connection to %s", url)
            response = requests.get(url, timeout=5)
            self._log_message(f"Test Connection: HTTP {response.status_code}")
            messagebox.showinfo(
                "Test Connection", f"Server reachable. HTTP status: {response.status_code}"
            )
        except requests.exceptions.Timeout:
            self._log_message("Test Connection: timeout")
            messagebox.showerror("Test Connection Failed", "Connection timeout.")
        except requests.exceptions.ConnectionError:
            self._log_message("Test Connection: network failure")
            messagebox.showerror("Test Connection Failed", "Network failure. Server unreachable.")
        except requests.exceptions.RequestException as exc:
            self._log_message(f"Test Connection error: {exc}")
            messagebox.showerror("Test Connection Failed", str(exc))

    def on_connect(self) -> None:
        self.on_save()  # persist url/token first
        try:
            client = self._get_client()
        except ApiError as exc:
            messagebox.showerror("Error", exc.message)
            return

        token = self.token_var.get().strip()
        if not token:
            messagebox.showerror("Error", "Enter a Token before connecting.")
            return

        try:
            logger.info("Register request initiated")
            result = client.register(
                machine_uuid=self.config.get("uuid"),
                token=token,
                hostname=self.config.get("hostname"),
                os_type=self.config.get("os_type"),
                os_version=self.config.get("os_version"),
                agent_version=self.config.get("agent_version"),
            )
        except ApiError as exc:
            logger.error("Register failed: %s", exc.message)
            self._log_message(f"Register failed: {exc.message}")
            self._set_status("Disconnected", COLOR_RED)
            messagebox.showerror("Connection Failed", exc.message)
            return

        jwt_token = result.get("jwt", "")
        machine_id = result.get("machine_id", "")
        heartbeat_interval = result.get("heartbeat_interval", 30)

        if not jwt_token:
            self._log_message("Register response missing JWT.")
            messagebox.showerror("Connection Failed", "Server response did not include a JWT.")
            return

        self.config.update(
            {
                "jwt": jwt_token,
                "machine_id": machine_id,
                "heartbeat_interval": heartbeat_interval,
            }
        )
        self.jwt_var.set(jwt_token)
        self.client = client
        self._set_status("Connected", COLOR_GREEN)
        self.sync_btn.config(state="normal")
        self._log_message("Connected successfully.")

        self._start_heartbeat()
        self._start_job_manager()

    def _start_heartbeat(self) -> None:
        if self.client is None:
            return
        if self.heartbeat and self.heartbeat.is_running():
            return
        self.heartbeat = HeartbeatWorker(
            client=self.client,
            config=self.config,
            on_success=self._on_heartbeat_success,
            on_failure=self._on_heartbeat_failure,
            on_auth_failure=self._on_auth_failure,
        )
        self.heartbeat.start()
        self._set_status("Heartbeat Running", COLOR_ACCENT)

    def _start_job_manager(self) -> None:
        if self.client is None:
            return
        if self.job_manager and self.job_manager.is_running():
            return
        self.job_manager = JobManager(
            client=self.client,
            config=self.config,
            on_job_event=self._on_job_event,
            on_auth_failure=self._on_auth_failure,
        )
        self.job_manager.start()

    def _on_job_event(self, event: dict) -> None:
        # Called from a background thread; marshal to the main thread.
        self.root.after(0, self._apply_job_event, event)

    def _apply_job_event(self, event: dict) -> None:
        job_id = event.get("job_id")
        status = event.get("status", "received")
        message = event.get("message", "")
        timestamp = datetime.now().strftime("%H:%M:%S")

        row_id = self._job_row_by_id.get(job_id)
        values = (timestamp, job_id, status, message)
        tag = status if status in STATUS_COLORS else "received"
        if row_id and self.queue_tree.exists(row_id):
            self.queue_tree.item(row_id, values=values, tags=(tag,))
        else:
            row_id = self.queue_tree.insert("", 0, values=values, tags=(tag,))
            self._job_row_by_id[job_id] = row_id

        self.queue_summary_var.set(f"{len(self._job_row_by_id)} job(s) seen this session")
        self._log_message(f"Job {job_id}: {status} - {message}")

    def _on_heartbeat_success(self, result: dict) -> None:
        self.root.after(0, lambda: self._set_status("Heartbeat Running", COLOR_ACCENT))
        pending = result.get("pending_jobs")
        self.root.after(0, lambda: self._log_message(f"Heartbeat OK (pending jobs: {pending})"))

    def _on_heartbeat_failure(self, message: str) -> None:
        self.root.after(0, lambda: self._set_status("Heartbeat retrying...", COLOR_ORANGE))
        self.root.after(0, lambda: self._log_message(f"Heartbeat failed, retrying: {message}"))

    def _on_auth_failure(self, message: str) -> None:
        # JWT rejected server-side; token already cleared by the worker.
        self.jwt_var.set("")
        self.client = None
        if self.job_manager:
            self.job_manager.stop()

        def _notify() -> None:
            self._set_status("Disconnected (auth expired)", COLOR_RED)
            self.sync_btn.config(state="disabled")
            self._log_message(f"Session expired, please reconnect: {message}")
            messagebox.showerror(
                "Session Expired", "Your session expired. Please click Connect again."
            )

        self.root.after(0, _notify)

    def on_close(self) -> None:
        if self.heartbeat:
            self.heartbeat.stop()
        if self.job_manager:
            self.job_manager.stop()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Button handlers - Printers
    # ------------------------------------------------------------------
    def on_sync_printers(self) -> None:
        if self.client is None:
            messagebox.showerror("Error", "Connect first before syncing printers.")
            return

        jwt_token = self.config.get("jwt", "")
        if not jwt_token:
            messagebox.showerror("Error", "No JWT stored. Connect first.")
            return

        client = self.client
        self.sync_btn.config(state="disabled")
        self._log_message("Discovering printers...")
        threading.Thread(
            target=self._sync_printers_worker, args=(client, jwt_token), daemon=True
        ).start()

    def _sync_printers_worker(self, client: OdooApiClient, jwt_token: str) -> None:
        try:
            printers = PrinterDiscovery().discover()
        except PrinterDiscoveryError as exc:
            logger.error("Printer discovery failed: %s", exc)
            self.root.after(0, self._on_sync_printers_error, f"Printer discovery failed: {exc}")
            return

        self.root.after(0, self._populate_printers_tree, printers)
        self.root.after(
            0, self._log_message, f"Discovered {len(printers)} printer(s)."
        )

        try:
            result = client.sync_printers(jwt_token, printers)
        except ApiError as exc:
            logger.error("Printer sync failed: %s", exc.message)
            self.root.after(0, self._on_sync_printers_error, f"Printer sync failed: {exc.message}")
            return

        logger.info("Printer sync response: %s", result)
        self.root.after(0, self._on_sync_printers_success)

    def _populate_printers_tree(self, printers: list) -> None:
        self.printers_tree.delete(*self.printers_tree.get_children())
        for p in printers:
            self.printers_tree.insert("", "end", values=(
                p.get("name", ""), p.get("driver", ""), p.get("status", ""),
                "Yes" if p.get("is_default") else "",
            ))

    def _on_sync_printers_error(self, message: str) -> None:
        self._log_message(message)
        self.sync_btn.config(state="normal")
        messagebox.showerror("Printer Sync Failed", message)

    def _on_sync_printers_success(self) -> None:
        self._log_message("Printer synchronization completed.")
        self.sync_btn.config(state="normal")