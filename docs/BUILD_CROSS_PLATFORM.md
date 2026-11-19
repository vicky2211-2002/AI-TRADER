# Build and ship AI-TRADER

Three artifacts come from one codebase:

| Target | Wrapper | Output |
|--------|---------|--------|
| Windows | Electron | `.exe` installer (NSIS) + portable `.exe` |
| macOS | Electron | `.dmg` + `.zip` |
| Linux | Electron | `.AppImage` + `.deb` |
| Browser | Vite | `app/dist/` served by any static host |
| Android | Capacitor | `.apk` / `.aab` |
| iOS | Capacitor | `.ipa` (macOS + Xcode only) |

The Python core is **not** compiled into the Electron bundle in 0.1.0. The
packaged app ships the core source and launches a system Python. See
[Bundling Python](#bundling-python) for the trade-offs and the upgrade path.

---

## 0. Prerequisites

| Tool | Version | Needed for |
|------|---------|------------|
| Node.js | 20+ | UI, Electron, Capacitor |
| npm | 10+ | dependency install |
| Python | 3.11/3.12 | core |
| Git | any | clone/update |
| Android Studio + JDK 17 | latest | APK |
| Xcode 15+ | macOS only | iOS/macOS signing |

```powershell
cd AI-TRADER
py -3.12 -m pip install -r core\requirements.txt
cd app
npm install
```

Add optional broker/runtime dependencies on the build machine:

```powershell
py -3.12 -m pip install MetaTrader5   # Windows only
py -3.12 -m pip install ccxt          # crypto
```

---

## 1. Web build (always first)

```powershell
cd app
npm run build:web
```

Output: `app/dist/index.html` + hashed assets. Electron, Capacitor and any static
host consume this folder.

Sanity checks:

```powershell
npx tsc -p tsconfig.json --noEmit
npm run build:web
```

`base: "./"` in `vite.config.ts` keeps asset paths relative, which is required for
`file://` loading in Electron and the Capacitor WebView.

---

## 2. Windows desktop

```powershell
cd app
npm run dist:win
```

This runs:

1. `tsc -p tsconfig.electron.json` → `dist-electron/main.js`, `preload.js`
2. `vite build` → `dist/`
3. `electron-builder --win` → `app/release/`

Artifacts:

```
app/release/AI-TRADER-0.1.0-x64.exe          # NSIS installer
app/release/AI-TRADER-0.1.0-x64-portable.exe # portable
```

NSIS options are in `package.json → build.nsis`: install directory is selectable,
desktop shortcut is created, one-click is off.

### Icons and metadata

Put these in `app/build/` before a release build:

```
app/build/icon.ico      # 256x256 multi-size, Windows
app/build/icon.icns     # macOS
app/build/icon.png      # 512x512 or 1024x1024, Linux
```

electron-builder falls back to the default Electron icon if they are missing —
fine for internal builds, not for distribution.

### Code signing (optional but recommended)

Unsigned installers trigger SmartScreen. With an EV/OV certificate:

```powershell
$env:CSC_LINK="C:\certs\aitrader.pfx"
$env:CSC_KEY_PASSWORD="..."
npm run dist:win
```

Or configure `build.win.certificateFile` / `certificatePassword` (use environment
variables in CI, never commit them).

### Portable caveat

The portable `.exe` still needs Python on the target machine. If that is not
acceptable, see [Bundling Python](#bundling-python).

---

## 3. macOS

```bash
cd app
npm install
npm run dist:mac
```

Output: `app/release/AI-TRADER-0.1.0-arm64.dmg` (and x64 if you build on Intel or
pass `--x64`).

Unsigned apps need a right-click → Open the first time. For distribution:

```bash
export CSC_LINK="/path/to/DeveloperIDApplication.p12"
export CSC_KEY_PASSWORD="..."
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="app-specific-password"
export APPLE_TEAM_ID="TEAMID1234"
npm run dist:mac
```

Notarisation is handled by electron-builder when the Apple env vars are present.
Without notarisation, Gatekeeper blocks the app on other Macs.

### Core on macOS

- `MetaTrader5` is **not available**. Use the **MetaAPI** adapter for MT5/MT4.
- The Electron shell looks for `python3` then `python`. Point it at a specific
  interpreter with `AI_TRADER_PYTHON=/opt/homebrew/bin/python3.12`.
- The core data directory becomes
  `~/Library/Application Support/AI-TRADER` (Electron passes its `userData` path).

Install core dependencies into the same interpreter:

```bash
/opt/homebrew/bin/python3.12 -m pip install -r core/requirements.txt
```

---

## 4. Linux

```bash
cd app
npm run dist:linux
```

Outputs `AppImage` and `.deb` in `app/release/`. AppImage needs `libfuse2` on some
distros.

---

## 5. Android APK

Full walkthrough: [`../mobile/README.md`](../mobile/README.md).

Short version:

```powershell
cd app
npm run build:web

cd ..\mobile
npm install
npx cap add android      # once
npx cap sync android
cd android
.\gradlew.bat assembleDebug
```

APK:

```
mobile/android/app/build/outputs/apk/debug/app-debug.apk
```

Install:

```powershell
adb install -r mobile\android\app\build\outputs\apk\debug\app-debug.apk
```

### Connect to the core

1. Start the core with `--lan` and a token.
2. Enter `http://<pc-lan-ip>:8765` on the app's offline screen.
3. Add the token in Settings.

### Cleartext HTTP on Android

Android 9+ blocks plain HTTP. Options:

- **Best:** use an HTTPS tunnel (Tailscale Funnel, Cloudflare Tunnel) and an
  `https://` core URL. Nothing to change in the app.
- **LAN only:** add `android/app/src/main/res/xml/network_security_config.xml`:

  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <network-security-config>
    <domain-config cleartextTrafficPermitted="true">
      <domain includeSubdomains="false">192.168.1.42</domain>
    </domain-config>
  </network-security-config>
  ```

  Reference it from `AndroidManifest.xml`:

  ```xml
  <application
      android:networkSecurityConfig="@xml/network_security_config"
      ... >
  ```

Never enable global cleartext for a released build.

### Release signing

```powershell
keytool -genkeypair -v -keystore mobile\android\aitrader-release.jks `
  -alias aitrader -keyalg RSA -keysize 2048 -validity 10000
```

`mobile/android/key.properties` (git-ignored):

```properties
storeFile=../../aitrader-release.jks
storePassword=...
keyAlias=aitrader
keyPassword=...
```

Wire it into `android/app/build.gradle` signing configs, then:

```powershell
cd mobile\android
.\gradlew.bat bundleRelease
```

Upload `app/build/outputs/bundle/release/app-release.aab` to Play Console, or use
`assembleRelease` for a signed APK for internal distribution.

---

## 6. iOS

On macOS only:

```bash
cd app && npm run build:web
cd ../mobile
npm install
npx cap add ios
npx cap sync ios
npx cap open ios
```

Set the team and bundle id in Xcode, pick a device, Run. For TestFlight, Product →
Archive → Distribute App.

The phone cannot run `npx`/`uvx` MCP servers. Use HTTP MCP servers or keep the
tool work on the core host.

---

## 7. Bundling Python

Current behavior: Electron ships `core/**/*.py` as a resource and spawns
`py -3.12` / `python3`. Target machines need Python + `requirements.txt`.

Why it is done this way in 0.1.0:

- `MetaTrader5` is a Windows-only native package; bundling it blindly breaks
  macOS/Linux.
- Users often already have a Python they trust.
- A frozen core makes MCP `npx`/`uvx` children and debugging harder.

Upgrade path (recommended before public distribution):

1. Build a **core sidecar** with PyInstaller on each OS:

   ```powershell
   pyinstaller --noconfirm --onedir --name aitrader-core `
     --add-data "core\seed;seed" `
     --add-data "skills;skills" `
     core\main.py
   ```

2. Copy `dist/aitrader-core/` into `app/resources/core-runtime/`.
3. In `electron/main.ts`, prefer `path.join(process.resourcesPath,
   "core-runtime", "aitrader-core(.exe)")` and fall back to Python.
4. Build per-platform (Windows on Windows, macOS on macOS) because PyInstaller
   does not cross-compile.

Alternatively use `uv` to vendor a relocatable interpreter. Either way, sign the
sidecar on macOS or Gatekeeper will kill it.

---

## 8. CI outline (GitHub Actions)

```yaml
name: build
on: [push, workflow_dispatch]
jobs:
  core:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r AI-TRADER/core/requirements-dev.txt
      - run: pytest AI-TRADER/core/tests -q
        env: { AI_TRADER_HOME: /tmp/aitrader }

  ui:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: AI-TRADER/app } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: npm, cache-dependency-path: AI-TRADER/app/package-lock.json }
      - run: npm ci
      - run: npx tsc -p tsconfig.json --noEmit
      - run: npm run build
