---
name: user-context
description: Data Agent 项目级预检系统。管理源路由偏好、语义层注册表、引导流程。所有其他 skill 的强制预检入口。
---

# User Context

这个 skill 是 Data Agent 的项目级预检、源路由、语义层注册表和引导层。它加载项目上下文、数据源偏好、语义层指针和引导进度，供分析工作流使用。它不作为全局记忆系统使用。

## Mandatory Pre-Answer Gate

每个 Data Agent skill 在回答、搜索数据源、获取证据、创建产物或起草输出之前，**必须**先通过本 skill 执行预检。

本 skill 自身的预检路径：

1. 加载 `server/app/tools/preflight.py` 构建的预检信封
2. 信封包含：项目上下文、语义层定义、数据集画像、源路由偏好、上下文缺口、验证义务
3. 预检信封通过 `build_preflight_envelope()` 生成，`preflight_to_markdown()` 渲染为可读格式
4. 如预检信封不可用，手动读取项目级配置文件

不要跳过预检，即使项目上下文看起来已可用。

## 目的

User Context 在项目级配置中持久化两类信息：

1. **源路由偏好**：用户明确选择的未来数据源偏好（Prefer/Avoid）
2. **语义层注册表**：产品区域对应的语义层 skill 指针

它**不**存储：
- 任意业务背景或"记住这个"内容
- 分析优先级、输出偏好
- 已批准的草稿、历史产物
- 全局记忆

## 预检协议

### 调用路径

其他 skill 调用 user-context 作为强制预检门时：

1. 加载本 skill (`skills/user-context.md`)
2. 通过 `server/app/tools/preflight.py` 的 `build_preflight_envelope()` 构建信封
3. 使用返回的以下字段作为分析上下文：
   - `project`：选定的项目及其上下文
   - `semantic_layer`：语义层定义（metrics, dimensions, sources, filters, joins, caveats, patterns）
   - `datasets`：数据集画像和 schema 摘要
   - `source_routing`：源路由偏好（Prefer/Avoid/Neutral）
   - `context_gaps`：缺失的定义或上下文缺口
   - `validation_obligations`：必须通过的验证门
4. 立即让调用 skill 继续——预检信封是权威的、可审计的预检上下文

### 预检失败回退

如果预检脚本不可用：
- 手动读取 `config/semantic-layer.yaml` 获取语义层定义
- 检查 `config/agent-manifest.yaml` 获取源路由配置
- 读取项目上下文文件（如果存在）
- 声明缺失的上下文，但不要让预检阻塞分析——用现有信息继续，标记缺口

如果语义层文件不存在或为空：
- 这是正常初始状态
- 在 `context_gaps` 中标记"无规范指标定义"
- 继续分析，但不要编造指标定义

## 状态文件

项目级配置（相对于项目根目录）：

| 文件 | 用途 |
|------|------|
| `config/semantic-layer.yaml` | 语义层定义（规范指标、维度、源表） |
| `config/agent-manifest.yaml` | Agent 能力声明（含源路由类别） |
| 项目上下文文件 | 由 preflight.py 加载的业务上下文 |

与插件不同，Data Agent **不使用** `$CODEX_HOME` 全局状态目录。所有配置是项目级的。

## 源路由偏好

管理用户明确选择的源偏好。每个源类别可以有：`Prefer`（优先使用）、`Avoid`（避免使用）、`Neutral`（无偏好）。

### 源类别

| 类别 ID | 名称 | 说明 |
|---------|------|------|
| `structured_data` | 结构化数据 | 数据仓库、SQL 数据库、CSV/Excel 文件 |
| `team_communication` | 团队沟通 | Slack、Teams、邮件 |
| `company_docs` | 公司文档 | Notion、Google Drive、SharePoint |
| `product_analytics` | 产品分析 | Amplitude、Mixpanel、Statsig |

### 偏好设置

用户可以通过对话设置偏好，例如：
- "优先使用 CSV 文件中的数据"
- "避免使用外部 API 源"

