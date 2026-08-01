import { describe, expect, test } from "bun:test";
import fs from "node:fs";
import path from "node:path";

const sourceDir = import.meta.dir;

describe("Electron preload configuration", () => {
  test("loads a CommonJS preload artifact", () => {
    const mainSource = fs.readFileSync(path.join(sourceDir, "main.ts"), "utf8");

    expect(mainSource).toContain('preload: path.join(__dirname, "preload.cjs")');
    expect(fs.existsSync(path.join(sourceDir, "preload.cts"))).toBe(true);
  });
});
