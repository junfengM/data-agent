# Codex Data Analytics 可视化思路借鉴与推进方案

Last updated: 2026-06-10

## 背景

用户反馈当前 Data Agent 的最终报告过于表格化。目标不是复刻 Codex / ChatGPT 的视觉效果，而是让最终报告最少具备管理层可读、可截图、可分享的丰富展示方式。

本文件记录从 Codex Data Analytics 插件中值得借鉴的可视化架构，并拆解成可逐项推进的工程任务。

## 核心结论

Codex Data Analytics 的关键不是“让模型直接生成漂亮页面”，而是把分析结果做成一个受控 artifact app：

```text
analysis result
  -> manifest
  -> bounded snapshot
  -> validation
  -> renderer / artifact app
  -> export / share / inspect
```

因此我们也应该避免只靠 prompt 或 CSS 美化来解决表格化问题。长期方案应是：

1. 后端产出标准 visual manifest。
2. 前端按 block schema 渲染视觉报告。
3. 验证层保证 chart、table、card、source、snapshot 可用。
4. 表格作为证据层，不作为默认主阅读面。

## 值得借鉴的点

### 1. Manifest + Snapshot 分离

Codex 插件把报告结构和数据分离：

- `manifest`：描述报告标题、blocks、cards、charts、tables、sources、filters、布局和字段编码。
- `snapshot`：保存经过审阅和裁剪的渲染数据，通常是 `datasets` 映射。

借鉴方式：

- 保持我们现有 `visual_report.data.manifest + visual_report.data.snapshot` 结构。
- 后端不要只输出 Markdown；必须生成可渲染 block 流。
- snapshot 数据要 bounded，避免把完整明细表塞到主报告。
- chart/table/card 只引用 dataset id，不直接内嵌大数据。

推进任务：

- [x] 已有 manifest/snapshot 基础结构。
- [ ] 扩展后端 block schema，支持经营报告需要的视觉 block。
- [ ] 给 snapshot 增加大小/行数限制和状态标记：`ready`、`partial`、`blocked`。

### 2. Surface 分流，而不是所有结果都做成表格报告

Codex 插件区分 inline widget、report artifact、dashboard artifact。不同任务应进入不同展示面。

借鉴方式：

```text
临时图表 / 单图分析       -> inline chart/table
经营复盘 / 月报 / 管理层报告 -> visual_report
持续监控 / 可筛选看板       -> dashboard
审计 / 明细核查            -> table / evidence detail
```

推进任务：

- [x] `visual_report` 已经在前端优先展示。
- [ ] 在后端 delivery mode 中默认识别“经营概览、月报、复盘、管理层报告、可分享报告”为 `visual_report`。
- [ ] 后续新增 `dashboard` surface，不和 report 混用。

### 3. 少量强语义 block + 通用 chart/table/card renderer

Codex 插件的 report block 很克制，常用：

- `markdown`
- `metric-strip`
- `chart`
- `table`
- `html`

它的丰富度来自 runtime、layout、sources、edit controls，而不是无限堆 block 类型。

结合我们的经营分析场景，可以保留少量强语义视觉 block：

- `kpi_grid`
- `delta_bridge`
- `leaderboard_pair`
- `composition_panel`
- `insight_banner`
- `risk_panel`
- `next_action_list`
- `page_summary`

借鉴方式：

- 不继续无限增加 block 类型。
- 每个 block 都要回答明确业务问题。
- 能用 chart 表达的不要再定义新组件。
- 表格只做证据下钻。

推进任务：

- [x] 前端已新增这些视觉 block 的基础渲染器。
- [x] 前端已新增 `VisualAutoOverview` 作为兜底视觉层。
- [ ] 后端正式生成这些 visual blocks，而不是只靠前端兜底。

### 4. Chart Contract 要强于“画个图”

Codex 插件将 chart 看作一个严格 contract，而不是自由图像：

```text
chart intent
chart type
compatible types
encodings: x / y / color / size / label
source
format
axis title
value format
dataset id
```

借鉴方式：

| 分析意图 | 推荐图形 |
|---|---|
| trend | line / area / sparkline |
| comparison | bar / horizontalBar |
| ranking | leaderboard / horizontalBar |
| composition | stackedBar / stackedBar100 / pie |
| decomposition | waterfall / driver bridge |
| distribution | histogram / boxPlot |
| relationship | scatter / heatmap |
| funnel | funnel / stage bar |

推进任务：

- [ ] 在后端 chart spec 中加入 `intent`。
- [ ] 新增 chart intent -> chart type 的选择器。
- [ ] 校验 chart encodings 的字段是否存在于 snapshot dataset。
- [ ] 前端 renderer 根据 intent 提供更合理的默认图形。

### 5. Validation 先于 Rendering

Codex 插件强调 artifact validation：

```text
validate_artifact
  -> fix manifest / snapshot
  -> render_artifact
```

借鉴方式：

增加专门的 visual artifact validation：

