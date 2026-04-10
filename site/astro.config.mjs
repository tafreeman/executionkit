import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";
import expressiveCode from "astro-expressive-code";

export default defineConfig({
  site: "https://tafreeman.github.io",
  base: "/executionkit",
  integrations: [
    expressiveCode({
      themes: ["github-dark"],
      styleOverrides: {
        codeBackground: "#0d1117",
        borderColor: "#30363d",
      },
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
  },
});
