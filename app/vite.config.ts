import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
  },
  // Tauri expects a fixed dist dir
  build: {
    outDir: "dist",
    target: "es2021",
  },
});
