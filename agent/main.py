"""Entry point for Kits Direct Print Agent."""

import sys
import tkinter as tk

from config import ConfigManager
from logger import get_logger
from gui import AgentGUI

logger = get_logger(__name__)


def main() -> None:
    logger.info("Application Started")

    try:
        config = ConfigManager()
        logger.info("Configuration Loaded: uuid=%s", config.get("uuid"))

        root = tk.Tk()
        AgentGUI(root, config)
        root.mainloop()
    except Exception:
        # Without this, a crash before/during mainloop just closes the
        # window silently with nothing in the log to explain why.
        logger.exception("Fatal error, agent is shutting down")
        raise
    finally:
        logger.info("Application Stopped")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        print(f"Kits Direct Print Agent crashed: {exc}", file=sys.stderr)
        sys.exit(1)