```

Desktop artifacts need a matrix of `windows-latest`, `macos-latest`,
`ubuntu-latest`, with signing secrets injected as environment variables.

---

## 9. Release checklist

- [ ] `pytest core/tests -q` green
- [ ] `npx tsc -p tsconfig.json --noEmit` clean
- [ ] `npm run build` succeeds
- [ ] Version bumped in `app/package.json`, `core/aitrader/__init__.py`,
      `mobile/package.json`
- [ ] Icons present in `app/build/`
- [ ] No `.env`, key, `vault.key`, DB or log in the repo
- [ ] `cryptography` is a documented dependency
- [ ] Installer tested on a **clean** VM (no Python) to confirm the expected
      dependency message
- [ ] Smoke test: add provider → test → chat → paper order → approve → close
- [ ] README and docs screenshots/commands still accurate

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Window opens, “Core offline” | Python deps missing or wrong interpreter | Check `%APPDATA%\AI-TRADER\logs\core.log`; set `AI_TRADER_PYTHON` |
| `Core not found at ...\resources\core\main.py` | `extraResources` didn’t copy | Rebuild; verify `app/release/win-unpacked/resources/core/main.py` |
| Blank white window in production | `base` not relative or `loadFile` path wrong | Keep `base: "./"`; check `dist/index.html` exists |
| `spawn py ENOENT` | Python not on PATH | Install Python or set `AI_TRADER_PYTHON` |
| Android app can’t reach core | Firewall / wrong IP / `127.0.0.1` | Use LAN IP, allow port, bind `0.0.0.0`, token |
| Gradle can’t find SDK | `ANDROID_HOME` unset | Set it or create `android/local.properties` |
| macOS “app is damaged” | Quarantine / unsigned | `xattr -dr com.apple.quarantine AI-TRADER.app`, or notarise |
| electron-builder fails on symlinks (Windows) | Developer Mode off | Enable Developer Mode or run as admin |

---

## Related docs

- [../mobile/README.md](../mobile/README.md) — Android/iOS detail
- [ARCHITECTURE.md](../ARCHITECTURE.md) — what the Electron shell actually does
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — runtime issues
