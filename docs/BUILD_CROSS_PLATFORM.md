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

The Python core **is** compiled into the desktop bundle since v0.1.1: each
installer carries a PyInstaller freeze of `core/` and Electron launches it
directly. End users need no Python, pip or Node. See
[Bundling Python](#7-bundling-python-now-the-default) — you only need the
toolchain below to *build* the app, not to run it.

**v0.1.1+ Zero-config features baked into builds:**
- Bundled Python core (`resources/core-runtime`) — no system Python required
- Core binds `0.0.0.0:8765` by default → LAN/mobile works instantly
- Windows Firewall rule auto-attempted on first launch
- VC++ Redistributable detection with download URL if missing
- MT5 terminal auto-detection (common paths + registry)
- Asset filenames stamped from the git tag (`AI-TRADER-0.1.1-x64.exe`)

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
py -3.12 core\build_sidecar.py --clean   # bundle the Python core first
cd app
npm run dist:win
```

This runs:

1. `tsc -p tsconfig.electron.json` → `dist-electron/main.js`, `preload.js`
2. `vite build` → `dist/`
3. `electron-builder --win` → `app/release/`

Artifacts:

```
app/release/AI-TRADER-0.1.1-x64.exe          # NSIS installer
app/release/AI-TRADER-0.1.1-x64-portable.exe # portable
```

The version comes from `app/package.json`; CI overwrites it from the git tag so
asset names always match the release.

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

The portable `.exe` unpacks to a temp folder on launch and needs no Python
either — the frozen core travels with it.

---

## 3. macOS

```bash
cd app
npm install
npm run dist:mac
```

Output: `app/release/AI-TRADER-0.1.1-arm64.dmg` (and x64 if you build on Intel or
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

- Bundled as `resources/core-runtime/aitrader-core` (universal per build arch).
- `MetaTrader5` is **not available**. Use the **MetaAPI** adapter for MT5/MT4.
- The frozen core needs no interpreter. For development against
  `resources/core/main.py`, Electron looks for `python3` then `python`; point it
  at a specific one with `AI_TRADER_PYTHON=/opt/homebrew/bin/python3.12`.
- The core data directory becomes
  `~/Library/Application Support/AI-TRADER` (Electron passes its `userData` path).

For development, install core dependencies into the same interpreter:

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

**v0.1.1+**: Core binds `0.0.0.0` by default. If running as a service (systemd),
the Firewall rule is handled by the OS — no Electron auto-rule needed.

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

1. Start the desktop app on the PC (its core binds `0.0.0.0:8765`).
2. If Windows Firewall asks, allow **Private** networks.
3. On the phone: **Settings → Core URL** → `http://<PC-LAN-IP>:8765`.
4. Tap **Connect**.

The APK build already permits cleartext HTTP for that LAN call (see below), so
there is no manifest editing to do.

### Cleartext HTTP on Android

The phone talks to your PC over plain HTTP on the LAN. Android 9+ blocks that by
default, so the CI build injects a permissive network-security config into the
generated project:

```
mobile/android/app/src/main/res/xml/network_security_config.xml
  <base-config cleartextTrafficPermitted="true" />
mobile/android/app/src/main/AndroidManifest.xml
  android:networkSecurityConfig="@xml/network_security_config"
  android:usesCleartextTraffic="true"
```

`mobile/capacitor.config.ts` also sets `android.allowMixedContent: true`, because
the WebView runs on `https://localhost` and the core is `http://192.168.x.x`.

If you build the APK locally instead of via CI, run `npx cap sync android` and
then repeat those two edits — `cap` regenerates the manifest on some upgrades.
For anything beyond a trusted home LAN, use an HTTPS tunnel (Tailscale Funnel,
Cloudflare Tunnel) and drop the cleartext config.

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

## 7. Bundling Python (now the default)

Since v0.1.1 the installers ship a **frozen core** instead of asking users to
install Python:

```
core/build_sidecar.py  →  app/core-runtime/aitrader-core(.exe) + _internal/
                       →  electron-builder extraResources
                       →  <install dir>/resources/core-runtime/
                       →  Electron spawns it on Startup
```

```powershell
py -3.12 core\build_sidecar.py --clean     # Windows
python3 core/build_sidecar.py --clean      # macOS / Linux
```

What is inside: FastAPI, uvicorn, pydantic, httpx, cryptography (Fernet vault),
sqlite, the seed JSON, and — on Windows only — the `MetaTrader5` bridge. Size on
Windows is roughly 100 MB unpacked, which is why the installer grew. `ccxt` is
**not** bundled (≈150 MB extra); set `AI_TRADER_BUNDLE_CCXT=1` if you want it.

### The MCP runtimes (Node.js + uv)

MCP servers are separate programs launched by the core:

| Server kind | Command | Runtime needed |
|-------------|---------|----------------|
| Context7, Playwright, Firecrawl, Tavily, … | `npx` | **Node.js 20+** |
| Fetch, Time, Git, Alpaca, … | `uvx` | **uv** (the Rust Python toolchain) |

Rather than make the user install them, CI downloads both and ships them:

```
app/node/node.exe  +  app/node/npx.cmd  +  app/node/node_modules/npm/…
app/uv/uv.exe      +  app/uv/uvx.exe
                    →  <install dir>/resources/{node,uv}/
```

**`npx.cmd` needs the full npm package.** It resolves
`%~dp0\node_modules\npm\bin\npx-cli.js`, and that script in turn requires
`npm\lib\`. Copying only `npx.cmd` produces a `Cannot find module '../lib/cli.js'`
crash the first time an MCP server starts. The CI step copies the whole
`node_modules/npm` tree.

**`uvx` is a separate binary from `uv`.** The catalog invokes `uvx`, so copying
only `uv.exe` leaves every uv-based server broken.

**On Unix, `npx` must be a wrapper, not Node's `bin/npx`.** Node's Unix
`bin/npx` is a JavaScript shim that resolves `../lib/cli.js` and
`./npm-cli.js` **relative to its own file**. The Unix tarball puts the npm
package at `lib/node_modules/npm`, so copying `bin/npx` next to a flat
`node_modules/npm` breaks those two requires and `npx` dies on the first MCP
server start. The CI step writes a POSIX wrapper instead:

```sh
#!/bin/sh
DIR=$(cd "$(dirname "$0")" && pwd)
exec "$DIR/node" "$DIR/node_modules/npm/bin/npx-cli.js" "$@"
```

That is exactly what `npx.cmd` does on Windows, and it is known to work.

**CI verifies the runtimes twice.** Once against the source folder, and once
against the **packaged** output — a lost executable bit (Unix) or a missing
`.cmd` (Windows) must fail the build, not the user's first MCP server.

At startup the core calls `_setup_bundled_tools()` (`core/main.py`), which puts
`resources/node` and `resources/uv` on `PATH` itself. Electron also injects
them, but the core does not depend on that — it finds the folders relative to
`sys.executable` and works even if it is launched by hand.

### Linux packaging needs a homepage

electron-builder's `deb` target (FPM) refuses to build without a project URL:

```
Error: Please specify project homepage, see https://electron.build/configuration.md#Metadata-homepage
```

`app/package.json` must declare `homepage` (the `repository` fallback does not
apply unless `repository.type` is `github`):

```json
"homepage": "https://github.com/vicky2211-2002/AI-TRADER",
"repository": { "type": "git", "url": "https://github.com/vicky2211-2002/AI-TRADER.git" }
```

Pin `linux.artifactName` too, otherwise the deb is named after the npm package
name (`ai-trader_0.1.4_amd64.deb`) instead of the branded, version-stamped
`AI-TRADER-0.1.4-x64.deb`.

### MetaTrader5 in the frozen core

`MetaTrader5` is a Windows-only native package (a `.pyd`). It must be
installed **in the build environment** or PyInstaller silently drops it and the
Brokers tab says "MetaTrader5 is not importable":

```yaml
- name: Install core dependencies
  run: |
    python -m pip install -r core/requirements.txt pyinstaller
    if [ "${{ runner.os }}" = "Windows" ]; then
      python -m pip install "MetaTrader5>=5.0.45"
    fi

- name: Build frozen core sidecar
  run: |
    python core/build_sidecar.py --clean
    # Fail loudly instead of shipping a broker-less build.
    ls app/core-runtime/_internal/ | grep -qi MetaTrader5 || exit 1
```

The `MetaTrader5` line is commented out in `core/requirements.txt` on purpose —
it has no macOS/Linux build and would break the other two jobs. The Windows job
installs it explicitly and the build fails if it is missing.

**`MetaTrader5` needs `numpy`, and PyInstaller cannot see that.**

`MetaTrader5/__init__.py` does `from ._core import *`, and the native `_core.pyd`
imports numpy from **compiled C code**. PyInstaller's static analysis walks
Python sources only, so it never sees the dependency and silently drops numpy:

```
ModuleNotFoundError: No module named 'numpy'
```

The Brokers tab then says "MetaTrader5 package not installed" even though the
folder is right there in the bundle. This bit the published v0.1.4 Windows
build: the dev machine already had numpy installed, so numpy landed in the
dependency graph by accident, while the CI runner (which installs only
`core/requirements.txt`) produced a core without it.

Two things are required, and both are in place:

- `core/requirements.txt` lists `numpy>=1.26,<3.0; sys_platform == "win32"`.
  It is not optional when the MT5 bridge is bundled.
- `core/build_sidecar.py` adds `--hidden-import numpy` next to
  `--hidden-import MetaTrader5`, so the collection is deliberate rather than an
  accident of the build machine.

### The frozen core must be booted, not just built

Checking that a `MetaTrader5` folder exists is not the same as checking that
the module imports — that is exactly how the numpy bug shipped. The workflow
now has a **"Verify the frozen core"** step that starts the freshly built
core and asks it what it can actually do:

```bash
"$CORE" --port 8799 > core-verify.log 2>&1 &
curl -fsS "http://127.0.0.1:8799/api/system" -o system-verify.json
```

and then asserts that `/api/system` reports `node`, `node_bundled`, `uv` and
`uv_bundled` as true, that `mt5_available` is true on Windows, and that the
core log contains no `ModuleNotFoundError`.

Two portability notes for that step:

- Keep the scratch files **inside the workspace**. An absolute `/tmp` path is
  not portable: on Windows the step's shell is Git Bash (where `/tmp` is a
  Git-Bash-specific folder) while `python` is Windows Python (where `/tmp`
  means `C:\tmp`). `curl` writes to one place and Python looks in another.
- `node_bundled` / `uv_bundled` are the meaningful assertions. The runners
  already have Node.js installed, so a plain "node is there" proves nothing.
  They are only true when the command resolves inside the folder this install
  actually ships (`core/aitrader/tools.py` owns that definition).

**Note:** the MT5 *terminal* (the desktop app) is still not bundled. It is
proprietary, must be installed from your broker, and must be logged into once.
The bridge is bundled; the terminal is the user's to install.

Build rules:

- PyInstaller cannot cross-compile. Build the sidecar on each OS you ship to;
  the CI matrix does exactly that.
- Unsigned sidecars are flagged by SmartScreen/Gatekeeper like the main app. Sign
  both on macOS or the app will be killed on launch.
- `resources/core/main.py` is still shipped as a fallback. If the frozen binary
  is missing or fails to start, Electron falls back to a system Python — useful
  for development, never expected for an end user.
- When adding a new core dependency, re-run the sidecar build; there is no
  auto-discovery.

---

## 8. CI (GitHub Actions)

`.github/workflows/build-all.yml` runs on every `v*` tag (and manually):

| Job | Runner | Output |
|-----|--------|--------|
| Windows | `windows-latest` | `.exe` installer + portable |
| macOS | `macos-latest` | `.dmg` + `.zip` |
| Linux | `ubuntu-latest` | `.deb` + `.tar.gz` |
| Android | `ubuntu-latest` | debug `.apk` |
| Publish | `ubuntu-latest` | replaces the release for that tag with exactly those files |

What the workflow does that a naive one does not:

1. **Stamps the version from the tag** into `app/package.json`,
   `mobile/package.json`, `core/aitrader/__init__.py` and `config.py`, so a
   `v0.1.2` tag can never produce `AI-TRADER-0.1.1-*.exe`.
2. **Builds the frozen core** with `core/build_sidecar.py` before packaging.
3. **Collects** whatever electron-builder produced and fails the job with the
   last 100 log lines when a platform produced nothing.
4. **Deletes the previous release for the tag** before uploading, so stale assets
   from an earlier failed run cannot survive.
5. **Writes release notes from the files that actually exist**, and warns which
   platforms are missing instead of advertising downloads that 404.

Tag a release with:

```powershell
git tag v0.1.2
git push origin v0.1.2
```

---

## 9. Release checklist

- [ ] `pytest core/tests -q` green
- [ ] `npx tsc -p tsconfig.json --noEmit` clean
- [ ] `npm run build` succeeds
- [ ] `python core/build_sidecar.py --clean` runs, and the frozen core answers
      `/api/health` on a spare port
- [ ] Version bumped in `app/package.json`, `core/aitrader/__init__.py`,
      `core/aitrader/config.py`, `mobile/package.json` (CI re-stamps from the tag)
- [ ] Icons present in `app/build/`
- [ ] No `.env`, key, `vault.key`, DB or log in the repo
- [ ] `cryptography` is a documented dependency
- [ ] Installer tested on a **clean** VM with **no Python installed**: the window
      must open and `/api/health` must answer
- [ ] Smoke test: add provider → test → chat → paper order → approve → close
- [ ] README and docs screenshots/commands still accurate

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Window opens, "Core offline" | Bundled core failed to start | Check `%APPDATA%\AI-TRADER\logs\core.log`; the first lines name the missing DLL or port clash |
| `Core not found at ...\resources\core\main.py` | Neither `core-runtime` nor core sources were packaged | Rebuild; verify `resources/core-runtime/aitrader-core.exe` exists |
| Blank white window in production | `base` not relative or `loadFile` path wrong | Keep `base: "./"`; check `dist/index.html` exists |
| `spawn py ENOENT` | A dev build without `core-runtime`, and no Python on PATH | Run `core/build_sidecar.py`, or install Python and set `AI_TRADER_PYTHON` |
| Antivirus quarantines `aitrader-core.exe` | Unsigned PyInstaller binary | Sign the app + sidecar, or allow the folder |
| Installer is ~200 MB | Frozen Python core + Electron | Expected; `ccxt` is excluded to keep it down |
| Android app can't reach core | Firewall / wrong IP / `127.0.0.1` | Use the PC's LAN IP, allow port 8765, keep the desktop app open |
| Gradle can't find SDK | `ANDROID_HOME` unset | Set it or create `android/local.properties` |
| macOS "app is damaged" | Quarantine / unsigned | `xattr -dr com.apple.quarantine AI-TRADER.app`, or notarise |
| electron-builder fails on symlinks (Windows) | Developer Mode off | Enable Developer Mode or run as admin |
| **Firewall dialog doesn't appear** | Rule already exists | Core adds rule silently; check `netsh advfirewall firewall show rule name="AI-TRADER Core"` |
| **MT5 path not auto-filled** | Terminal in a non-standard location | Set manually in Brokers tab; core logs checked paths |
| **VC++ missing warning** | Redistributable not installed | Install from `https://aka.ms/vs/17/release/vc_redist.x64.exe` |

---

## Related docs

- [`../mobile/README.md`](../mobile/README.md) — Android/iOS detail
- [`ARCHITECTURE.md`](../ARCHITECTURE.md) — what the Electron shell actually does
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — runtime issues