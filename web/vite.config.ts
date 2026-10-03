import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The web app reads brand.json and the demo fixtures straight from the Python
// package so there is one copy of each (ADR 0002, ADR 0003).
const core = fileURLToPath(new URL("../src/issueradar", import.meta.url));
const src = fileURLToPath(new URL("./src", import.meta.url));
const brand = JSON.parse(readFileSync(`${core}/brand.json`, "utf8")) as { name: string };

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: "brand-name",
      transformIndexHtml: (html) => html.replaceAll("%BRAND_NAME%", brand.name),
    },
  ],
  resolve: {
    alias: { "@core": core, "@": src },
  },
  server: {
    port: 5173,
    fs: { allow: [".", core] },
    // `firstpr serve` runs the API on 8765; the dev server forwards /api to it.
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    exclude: ["e2e/**", "node_modules/**"],
  },
});
