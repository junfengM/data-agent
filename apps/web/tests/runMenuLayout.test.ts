import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const runModule = readFileSync(
  resolve(__dirname, "../src/components/RunModule.tsx"),
  "utf8",
);
const runStyles = readFileSync(
  resolve(__dirname, "../src/analysis-chat.css"),
  "utf8",
);

describe("analysis run menu layout", () => {
  it("keeps dark context rows readable inside the run popover", () => {
    expect(runStyles).toMatch(
      /\.run-menu-popover\s+\.dataset-row\.light\s*\{[^}]*background:[^;]*!important;[^}]*color:[^;]*!important;/s,
    );
  });

  it("prevents skill rows from shrinking into overlapping content", () => {
    expect(runStyles).toMatch(
      /\.skill-selector-list\s*\{[^}]*align-content:\s*start;[^}]*grid-auto-rows:\s*max-content;/s,
    );
    expect(runStyles).toMatch(
      /\.skill-selector-list\s+\.run-selector-option\s*\{[^}]*min-height:\s*max-content;/s,
    );
    expect(runStyles).toMatch(
      /\.skill-selector-list\s+\.skill-trigger\s*\{[^}]*-webkit-line-clamp:\s*2;/s,
    );
  });

  it("does not expose partial run modes in the run composer", () => {
    expect(runModule).not.toContain('label="模式"');
    expect(runModule).not.toContain('openSection === "mode"');
    expect(runModule).not.toContain("runModeOptions");
  });
});
