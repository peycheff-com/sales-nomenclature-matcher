import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    chunkSizeWarningLimit: 1000,
    rolldownOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/")) {
            return "react-vendor";
          }
          if (
            id.includes("node_modules/@tanstack/react-query") ||
            id.includes("node_modules/@tanstack/react-router") ||
            id.includes("node_modules/@tanstack/react-table")
          ) {
            return "tanstack";
          }
          if (
            id.includes("node_modules/@base-ui/react") ||
            id.includes("node_modules/@radix-ui/react-switch") ||
            id.includes("node_modules/cmdk") ||
            id.includes("node_modules/framer-motion") ||
            id.includes("node_modules/lucide-react")
          ) {
            return "ui-vendor";
          }
          if (
            id.includes("node_modules/ky") ||
            id.includes("node_modules/papaparse") ||
            id.includes("node_modules/sonner") ||
            id.includes("node_modules/clsx") ||
            id.includes("node_modules/tailwind-merge")
          ) {
            return "utils";
          }
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