- visual_report 是否至少包含 3 个非表格组件。
- 是否连续出现大表格。
- chart 是否有 dataset。
- chart encoding 字段是否存在。
- card metric 字段是否存在。
- table 是否被放在主报告第一屏。
- source/query metadata 是否可追溯。
- snapshot 是否过大。

推进任务：

- [ ] 扩展 `run_validation_gates`，增加 visual report gates。
- [ ] validation 结果直接显示在 visual report 顶部或底部。
- [ ] fail/warning 不能被隐藏在 debug log 里。

### 6. Source / Data / Query 可检查

Codex 插件不是只展示图，而是让每个图表、表格、指标都能追溯到 source、query、filters、metric definitions。

借鉴方式：

- 每个 chart/table/card 都要保留 `source_id` 或 `evidence_ids`。
- 来源信息不能只有“本次运行”；要包含 dataset、date window、filters、query/code path。
- 前端每个证据块支持“查看数据 / 查看来源 / 查看计算逻辑”。

推进任务：

- [ ] 标准化 manifest source 结构。
- [ ] 前端给 chart/table/card 增加 source drawer。
- [ ] 导出图片时隐藏复杂 source 细节，但 HTML/export package 保留。

### 7. 表格是 Evidence Layer，不是主阅读面

Codex 的表格更像 review 和 audit 工具，而不是主报告主体。

借鉴方式：

- visual_report 第一屏不放大表。
- 明细表进入“证据明细 / 附录 / 查看数据”。
- ranking 不用 full table，优先用 compact leaderboard。
- 管理层报告中表格占比应低于 30%。

推进任务：

- [x] skill 中已加入反表格堆砌规则。
- [ ] 后端 manifest builder 把未匹配表格默认放入 appendix。
- [ ] 前端对 appendix/evidence table 默认折叠或弱化视觉权重。

## 实施路线

### Phase 1：Schema 对齐

目标：后端可以合法产出前端已支持的 visual block。

要做：

1. 扩展 `ArtifactBlockType`。
2. 扩展 `ArtifactBlock` 字段：`title`、`subtitle`、`items`、`positive`、`negative`、`left_title`、`right_title`、`text`、`summary`、`note`、`dataset`。
3. 保持向后兼容：已有 `markdown`、`metric-strip`、`chart`、`table` 不变。

完成标准：

- Pydantic 不会拒绝 `kpi_grid` 等 block type。
- `manifest.model_dump()` 能保留视觉 block 数据。

### Phase 2：Visual Report Planner

目标：即使 LLM 输出普通 markdown + tables，也能自动生成视觉报告骨架。

要做：

1. 新增 `visual_report_planner.py`。
2. 从 cards/tables/charts/report text 推导：
   - `kpi_grid`
   - `leaderboard_pair`
   - `composition_panel`
   - `insight_banner`
   - `risk_panel`
   - `page_summary`
3. 在 `build_artifact_manifest` 中先插入视觉 blocks，再插入正文 evidence blocks。

完成标准：

- 经营类报告默认第一屏出现 KPI / 排行 / 洞察，而不是表格。
- 原表格仍保留在 evidence/appendix。

### Phase 3：Chart Intent Contract

目标：图表生成从“有图就行”升级到“意图驱动”。

要做：

1. chart spec 增加 `intent` 字段。
2. 增加 intent compatibility 校验。
3. 前端 chart renderer 按 intent 选择默认布局。
4. 支持至少：trend、ranking、composition、decomposition、distribution、relationship、funnel。

完成标准：

- 同一份数据不会总被渲染成普通 bar/table。
- 排行默认横向榜单，趋势默认 line，结构默认 composition。

### Phase 4：Visual Validation Gates

目标：防止视觉报告退化。

要做：

1. 增加 visual block count gate。
2. 增加 table dominance gate。
3. 增加 chart encoding field gate。
4. 增加 source/evidence link gate。

完成标准：

- 如果 visual_report 几乎全是表格，validation 给 warning。
- 如果 chart/table/card 引用不存在字段，validation 给 fail。

### Phase 5：Source Drawer 与 Evidence UX

目标：报告既丰富，也可信。

要做：

1. chart/table/card 支持查看 source。
2. table 支持“查看数据”而非默认铺满主阅读面。
3. report export 时保留 HTML source；图片导出只展示主报告。

完成标准：

- 业务方看图能读结论。
- 分析师能追溯数据和计算。

## 当前状态

已经完成：

- `visual_report` 优先展示。
- 前端视觉报告画布和导出图片能力。
- 前端基础视觉 blocks。
- 前端自动视觉摘要兜底。
- skill 约束：管理层报告不要表格堆叠。

下一步按顺序推进：

1. Phase 1：Schema 对齐。
2. Phase 2：Visual Report Planner。
3. Phase 3：Chart Intent Contract。
4. Phase 4：Visual Validation Gates。
5. Phase 5：Source Drawer / Evidence UX。
