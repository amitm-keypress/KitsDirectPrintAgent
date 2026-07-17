"""Configuration management for Kits Direct Print Agent."""

import json
import uuid
import platform
from pathlib import Path
from typing import Any, Dict

APP_DATA_DIR = Path.home() / ".kits_direct_print_agent"
CONFIG_PATH = APP_DATA_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "uuid": "",
    "odoo_url": "",
    "token": "",
    "jwt": "",
    "machine_id": "",
    "heartbeat_interval": 30,
    "hostname": platform.node(),
    "os_type": platform.system(),
    "os_version": platform.version(),
    "agent_version": "1.0.0",
}


class ConfigManager:
    """Loads, saves, and provides access to agent configuration."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load config from disk, creating defaults with a fresh UUID if missing."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.data = {**DEFAULT_CONFIG, **loaded}
            except (json.JSONDecodeError, OSError):
                self.data = dict(DEFAULT_CONFIG)
        else:
            self.data = dict(DEFAULT_CONFIG)

        if not self.data.get("uuid"):
            self.data["uuid"] = str(uuid.uuid4())

        # keep host/os info fresh each run
        self.data["hostname"] = platform.node()
        self.data["os_type"] = platform.system()
        self.data["os_version"] = platform.version()

        self.save()
        return self.data

    def save(self) -> None:
        """Persist current config to disk."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def update(self, values: Dict[str, Any]) -> None:
        self.data.update(values)
        self.save()
