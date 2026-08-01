# Visual Report Blocks

This document defines the first reusable block schema for management-ready `visual_report` artifacts. The goal is to make final reports render as rich, screenshot-friendly business pages instead of table-heavy Markdown.

## Block Types

### `kpi_grid`

Use for headline metrics.

```json
{
  "type": "kpi_grid",
  "title": "总体经营概览",
  "subtitle": "核心指标同比表现",
  "items": [
    {"label": "销售额", "value": "952.4 万", "previous": "895.0 万", "delta": "+6.4%", "direction": "up"}
  ],
  "evidence_ids": ["metric_sales"]
}
```

### `delta_bridge`

Use for change decomposition.

```json
{
  "type": "delta_bridge",
  "title": "销售变化拆解",
  "subtitle": "销售额增长由客单价与老客贡献驱动",
  "items": [
    {"label": "成交会员数减少", "value": "-12.7 万", "direction": "down"},
    {"label": "购买频次提升", "value": "+10.8 万", "direction": "up"},
    {"label": "客单价提升", "value": "+59.2 万", "direction": "up"}
  ],
  "evidence_ids": ["driver_sales"]
}
```

### `leaderboard_pair`

Use for Top growth versus Top drag contributors.

```json
{
  "type": "leaderboard_pair",
  "title": "品类贡献排行",
  "left_title": "增长贡献 Top",
  "right_title": "拖累贡献 Top",
  "positive": [{"label": "毛绒玩具", "value": "+112.4 万", "direction": "up"}],
  "negative": [{"label": "保温杯壶", "value": "-52.5 万", "direction": "down"}],
  "evidence_ids": ["category_rank"]
}
```

### `composition_panel`

Use for channel mix, customer mix, product-age structure, or category structure.

```json
{
  "type": "composition_panel",
  "title": "渠道结构",
  "items": [
    {"label": "店内", "value": "650.1 万", "share": "68.3%"},
    {"label": "线上", "value": "302.3 万", "share": "31.7%"}
  ],
  "evidence_ids": ["channel_mix"]
}
```

### `insight_banner`

Use for short business interpretation.

```json
{
  "type": "insight_banner",
  "title": "关键洞察",
  "text": "今年不是人更多了，而是买的人略少、但买得更贵。",
  "evidence_ids": ["kpi_grid", "driver_sales"]
}
```

### `risk_panel`

Use for caveats, risks, and data-quality warnings.

```json
{
  "type": "risk_panel",
  "title": "风险信号",
  "items": [
    {"text": "新客数同比下降，需要排查获客渠道与新品拉新效率。"},
    {"text": "增长集中在少数 IP / 爆款，结构均衡性不足。"}
  ],
  "evidence_ids": ["customer_mix", "brand_rank"]
}
```

### `next_action_list`

Use for concrete follow-up actions.

```json
{
  "type": "next_action_list",
  "title": "下一步重点",
  "items": [
    {"text": "复刻毛绒/IP/礼赠主题的成功方法。"},
    {"text": "下钻 stanley、Tagi、NICI 等拖累品牌及核心 SKU 的下滑原因。"}
  ],
  "evidence_ids": ["brand_rank", "sku_rank"]
}
```

### `page_summary`

Use at the end of a report page or major section.

```json
{
  "type": "page_summary",
  "title": "本页结论",
  "items": [
    {"text": "总销售额同比增长，但增长并非来自客数增加。"},
    {"text": "客单价提升是最核心增长驱动。"},
    {"text": "新客减少需要重点警惕。"}
  ],
  "evidence_ids": ["kpi_grid"]
}
```

## Rendering Rules

1. `visual_report` should prefer these visual blocks before table blocks.
2. Tables should be treated as drill-down evidence and should not dominate the main reading surface.
3. Every block must preserve `evidence_ids` when the claim is quantitative.
4. Every evidence-backed block should retain source metadata through the manifest and snapshot.
5. The first production renderer can map unsupported visual blocks to existing cards, charts, callouts, and compact tables, but the block type should remain explicit in the manifest.

## Minimum Visual Report Mix

For a business recap / management report, a valid first version should include at least:

- one `kpi_grid`
- one `delta_bridge` or `leaderboard_pair`
- one `composition_panel` or chart block
- one `insight_banner`
- one `risk_panel` or `next_action_list`

If the dataset cannot support one of these, the report should state the data gap rather than silently falling back to tables.
