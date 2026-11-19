/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "-apple-system", "sans-serif"],
        display: ["Georgia", "Iowan Old Style", "Times New Roman", "serif"],
        mono: ["JetBrains Mono", "Cascadia Code", "Consolas", "monospace"],
      },
      borderRadius: { xl2: "1.15rem" },
      keyframes: {
        "fade-up": { "0%": { opacity: "0", transform: "translateY(6px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        shimmer: { "0%": { opacity: "0.45" }, "50%": { opacity: "1" }, "100%": { opacity: "0.45" } },
      },
      animation: { "fade-up": "fade-up .22s ease-out both", shimmer: "shimmer 1.4s ease-in-out infinite" },
    },
  },
  plugins: [],
};
