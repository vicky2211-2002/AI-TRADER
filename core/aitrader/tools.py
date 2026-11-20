"""Locate the Node.js / uv runtimes that ship inside the installer.

Layout in a packaged install::

    <install>/resources/core-runtime/aitrader-core.exe   <- we are here
    <install>/resources/node/node.exe, npx.cmd
    <install>/resources/uv/uv.exe, uvx.exe

The tool folders are *siblings* of ``core-runtime`` inside the same
``resources`` folder, which is exactly where Electron puts them
(``process.resourcesPath/node`` and ``process.resourcesPath/uv``). In a dev
checkout nothing matches, so the system PATH is used instead.

Both ``core/main.py`` (which puts the folders on PATH) and
``core/aitrader/api.py`` (which reports whether a command came from the
bundle) use this module, so "is it bundled?" has exactly one definition.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Folder names that hold the bundled runtimes.
TOOL_FOLDERS = ("node", "uv")


def bundled_tool_dirs() -> list[str]:
    """Absolute paths of the bundled ``node`` / ``uv`` folders, if any."""
    dirs: list[str] = []

    # sys.executable is the frozen binary; its parent is core-runtime/.
    exe_dir = Path(sys.executable).resolve().parent
    # Dev fallback: core/aitrader/tools.py -> <repo>/core -> <repo>
    dev_root = Path(__file__).resolve().parents[2]

    bases = [
        exe_dir,                # <resources>/core-runtime/node (unlikely but cheap)
        exe_dir.parent,         # <resources>/node          <- packaged install
        dev_root,               # <repo>/node              <- dev checkout
    ]
    for base in bases:
        for name in TOOL_FOLDERS:
            folder = base / name
            if folder.is_dir() and str(folder) not in dirs:
                dirs.append(str(folder))
    return dirs


def is_bundled_command(resolved: Path) -> bool:
    """True when ``resolved`` lives in one of the bundled tool folders.

    The check is a positive match against the folders this install actually
    ships. It deliberately does not accept "the parent directory exists" --
    that is true for almost every path on disk and would report a system
    Node.js install as a bundled one.
    """
    try:
        parent = resolved.resolve().parent
    except Exception:
        return False
    for folder in bundled_tool_dirs():
        try:
            if parent == Path(folder).resolve():
                return True
        except Exception:
            continue
    return False
