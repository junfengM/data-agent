import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("CSS integrity", () => {
  it("keeps artifact layout CSS braces balanced", () => {
    const cssPath = resolve(__dirname, "../src/components/artifact-layout.css");
    const css = readFileSync(cssPath, "utf8");
    let balance = 0;

    for (const [lineIndex, line] of css.split("\n").entries()) {
      for (const character of line) {
        if (character === "{") balance += 1;
        if (character === "}") balance -= 1;
        expect(balance, `unexpected closing brace at line ${lineIndex + 1}`).toBeGreaterThanOrEqual(0);
      }
    }

    expect(balance).toBe(0);
  });
});
