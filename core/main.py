"""Entry point: python -m aitrader  (or: python core/main.py)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from aitrader.api import app  # noqa: E402
from aitrader.config import HOST, PORT  # noqa: E402


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
    uvicorn.run(app, host=host, port=args.port, log_level="info", reload=args.reload)


if __name__ == "__main__":
    main()
