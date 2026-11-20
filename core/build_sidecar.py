"""Build the frozen Python core ("sidecar") that ships inside the installers.

Why this exists
---------------
Historically the Electron app shipped ``core/*.py`` and spawned whatever
``python`` happened to be on the user's machine. On a clean Windows box that
means "install Python 3.12 + pip install -r requirements.txt" before the app
works at all -- exactly the manual step end users should never see.

This script freezes the core with PyInstaller into ``app/core-runtime/`` so
``electron-builder`` can copy it into ``resources/core-runtime``. Electron
prefers that binary and only falls back to a system Python when it is missing.

Usage
-----
    py -3.12 core/build_sidecar.py            # build
    py -3.12 core/build_sidecar.py --clean    # wipe previous output first

Output
------
    app/core-runtime/aitrader-core.exe   (Windows)
    app/core-runtime/aitrader-core       (macOS / Linux)
    + app/core-runtime/_internal/...     (bundled libraries)

Notes
-----
* PyInstaller does not cross-compile. Build on the OS you ship to.
* ``MetaTrader5`` is bundled on Windows only (the package has no other build).
* ``ccxt`` is NOT bundled by default (it is ~150 MB). Set
  ``AI_TRADER_BUNDLE_CCXT=1`` to include it.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent
APP_DIR = CORE_DIR.parent / "app"
OUT_DIR = APP_DIR / "core-runtime"
NAME = "aitrader-core"


def _data_sep() -> str:
    return ";" if os.name == "nt" else ":"


def _hidden_imports() -> list[str]:
    imports = [
        # uvicorn picks its event loop / protocol implementation at runtime.
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "email.mime.multipart",
        "email.mime.text",
        "sqlite3",
    ]
    if os.name == "nt":
        imports.append("MetaTrader5")
    if os.environ.get("AI_TRADER_BUNDLE_CCXT") == "1":
        imports.append("ccxt")
    return imports


def main() -> int:
    if "--clean" in sys.argv:
        shutil.rmtree(CORE_DIR / "build", ignore_errors=True)
        shutil.rmtree(CORE_DIR / "dist", ignore_errors=True)
        # Wipe only generated payload; keep the folder's README in git.
        if OUT_DIR.exists():
            for child in OUT_DIR.iterdir():
                if child.name == "README.md":
                    continue
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)

    cmd: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        NAME,
        "--distpath",
        str(CORE_DIR / "dist"),
        "--workpath",
        str(CORE_DIR / "build"),
        "--specpath",
        str(CORE_DIR / "build"),
        "--add-data",
        f"{CORE_DIR / 'seed'}{_data_sep()}seed",
        "--collect-submodules",
        "uvicorn",
        "--collect-submodules",
        "fastapi",
    ]
    for name in _hidden_imports():
        cmd += ["--hidden-import", name]
    cmd.append(str(CORE_DIR / "main.py"))

    print("[sidecar] " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(CORE_DIR))
    if result.returncode != 0:
        print("[sidecar] PyInstaller failed", file=sys.stderr)
        return result.returncode

    built = CORE_DIR / "dist" / NAME
    if not built.exists():
        print(f"[sidecar] expected output missing: {built}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Replace only the generated payload, never stray files a human added.
    for child in built.iterdir():
        target = OUT_DIR / child.name
        if child.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)

    exe = OUT_DIR / (f"{NAME}.exe" if os.name == "nt" else NAME)
    if not exe.exists():
        print(f"[sidecar] missing executable: {exe}", file=sys.stderr)
        return 1

    size_mb = sum(p.stat().st_size for p in OUT_DIR.rglob("*") if p.is_file()) / (1024 * 1024)
    print(f"[sidecar] built {exe} ({size_mb:.1f} MB) on {platform.system()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
