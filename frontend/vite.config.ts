import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { tanstackRouter } from "@tanstack/router-plugin/vite";

export default defineConfig({
  plugins: [tanstackRouter(), react()],
  server: {
    host: true,
    port: 3000,
    allowedHosts: true,
    proxy: {
      "/-": {
        target: process.env.VITE_PROXY_BACKEND_URL,
        changeOrigin: true,
        secure: false,
        xfwd: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
