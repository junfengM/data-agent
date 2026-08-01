---
name: Visualize Data
description: Design, choose, and QA data visualizations. Use when analysis needs chart selection, visual encoding, or visual polish.
trigger: chart|visualization|plot|graph|visual|图表|可视化
---

# Data Visualization

选择分析上合理、立即可读、足以交付的定量可视化。把图表当作对结论的证据支撑。

## Mandatory Pre-Answer Gate

每次调用前必须执行：
1. 运行 `$user-context` 预检，加载项目上下文、语义层、source routing
2. 检查语义层中是否有已定义的指标和维度
3. 源发现与验证：确认数据可用
4. 源访问护栏：必要时中止或标注缺口

## Chart Selection

| 数据关系 | 最佳图表 | 使用要点 |
|---|---|---|
| 时间趋势 | `line` | 足够的数据点揭示形状；`area` 仅在填充量级有用时使用 |
| 类别比较 | `bar` | 语义无关时排序；长标签用水平条；避免冗余图例 |
| 排名 / Top-N | `leaderboard` | 紧凑、单指标；超过 8 行考虑分页表格 |
| 构成分解 | `stackedBar` | 分母明确；`pie` 仅用于少量切片的粗略读数 |
| 分布 | `histogram` | 数值分箱揭示形状；比较组别用 `boxPlot` |
| 双数值关系 | `scatter` | x 和 y 同为数值、同粒度、同分母；保留点标签和分组字段 |
| 密集二维模式 | `heatmap` | 矩阵或强度；点级变化用 `scatter` |
| 加性桥接 | `waterfall` | 仅当驱动因素清晰汇总到终点值时使用 |
| 有序阶段递进 | `funnel` | 仅用于有序单系列阶段 |

### 选择原则

- **从分析问题出发**，不要从喜欢的图表类型出发
- 图表用于展示形状和比较，表格用于精确查找
- 不要仅仅因为 prompt 中有"趋势"就选 `line`——先判断读者需要状态、变化、混合还是分布
- 避免气泡图，除非第三个变量实质上改变解读
- `pie`、`waterfall`、`funnel` 是变体，不是默认选项
- 趋势图的点太少（<8个时间点）时，先尝试更细粒度或更长周期
- 散点图的点太少（<8个）时，用表格或条形图代替
- 当条形图比较一个指标跨类别时，只用一个类别轴和一个数值轴。不要将 `color` 或分组编码设为相同的类别字段

## Workflow

### 1. 确定分析问题

定义分析问题和一句话结论，再选图表。与 `$build-dashboard` 或 `$build-report` 协调。

### 2. 写图表契约

在绘图前写出紧凑的图表契约：
- 分析问题和结论
- 标准图表族和具体变体
- 数据充分性：预期行数、时间点数、散点观察数、日期范围和粒度
- 颜色策略
- 输出格式和交付目标

### 3. 选择交付路径

- **默认**：在当前运行产物中渲染图表（使用 artifact chart block）
- **报告模式**：由 `$build-report` 处理图表集成
- **看板模式**：由 `$build-dashboard` 处理图表集成
- **Web Report / 报告模式默认**：使用 Plotly 生成 `.html` 交互图表，并在 `report_md` 中用精确 Markdown 链接引用。
- **禁止默认静态图表**：不要使用 matplotlib、seaborn、pandas.DataFrame.plot 或静态 PNG 作为报告主图。
- **静态图片例外**：只有用户明确要求静态图片，且项目重新启用静态图能力时，才允许使用图片图表。

### 4. 构建顺序

格式 → 结构 → 颜色 → QA
先选族和变体；再决定标签、注释、基准线和保留信息；最后选颜色。

### 5. 图表数据要求

生成图表的数据表必须比最小渲染需要更丰富：
- 保留上下文维度（如产品线、地区、客户类型）
- 保留分子/分母字段、日期字段、排名、基准值
- 不要仅包含 x、y 值的精简数据表

### 6. QA 检查

- 图表选择遵循 Chart Selection 规则
- 数据粒度、过滤器、日期范围、分母、单位与图表支持的声明匹配
- 任何交付的图表必须有可见的标题和字幕
- 标签、刻度、标题、图例不碰撞、不裁剪
- 多系列填充标记需要明显区分
- 颜色不依赖颜色本身（用线型、标签、排序等辅助区分）
- 提交前在实际交付容器中检查图表

## Quality Bar

- 图表形式必须匹配分析比较，尺度必须诚实且跨可比图表一致
- 数据粒度、过滤器、日期范围、分母和单位必须匹配图表支持的声明
- 每个交付的图表必须有适合其交付面的可见标题和必要单位的字幕
- 正负状态应使用色调、开放填充、零线上下文和有符号标签，而非默认红/绿语义
- 图表脚手架应保持安静：没有任意背景色、渐变、装饰性参考线
- 多图表报告中避免全部使用同一种图表族——做图表族审计
- 对于执行报告，超过 4 个全部使用 `line` 的图表视为违反多图表报告契约

## Cross-Skill Dependencies

- `$user-context`：强制预检
- `$chart-rules`：图表选择规则，自动加载
- `$build-report`：报告模式下的图表集成
- `$build-dashboard`：看板模式下的图表集成
- `$validate-data`：需要验证支持分析时加载

## Available Tools

- `chart_contract.py`：图表类型验证、意图兼容性检查、混合尺度/混合指标检测
- `validation.py`：产物验证门，检查图表编码和渲染能力
- `execution.py`：本地 Python 代码执行（plotly HTML 图表生成；matplotlib 当前禁用）

