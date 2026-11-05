import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /v1 and /health are proxied to a local API on port 8000 so the browser never
// makes cross-origin calls. In production, set VITE_API_BASE to the deployed API origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
