import type { CapacitorConfig } from "@capacitor/cli";

/**
 * AI-TRADER mobile shell.
 *
 * The UI is the same React bundle that runs inside Electron. It talks to a
 * Python core over HTTP; there is no core inside the APK. Point the app at:
 *   - your PC on the same Wi-Fi  -> http://192.168.x.x:8765
 *   - a private tunnel           -> https://aitrader.your-tailnet.ts.net
 *
 * Build the web bundle first:  cd ../app && npm run build:web
 */
const config: CapacitorConfig = {
  appId: "com.aitrader.app",
  appName: "AI-TRADER",
  webDir: "../app/dist",
  android: {
    backgroundColor: "#faf9f5",
    // The core speaks plain HTTP on the LAN (http://192.168.x.x:8765), while the
    // WebView runs on https://localhost. Without this, every API call is blocked
    // as mixed content and the mobile app shows "Core offline".
    allowMixedContent: true,
  },
  ios: {
    contentInset: "always",
    backgroundColor: "#faf9f5",
  },
  server: {
    androidScheme: "https",
    iosScheme: "capacitor",
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 900,
      launchAutoHide: true,
      backgroundColor: "#faf9f5",
      androidScaleType: "CENTER_CROP",
      showSpinner: false,
    },
    StatusBar: {
      style: "DEFAULT",
    },
    Keyboard: {
      resize: "native",
    },
  },
};

export default config;
