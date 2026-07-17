# Kits Direct Print Agent

Desktop client for Odoo 18 `kits_direct_print` module. Talks to existing
Odoo REST APIs only — no Odoo-side code here.

## Phase 1 (this delivery)

- Config load/save (`config.json`), auto UUID generation
- Logging (rotating file `logs/agent.log`)
- GUI: Odoo URL, Token, UUID (read-only), JWT (read-only)
- Buttons: Connect, Sync Printers (disabled until Phase 3), Save, Test Connection
- `POST /kits/direct_print/v1/register` wired up end-to-end

## Setup

```bash
cd agent
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Usage

1. Enter Odoo URL (e.g. `http://localhost:8069`) and Token.
2. Click **Save** to persist config.
3. Click **Test Connection** to verify the server is reachable.
4. Click **Connect** to register the agent and obtain a JWT.
5. On success, JWT/machine ID/heartbeat interval are stored in `config.json`
   and status changes to "Connected".

## Files

| File | Purpose |
|---|---|
| `main.py` | Entry point, launches GUI |
| `config.py` | Loads/saves `config.json`, generates UUID on first run |
| `logger.py` | Rotating file + console logger |
| `api.py` | REST client for all `/kits/direct_print/v1/*` endpoints |
| `gui.py` | Tkinter GUI |
| `config.json` | Persisted agent config |
| `logs/agent.log` | Rotating application log |

## Next phases

- Phase 2: Heartbeat background thread (`heartbeat.py`)
- Phase 3: Printer discovery + sync (`printer.py`)
- Phase 4: Job polling (`jobs.py`)
