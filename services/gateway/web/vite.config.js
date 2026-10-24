import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // dev only: forward /api calls to the gateway running in your cluster
  server: { port: 5173, proxy: { "/api": { target: "http://gateway.localtest.me", changeOrigin: true } } },
});