偏好应记录在项目上下文中，由 preflight.py 加载。

### 源访问护栏

在查询数据源之前：
- 如果所需源不可用，**停止该路径**
- 告知用户缺少什么源，请他们提供或确认替代方案
- 不要将弱替代品视为等价
- 如果缺失的源仅是可选补充，用最强可用证据继续，标记缺口

## 语义层注册表

语义层是源支持的本地 skill，编码产品区域的规范指标、表、粒度、连接、过滤器和已知问题。

### 注册表格式

语义层指针应记录为：

```yaml
# 在 semantic-layer.yaml 中
areas:
  - name: customer_onboarding
    description: 客户引导流程分析
    metrics:
      - name: activation_rate
        formula: activated_users / total_signups
        grain: daily
        dimensions: [channel, plan]
    sources:
      - table: onboarding_events
        path: data/onboarding.csv
    caveats:
      - "2025-12 之前数据使用旧版事件定义"
```

### 使用语义层

当请求命名或暗示某个产品区域、指标、表或业务问题时：
1. 检查语义层注册表是否有匹配的区域
2. 如果有匹配的语义层，加载其定义
3. 在语义层作为起点映射候选指标、表、连接、过滤器、已知问题
4. 但**不要仅停在语义层**——用实际数据查询验证

### 语义层缺失时的行为

如果没有匹配的语义层：
- 在分析计划中标注"无规范定义"
- 从可用数据中推导指标，但明确说明推导逻辑
- 不要编造指标名称或定义

## 引导流程

Data Agent 提供 4 步引导流程：

| 步骤 | ID | 说明 |
|------|-----|------|
| 1 | `welcome` | 介绍 Data Agent 能力，确认使用场景 |
| 2 | `source_setup` | 确认数据源和连接方式 |
| 3 | `semantic_layer_setup` | 创建或导入语义层 |
| 4 | `hero_prompt` | 运行第一个分析工作流 |

### 首次运行

当没有项目上下文时：
- 不要假设用户的业务背景
- 询问必要的最少信息：数据在哪里？要分析什么？
- 引导完成后，记录偏好供后续使用

### Hero Prompts

引导完成后的建议首问：

- "分析用户激活流程，推荐团队关注方向" → `product-analysis`
- "诊断上周周活用户为什么下降" → `metric-diagnostics`
- "把本月指标做成领导层可读的运营更新" → `kpi-reporting`

## 读写规则

### 读

每次调用本 skill 时：
- 必须实际加载预检信封，不能仅检查文件是否存在
- 源路由偏好和语义层指针必须被加载和应用
- 不要将"列出文件"或"检查文件存在"视为充分读取

### 写

本 skill 管理的项目级配置中只持久化两类信息：

1. **源路由偏好**：`config/agent-manifest.yaml` 中的 `source_routing.categories`，每个类别可选 Prefer/Avoid/Neutral
2. **语义层注册表**：`config/semantic-layer.yaml` 中的结构化指标、维度、源表定义

业务含义（指标定义、数据源表、已知问题、报表偏好）必须通过语义层结构化定义，不要作为自由文本存入项目上下文。`project_contexts` 表仅用于存储路由指针（source_routing + semantic_layer），不存储业务内容 body。

## 与其他 Skill 的关系

- 本 skill 是**所有其他 Data Agent skill 的强制预检入口**
- 每个 skill 在其工作流开头必须包含强制预检门
- 预检完成后，控制权立即返回调用 skill
- 本 skill 不执行具体分析——它是上下文提供层

## 行为原则

- 不要用实现术语（预检、状态文件、schema、API 等）向用户解释——翻译成实际影响
- 每次输出应包含一个可操作的下一步，不要以死胡同结束
- 只在高度不确定、高影响的问题上追问用户——不要为了填充上下文而问问题
- 缺失上下文不是阻塞理由——用现有信息提供最佳答案，标记缺口
