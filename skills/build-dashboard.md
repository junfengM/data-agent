---
name: Build Dashboard
description: Build source-backed analytical dashboards for monitoring performance and exploring drivers.
trigger: dashboard|scorecard|monitor|看板|仪表盘|监控
---

# Dashboard Building

构建可复用的分析看板，帮助团队监控指标、探索驱动因素并采取行动。好的看板是总结优先、图表驱动、可扫描的，围绕受众需要监控、理解或采取行动的内容组织。

## Mandatory Pre-Answer Gate

每次调用前必须执行：
1. 运行 `$user-context` 预检，加载项目上下文、语义层、source routing
2. 应用语义层：作为候选指标、表、连接、过滤器和注意事项的起始地图
3. 源发现与验证：跨可用源通道搜索，通过实时读取验证
4. 源访问护栏：如果必需源不可用，停止该路径；如果是可选补充，继续并标注缺口

## Workflow

### 1. 定义看板简报

了解谁将使用看板、他们需要测量或监控什么、哪些指标重要、以及什么约束可能改变构建。
明确主要受众、测量目标、指标范围、交付面、刷新期望、所需过滤器和共享需求。

当看板目的、指标定义或受众期望不够明确时，使用 `$gather-business-context`。

### 2. 选择交付面

- **默认**：在 Data Agent 内渲染 `visual_report` artifact（manifest.surface=dashboard）
- **HTML**：仅在需要便携静态看板时作为附件生成

### 3. 收集和验证数据

按此顺序做数据工作：
- **先找到源路径**：在渲染前确定核心看板指标的源路径
- **使用持久看板数据**：在接入看板前验证数据。保持最终提取紧凑且聚合
- **验证信任**：确认源、粒度、新鲜度和基本对账。当数据信任是重大风险时使用 `$analyze-data-quality`
- **确定时间和上下文锚点**：建立日期锚点、比较窗口、最新完整数据日期
- **停止如果源支持数据不可用**：不要从样本、临时表或部分阻塞的数据渲染看板

### 4. 定义指标模型

选择指标时考虑这些指标族：
- **覆盖面**：谁在使用、合格人口、渗透率、激活率、采用率
- **量级**：事件数、使用量、交易数、会话数、吞吐量、频率
- **价值**：收入、成本、利润、节省、转化、留存价值、生产力
- **质量**：成功、失败、可靠性、延迟、满意度、正确性、安全性
- **深度**：重复使用、强度、功能组合、工作流完成度、成熟度
- **组合**：细分、客户类型、地域、渠道、产品/版本、计划、队列
- **变动**：趋势、增长、季节性、前后对比、基准、目标、预测
- **风险和约束**：数据覆盖、源新鲜度、已知盲点、容量

将选定的族映射到看板角色：默认视图的英雄指标、变动和分解的诊断指标、解释的护栏指标、查找的详细指标。

当选定的基线指标族不够时调用 `$design-kpis`。

### 5. 设计看板布局

从总结到细节排列看板：从关键状态或主要 KPI 上下文开始，然后是随时间的变动，接着展示解释模式的分解，最后将详细表格放在较低位置。
保持看板可视化为主且中立：短标签、直接指标名、稀疏注释、主画布上最少的解释性文本。

### 6. 选择正确的图表

使用 `$visualize-data` 处理图表选择、视觉编码和图表打磨。本技能定义每个图表需要传达什么；`$visualize-data` 处理详细的视觉设计。

### 7. 构建和验证

在选定面构建，使用其原生模式。提交前检查：
- 看板打开干净
- 过滤器工作
- 图表渲染
- 数字对账
- 访问权限处理清晰
- 性能可接受

### 8. 交付看板

包含看板路径、执行的验证、源或访问注意事项以及任何剩余的共享步骤。

## Dashboard Quality Bar

提交前确保看板作为测量面可用：
- 默认视图在观众交互前回答主要受众问题
- 过滤器少、有意义、跨面工作
- 卡片、图表和表格对账一致，除非差异被清楚标注
- 图表回答明确问题，指标兼容
- 表格支持图表总结后的查找、比较或操作跟进
- 指标集足够广泛：覆盖相关族
- KPI 卡片精确定义
- 源新鲜度、访问限制和注意事项在相关处可见
- 布局、标签和性能适合所选交付模式

## Cross-Skill Dependencies

- `$user-context`：强制预检，source routing
- `$gather-business-context`：看板目的或指标定义不明确时加载
- `$design-kpis`：需要更深指标框架时加载
- `$analyze-data-quality`：数据信任是重大风险时加载
- `$visualize-data`：图表选择、视觉编码和图表 QA
- `$chart-rules`：图表选择规则，自动加载

## Output Contract

- Dashboard artifact（visual_report，manifest.surface=dashboard）
- Bounded snapshot（datasets）
- Metric definitions（在 manifest.cards[] 和 manifest.sources[] 中）
- Filter definitions（在 manifest.filters[] 中）
- Source and caveat notes



## Available Tools

- `preflight.py`：项目预检信封
- `validation.py`：验证门——产物可渲染性、源安全
- `chart_contract.py`：图表类型验证和意图兼容性检查
- `execution.py`：本地 Python 代码执行
