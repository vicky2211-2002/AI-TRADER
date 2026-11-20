# AI-TRADER — Mobile (Android / iOS)

The APK does **not** contain the trading core. It is a thin Capacitor shell around
the same React UI that Electron loads, pointed at a Python core running on your
computer, a VPS, or a private tunnel.

```
Phone (Capacitor WebView)  ──HTTPS/HTTP──▶  Python core (FastAPI :8765)
                                              ├─ MT5 local (Windows only)
                                              ├─ MetaAPI cloud (any OS)
                                              └─ local SQLite + vault
```

Read [`../docs/BUILD_CROSS_PLATFORM.md`](../docs/BUILD_CROSS_PLATFORM.md) for the
full signed-build walkthrough and [`../docs/SECURITY_AND_RISK.md`](../docs/SECURITY_AND_RISK.md)
before exposing the core to a network.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 20+ | `node --version` |
| Android Studio | Hedgehog+ | Includes SDK 34, build tools, platform-tools |
| JDK | 17 | Bundled with Android Studio |
| Python | 3.11/3.12 | Only for the core, not the APK |
| `adb` | platform-tools | `adb devices` must list the phone |

Set `ANDROID_HOME` (Windows: `%LOCALAPPDATA%\Android\Sdk`) and make sure
`%ANDROID_HOME%\platform-tools` is on `PATH`.

---

## First build

```powershell
# 1. from the repo root: build the shared UI
cd app
npm install
npm run build:web

# 2. install the Capacitor shell
cd ..\mobile
npm install

# 3. generate the Android project (once)
npx cap add android

# 4. copy the web bundle + plugins into it
npx cap sync android

# 5. build a debug APK
cd android
.\gradlew.bat assembleDebug
```

Output:

```
mobile/android/app/build/outputs/apk/debug/app-debug.apk
```

Install it:

```powershell
adb install -r mobile\android\app\build\outputs\apk\debug\app-debug.apk
```

Or open the project in Android Studio:

```powershell
cd mobile
npx cap open android
```

---

## Point the app at your core

1. Start the desktop app on the PC. Its bundled core already binds `0.0.0.0:8765`.
   For a bare dev core:

   ```powershell
   cd core
   $env:AI_TRADER_HOST="0.0.0.0"
   $env:AI_TRADER_TOKEN="pick-a-long-random-token"
   py -3.12 main.py
   ```

2. Find the PC's LAN IP: `ipconfig` → IPv4 address, e.g. `192.168.1.42`.
3. Allow inbound TCP 8765 in Windows Firewall (Private network only).
4. Open the app. The **Core offline** screen asks for a URL — enter
   `http://192.168.1.42:8765` and the token from Settings.

`127.0.0.1` on the phone means *the phone*, so it can never reach the PC.

The URL and token are stored in the WebView's `localStorage` on the device.

> Android 9+ blocks cleartext HTTP by default. `mobile/capacitor.config.ts` sets
> `android.allowMixedContent: true`, and the CI build injects a permissive
> network-security config so the LAN call works. For anything beyond a trusted
> home network, use an HTTPS tunnel instead.

---

## Rebuilding after UI changes

```powershell
cd app
npm run build:web
cd ..\mobile
npx cap sync android
```

`npm run mobile:sync` from `app/` does both steps.

---

## Release APK / AAB

```powershell
keytool -genkeypair -v -keystore android\aitrader-release.jks `
  -alias aitrader -keyalg RSA -keysize 2048 -validity 10000
```

Add to `android/gradle.properties` (never commit the file):

```properties
AITRADER_STORE_FILE=../aitrader-release.jks
AITRADER_STORE_PASSWORD=...
AITRADER_KEY_ALIAS=aitrader
AITRADER_KEY_PASSWORD=...
```

Then `.\gradlew.bat bundleRelease` and upload the `.aab` to Play Console, or
`assembleRelease` for a signed APK for internal distribution.

---

## iOS (macOS only)

```bash
cd mobile
npm install
npx cap add ios
npx cap sync ios
npx cap open ios
```

Set your team and bundle id in Xcode, then run on a device. Capacitor iOS needs
Xcode 15+ and CocoaPods.

---

## What you get on a phone

| Works | Does not work |
|-------|---------------|
| Chat, analysis, skills, MCP tools | Local MT5 terminal (Windows-only bridge) |
| Approvals, order proposals, risk gate | Starting the Python core from inside the app |
| Broker accounts via MetaAPI / OANDA / Alpaca / CCXT | Running `npx`-based MCP servers on the phone |
| Paper trading | Keyring-backed vault (vault lives on the core host) |

The risk engine, vault and broker adapters always run on the core host. The phone
is a remote control, never the thing that holds the broker password.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Blank screen after install | Re-run `npx cap sync android`; confirm `../app/dist/index.html` exists |
| `webDir` not found | `cd ../app && npm run build:web` first |
| `SDK location not found` | Set `ANDROID_HOME`, or create `android/local.properties` with `sdk.dir=C\:\\Users\\you\\AppData\\Local\\Android\\Sdk` |
| Core offline on Wi-Fi | Same subnet, desktop app open, firewall allows 8765, correct LAN IP (not `127.0.0.1`) |
| `CLEARTEXT communication not permitted` | Rebuild through CI (it injects the config), or add a network-security config manually |
| Gradle out of memory | Add `org.gradle.jvmargs=-Xmx4g` to `android/gradle.properties` |
