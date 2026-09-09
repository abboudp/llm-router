import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/v1": "http://localhost:8000" },
  },
  build: { outDir: "dist" },
  test: {
    exclude: ["node_modules/**", "dist/**", "e2e/**"],
  },
});
