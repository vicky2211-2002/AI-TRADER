"""Entry point: python -m aitrader  (or: python core/main.py)."""
from __future__ import annotations

import argparse
import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from aitrader.api import app  # noqa: E402
from aitrader.config import HOST, PORT  # noqa: E402
from aitrader.tools import bundled_tool_dirs  # noqa: E402


def _setup_windows_firewall() -> None:
    """Add Windows Firewall rule for port 8765 (run once)."""
    if os.name != "nt":
        return
    try:
        # Check if rule already exists
        check = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=AI-TRADER Core"],
            capture_output=True, text=True, timeout=5
        )
        if "AI-TRADER Core" in check.stdout:
            return
        # Add rule (requires admin, but we try silently)
        subprocess.run(
            [
                "netsh", "advfirewall", "firewall", "add", "rule",
                "name=AI-TRADER Core",
                "dir=in",
                "action=allow",
                "protocol=TCP",
                "localport=8765",
                "profile=private,domain",
                "description=AI-TRADER trading core API"
            ],
            capture_output=True, timeout=10
        )
    except Exception:
        pass  # Non-fatal - user can allow manually


def _check_vc_redist() -> bool:
    """Check if VC++ Redistributable is installed."""
    if os.name != "nt":
        return True
    try:
        # Check for VC++ 2015-2022 redistributable
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64")
        winreg.QueryValueEx(key, "Installed")
        return True
    except Exception:
        return False


def _find_mt5_terminal() -> str | None:
    """Find MT5 terminal64.exe on Windows."""
    if os.name != "nt":
        return None
    common_paths = [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\*\terminal64.exe"),
    ]
    for p in common_paths:
        if "*" in p:
            import glob
            matches = glob.glob(p)
            if matches:
                return matches[0]
        elif os.path.exists(p):
            return p
    return None


def _ensure_mt5_account_setup() -> dict:
    """Return MT5 setup info for UI guidance."""
    mt5_path = _find_mt5_terminal()
    return {
        "mt5_found": mt5_path is not None,
        "mt5_path": mt5_path,
        "vcpp_ok": _check_vc_redist(),
    }


def _bundled_tool_dirs() -> list[str]:
    """Locate the Node.js / uv folders that ship inside the installer.

    See ``aitrader.tools`` for the layout and the search order. The API
    layer uses the same helper, so the UI and the runtime can never
    disagree about what is bundled.
    """
    return bundled_tool_dirs()


def _setup_bundled_tools() -> None:
    """Put the bundled Node.js and uv on PATH so MCP servers work instantly.

    Without this, a clean machine has no ``npx`` and no ``uvx`` and every MCP
    server fails with "command not found". The installer ships both, so the
    core wires them up itself instead of relying on the parent process.
    """
    folders = _bundled_tool_dirs()
    if not folders:
        return
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    for folder in folders:
        if folder not in parts:
            parts.insert(0, folder)
    os.environ["PATH"] = os.pathsep.join(parts)
    print(f"[tools] bundled runtimes on PATH: {', '.join(folders)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-TRADER local core")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--lan", action="store_true", help="Bind 0.0.0.0 so phones on your LAN can connect")
    args = parser.parse_args()
    host = "0.0.0.0" if args.lan else args.host
    if host != "127.0.0.1" and not os.environ.get("AI_TRADER_TOKEN"):
        print("WARNING: binding to the network without AI_TRADER_TOKEN set is unsafe.")

    # Make the bundled Node.js (npx) and uv (uvx) reachable before anything
    # tries to spawn an MCP server.
    _setup_bundled_tools()

    # Windows auto-setup (non-blocking)
    if os.name == "nt":
        _setup_windows_firewall()
        mt5_info = _ensure_mt5_account_setup()
        if not mt5_info["vcpp_ok"]:
            print("NOTE: VC++ Redistributable not detected. If app fails to start, install:")
            print("  https://aka.ms/vs/17/release/vc_redist.x64.exe")
        if not mt5_info["mt5_found"]:
            print("NOTE: MetaTrader 5 terminal not found. Install from your broker,")
            print("      log in once, and enable: Tools > Options > Expert Advisors > Allow algorithmic trading")

    uvicorn.run(app, host=host, port=args.port, log_level="info", reload=args.reload)


if __name__ == "__main__":
    main()