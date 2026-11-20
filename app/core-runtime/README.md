# core-runtime

This folder receives the **frozen Python core** produced by
`core/build_sidecar.py` (PyInstaller). `electron-builder` copies it into
`resources/core-runtime/` inside the installed app, and Electron spawns it
directly — no system Python required.

The binaries are platform-specific build output and are ignored by `.gitignore`;
only this README is tracked.

```
py -3.12 core/build_sidecar.py --clean   # Windows → aitrader-core.exe
python3 core/build_sidecar.py --clean    # macOS/Linux → aitrader-core
```

If the folder is empty (dev checkouts), Electron falls back to launching
`core/main.py` with the system Python.
