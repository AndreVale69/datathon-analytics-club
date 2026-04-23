import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/listings": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/raw-data-images": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    manifest: true,
    emptyOutDir: true,
  },
});
