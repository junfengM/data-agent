import { describe, expect, it } from "vitest";
import {
  humanizeReportLabel,
  prepareReportBlocks,
  stripDuplicateReportTitle,
} from "../src/utils/reportLayout";
import { filterBlocksByMode } from "../src/components/ArtifactModule";

describe("prepareReportBlocks", () => {
  it("removes duplicate title but no longer skips visual blocks (legacy path)", () => {
    const blocks = prepareReportBlocks([
      { type: "leaderboard_pair", title: "贡献项排行" },
      { type: "insight_banner", text: "重复洞察" },
      { type: "risk_panel", items: [{ text: "重复风险" }] },
      { type: "page_summary", items: [{ text: "重复结论" }] },
      { type: "markdown", body: "# 销售报告" },
      { type: "markdown", body: "## 核心结论\n\n结论正文。" },
      { type: "markdown", body: "## 详细分析\n\n正文。" },
    ], "销售报告");

    // Legacy path no longer skips visual block types; they flow through.
    // leaderboard_pair is dropped by isUsefulStructuralVisual (no positive/negative items).
    // First markdown "# 销售报告" is title-stripped to empty → dropped.
    expect(blocks.map((block) => block.type)).toEqual([
      "insight_banner",
      "risk_panel",
      "page_summary",
      "markdown",
      "markdown",
    ]);
    expect(String(blocks[3].body)).toContain("核心结论");
  });

  it("preserves blocks as-is when renderer_target is present (layer-aware path)", () => {
    const blocks = prepareReportBlocks([
      { type: "insight_banner", text: "洞察", renderer_target: "md_visual", block_origin: "visual_deck" },
      { type: "markdown", body: "# 销售报告\n\n正文。", renderer_target: "narrative", block_origin: "artifact_manifest" },
      { type: "chart", chart_id: "ch1", renderer_target: "evidence_component", block_origin: "artifact_manifest" },
    ], "销售报告");

    // Layer-aware: only markdown sanitized, no reordering, no drops.
    expect(blocks.map((b) => b.type)).toEqual(["insight_banner", "markdown", "chart"]);
    // Title should be stripped from markdown.
    expect(String(blocks[1].body)).not.toContain("# 销售报告");
  });

  it("does not impose visual modules when the manifest has none", () => {
    const blocks = [{ type: "markdown", body: "## 方法\n\n技术说明。" }];
    expect(prepareReportBlocks(blocks, "技术报告")).toEqual(blocks);
  });

  it("preserves source-details display metadata for visualized markdown", () => {
    const blocks = prepareReportBlocks([
      { type: "markdown", body: "## 核心结论\n\n完整原文。", display_mode: "source_details" },
      { type: "executive_storyboard", source_section: "核心结论", items: [{ headline: "结论" }] },
    ], "销售报告");

    expect(blocks[0].display_mode).toBe("source_details");
    expect(blocks[1].type).toBe("executive_storyboard");
  });

  it("localizes common category labels without changing the underlying datasets", () => {
    const blocks = prepareReportBlocks([
      { type: "markdown", body: "## 品类\n\n| category |\n| --- |\n| Electronics |\n| Clothing |\n| Food |" },
    ], "销售报告");

    expect(blocks[0].body).toContain("| 电子 |");
    expect(blocks[0].body).toContain("| 服装 |");
    expect(blocks[0].body).toContain("| 食品 |");
  });
});

describe("report labels", () => {
  it("humanizes common technical chart and field labels", () => {
    expect(humanizeReportLabel("chart_monthly_revenue_trend")).toBe("月度营收表现");
    expect(humanizeReportLabel("revenue_growth_pct")).toBe("营收环比");
  });

  it("removes only an H1 matching the report title", () => {
    expect(stripDuplicateReportTitle("# 销售报告\n\n## 核心结论", "销售报告")).toBe("## 核心结论");
    expect(stripDuplicateReportTitle("# 另一份报告", "销售报告")).toBe("# 另一份报告");
  });
});

describe("filterBlocksByMode", () => {
  const blocks = [
    { type: "markdown", body: "## 摘要", renderer_target: "narrative" },
    { type: "chart", chart_id: "ch1", renderer_target: "evidence_component" },
    { type: "table", table_id: "t1", renderer_target: "appendix" },
    { type: "executive_storyboard", items: [], renderer_target: "md_visual" },
    { type: "metric-strip", card_ids: ["c1"], renderer_target: "evidence_component" },
  ];

  it("shows appendix blocks in evidence mode", () => {
    const result = filterBlocksByMode(blocks, "evidence");
    expect(result.map((b) => b.type)).toEqual(["chart", "table", "metric-strip"]);
  });

  it("shows only reading-relevant blocks in reading mode", () => {
    const result = filterBlocksByMode(blocks, "reading");
    expect(result.map((b) => b.type)).toEqual(["markdown", "chart", "executive_storyboard", "metric-strip"]);
  });

  it("returns all blocks in audit mode", () => {
    const result = filterBlocksByMode(blocks, "audit");
    expect(result).toHaveLength(5);
  });
});
