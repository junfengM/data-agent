# Codex 数据分析插件分析报告

分析对象：`0.1.38-cf2b8b6c00d3`（桌面插件目录）

## 核心架构对比

### 技能系统

| 插件技能 | 我们项目 | 差距 |
|----------|----------|------|
| index（路由器） | ✅ skills/index.md | 已升级为完整路由合约 |
| product-business-analysis | ✅ product-analysis | 名称不同，功能类似 |
| metric-diagnostics | ✅ metric-diagnostics | 已有 |
| build-report | ✅ build-report | 已有 |
| build-dashboard | ✅ build-dashboard | 已有 |
| visualize-data | ✅ visualize-data | 已有 |
| kpi-reporting | ✅ kpi-reporting | 已有 |
| design-kpis | ❌ 缺失 | 需要添加 |
| market-sizing | ❌ 缺失 | 需要添加 |
| analyze-data-quality | ❌ 缺失 | 需要添加 |
| validate-data | ❌ 缺失 | 需要添加 |
| gather-business-context | ❌ 缺失 | 需要添加 |
| jupyter-notebooks | ❌ 缺失 | 需要添加 |
| user-context | ❌ 缺失 | 需要添加 |
| report-to-google-doc | ❌ 缺失 | 需要添加 |
| report-to-google-slides | ❌ 缺失 | 需要添加 |
| report-to-pdf | ❌ 缺失 | 需要添加 |

### 用户上下文系统

**插件实现**：
- `user-context` 技能管理：
  - 源路由偏好（"Prefer: Databricks", "Avoid: Snowflake"）
  - 语义层注册表
  - 引导逻辑和设置进度
  - 预检门控（每个技能必须先运行 preflight）

**我们项目现状**：
- 只有简单的项目上下文（ProjectContext）
- 没有源路由偏好管理
- 没有语义层注册表管理
- 没有引导流程

### 语义层系统

**插件实现**：
- 完整的语义层技能（设置、刷新、检查、修复）
- 语义层是"源支持的本地技能"
- 编码：规范指标、表、粒度、连接、过滤器、查询模式、警告、源优先级
- 与 user-context 集成

**我们项目现状**：
- 只有 `config/semantic-layer.yaml` schema 定义
- 没有语义层管理功能
- 没有与项目上下文集成

### 源发现与验证

**插件实现**：
- 使用语义层作为起点
- 跨源搜索（数据仓库、仪表板、文档、聊天、笔记本、代码仓库）
- 通过实时源读取验证
- 源访问护栏（必需源不可用时停止路径）

**我们项目现状**：
- 只有数据集画像
- 没有跨源搜索
- 没有实时验证
- 没有源访问护栏

### 报告交付模式

**插件实现**：
- MCP 应用报告（默认）
- HTML 报告（Seaborn PNG 图表）
- Google Docs 转换
- Google Slides 转换
- PDF 导出

**我们项目现状**：
- Markdown 报告
- HTML 报告
- 结构化报告（块模式）

### 验证系统

**插件实现**：
- `validate_artifact` → `render_artifact`
- 图表合约验证
- 源安全检查
- 敏感负载检查
- 完成门（报告必须选择 exactly one delivery mode）

**我们项目现状**：
- 基本验证门（6 个）
- 没有图表合约验证
- 没有源安全检查

## 已完成任务的优化评估

### 1. Agent Manifest (`config/agent-manifest.yaml`)

**当前实现**：
- 声明了 agent 能力、技能、工具、产物类型、执行模式、验证门

**优化建议**：
- 添加源路由偏好配置
- 添加语义层注册表配置
- 添加引导流程配置
- 添加报告交付模式配置（MCP 应用、HTML、PDF、Google Docs/Slides）

### 2. 路由合约 (`skills/index.md`)

**当前实现**：
- 响应模式选择
- 主技能路由规则
- 辅助技能加载规则
- 语义层应用
- 项目预检信封
- 验证门应用

**优化建议**：
- 添加预检门控（mandatory pre-answer gate）
- 添加源发现与验证流程
- 添加源访问护栏
- 添加引导流程路由
- 添加完成门（report must choose exactly one delivery mode）

### 3. 语义层 schema (`config/semantic-layer.yaml`)

**当前实现**：
- 定义了 metrics、dimensions、sources、filters、joins、caveats、patterns

**优化建议**：
- 添加源优先级配置
- 添加查询模式示例
- 添加验证规则
- 添加刷新策略

### 4. 项目预检信封 (`server/app/tools/preflight.py`)

**当前实现**：
- 构建预检信封（项目、上下文、语义层、数据集画像、上下文差距、验证义务）

**优化建议**：
- 添加源路由偏好
- 添加语义层注册表
- 添加引导进度
- 添加最终义务（final obligations）

### 5. 验证门 (`server/app/tools/validation.py`)

**当前实现**：
- 6 个验证门（证据覆盖、源元数据、Schema 合规、图表合约、上下文警告、可渲染性）

**优化建议**：
- 添加图表合约验证（颜色、系列、分组）
- 添加源安全检查（敏感信息、凭证）
- 添加敏感负载检查
- 添加完成门验证

## 下一步优化任务

### 优先级 1（核心架构）

1. **创建 user-context 技能**
   - 管理源路由偏好
   - 管理语义层注册表
   - 实现预检门控
   - 实现引导流程

2. **增强语义层实现**
   - 添加语义层设置、刷新、检查功能
   - 与项目上下文集成
   - 添加源优先级管理

3. **实现源访问护栏**
   - 必需源不可用时停止路径
   - 告知用户需要什么源

### 优先级 2（用户体验）

4. **添加引导流程**
   - 创建引导技能
   - 添加设置进度跟踪
   - 添加英雄提示序列

5. **扩展报告交付模式**
   - 添加 PDF 导出
   - 添加 Google Docs/Slides 集成

### 优先级 3（质量保障）

6. **增强验证系统**
   - 添加图表合约验证
   - 添加源安全检查
   - 添加敏感负载检查

## 附录：插件关键文件

- `skills/index/SKILL.md` - 路由器技能
- `skills/user-context/SKILL.md` - 用户上下文技能
- `src/DESIGN.md` - 设计合约
- `src/analytics-app-core.md` - 应用核心合约
- `AGENTS.md` - 代理指南
- `README.md` - 插件说明
