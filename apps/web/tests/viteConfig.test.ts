// @vitest-environment node

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { build, type RollupOutput } from "vite";

describe("vite chunk strategy", () => {
  it("uses relative asset paths for Electron file loading", () => {
    const configSource = readFileSync(resolve(__dirname, "../vite.config.ts"), "utf8");

    expect(configSource).toMatch(/base:\s*["']\.\/["']/);
  });

  it("does not emit chunks that directly import each other", async () => {
    const result = await build({
      configFile: resolve(__dirname, "../vite.config.ts"),
      build: { write: false },
      logLevel: "silent",
    }) as RollupOutput;
    const chunks = result.output.filter((item) => item.type === "chunk");
    const importsByFile = new Map(chunks.map((chunk) => [chunk.fileName, new Set(chunk.imports)]));

    for (const [fileName, imports] of importsByFile) {
      for (const importedFile of imports) {
        expect(
          importsByFile.get(importedFile)?.has(fileName),
          `${fileName} and ${importedFile} import each other`,
        ).toBe(false);
      }
    }
  }, 15_000);
});
