/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Teenage-Engineering-inspired instrument palette
        base: "#09090a",
        surface: "#0c0c0e",
        panel: "#101012",
        raised: "#151517",
        txt: "#d8d9db",
        sub: "#83868c",
        dim: "#565a60",
        faint: "#2c2e32",
        accent: "#ff5c26",
        "accent-dim": "#b84a22",
        signal: "#ff453a",
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SF Mono",
          "JetBrains Mono",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      letterSpacing: {
        wider2: "0.14em",
        widest2: "0.2em",
      },
      borderRadius: {
        te: "3px",
      },
    },
  },
  plugins: [],
};
