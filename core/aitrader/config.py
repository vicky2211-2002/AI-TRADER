"""AI-TRADER core configuration.

All runtime state lives outside the source tree by default:
  Windows : %APPDATA%\\AI-TRADER
  macOS   : ~/Library/Application Support/AI-TRADER
  Linux   : ~/.local/share/AI-TRADER

Override with AI_TRADER_HOME (recommended for portable installs).
"""
from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
CORE_DIR = PACKAGE_DIR.parent
PROJECT_DIR = CORE_DIR.parent


def _default_home() -> Path:
    override = os.environ.get("AI_TRADER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "AI-TRADER"
    if os.uname().sysname == "Darwin":  # type: ignore[attr-defined]
        return Path.home() / "Library" / "Application Support" / "AI-TRADER"
    return Path.home() / ".local" / "share" / "AI-TRADER"


HOME_DIR: Path = _default_home()
DATA_DIR: Path = HOME_DIR / "data"
SKILLS_DIR: Path = Path(os.environ.get("AI_TRADER_SKILLS", PROJECT_DIR / "skills"))
SEED_DIR: Path = CORE_DIR / "seed"

for _p in (HOME_DIR, DATA_DIR):
    _p.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "aitrader.db"

# Bind to 0.0.0.0 by default so LAN/mobile works out of the box.
# Override with AI_TRADER_HOST=127.0.0.1 for localhost-only.
HOST = os.environ.get("AI_TRADER_HOST", "0.0.0.0")
PORT = int(os.environ.get("AI_TRADER_PORT", "8765"))
TOKEN = os.environ.get("AI_TRADER_TOKEN", "")

APP_NAME = "AI-TRADER"
APP_VERSION = "0.1.2"
API_PREFIX = "/api"

# Origins allowed to call the local core. Electron file:// sends "null".
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "capacitor://localhost",
    "http://localhost",
    "ionic://localhost",
    "file://",
    "null",
]

# Safety defaults. These are intentionally conservative: paper trading only,
# human approval for every order, hard daily loss cap.
SAFE_DEFAULTS = {
    "trading_mode": "paper",          # paper | demo | live
    "allow_live_trading": False,
    "require_order_approval": True,
    "kill_switch": False,
    "max_risk_per_trade_pct": 1.0,
    "max_daily_loss_pct": 2.0,
    "max_drawdown_pct": 8.0,
    "max_open_positions": 2,
    "max_lot_size": 0.10,
    "max_spread_points": 40,
    "default_symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"],
    "auto_execute_tools": False,
    # Autonomous mode (disabled until the operator presses Start).
    "autopilot_enabled": False,
    "autopilot_autostart": False,
    "autopilot_interval_sec": 300,
    "autopilot_symbols": [],
    "autopilot_symbols_per_cycle": 2,
    "autopilot_provider_ids": [],
    "autopilot_execution": "auto",       # auto | approval
    "autopilot_confidence": 0.55,
    "autopilot_max_trades_per_day": 6,
    "autopilot_sl_atr": 2.0,
    "autopilot_tp_atr": 4.0,
    "autopilot_cooldown_sec": 900,
    "autopilot_allow_live_auto": False,
}
