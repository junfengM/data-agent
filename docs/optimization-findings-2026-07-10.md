# Data Agent 优化排查记录 — 2026-07-10

状态：**Open**  
范围：本仓库（Data Agent）的本地优化评估。
审查基线：`main`，审查时仓库头提交 `cc64dfc8b318b458c5e5a8e6c5a9a62cc160a3c1`。  
审查方式：GitHub 静态代码检查；本次未在本地启动应用，也未重新执行测试套件。

本文用于记录当前排查出的正确性、安全性、运行稳定性和工程维护问题，便于后续在本地逐项修复。修复时建议每项单独提交，并补充回归测试。

---

## 优先级概览

| ID | 优先级 | 问题 | 主要影响 | 状态 |
|---|---|---|---|---|
| DA-OPT-001 | P0 | 同步子进程阻塞异步服务，缺少可靠取消 | 运行卡死、SSE 心跳中断、无法停止任务 | Open |
| DA-OPT-002 | P0 | Run 缺少顶层异常收尾 | 失败任务可能永久显示 `running` | Open |
| DA-OPT-003 | P0 | Excel 上传未验证真实文件结构 | 无效文件进入运行阶段并触发异常 | Open |
| DA-OPT-004 | P0 | Skill / Template 路径缺少边界校验 | 目录穿越、读取目录外 Markdown | Open |
| DA-OPT-005 | P0/P1 | `local-dev` 执行资源与隔离控制不足 | 宿主文件访问、磁盘/CPU/内存失控 | Open |
| DA-OPT-006 | P1 | Planner 调用、执行和上下文预算过宽 | Token、费用、时间不可控 | Open |
| DA-OPT-007 | P1 | `temperature=0` 被错误替换为 `0.2` | 模型配置不生效 | Open |
| DA-OPT-008 | P1 | Planner 异常被普通 fallback 报告掩盖 | 用户误判运行成功 | Open |
| DA-OPT-009 | P1 | Web Report iframe sandbox 组合过宽 | 生成 HTML 的浏览器隔离减弱 | Open |
| DA-OPT-010 | P2 | SQLite、运行历史和文件缺少生命周期管理 | 数据库/工作区持续膨胀 | Open |
| DA-OPT-011 | P2 | Trace 默认持久化较多 Prompt 内容 | 本地敏感上下文长期留存 | Open |
| DA-OPT-012 | P2 | 数据画像重复全表扫描 | 大文件、宽表性能差 | Open |
| DA-OPT-013 | P2 | CI 不完整且部分环境未固定 | 构建不可复现、Desktop 缺少持续验证 | Open |
| DA-OPT-014 | P2 | 前端报告模块体积和职责过重 | 维护、测试和按需加载困难 | Open |

---

## 修复状态（2026-08-01 更新）

已完成并带回归测试的条目：

- **DA-OPT-002 — Fixed**：`AgentOrchestrator.run()` 对异常/取消持久化最终状态（`failed`/`cancelled`），并覆盖所有正常返回路径。
- **DA-OPT-003 — Fixed**：`.xlsx` 校验 ZIP 签名、必需条目、条目数与解压总大小；`.xls` 校验 OLE2 签名。
- **DA-OPT-004 — Fixed**：Skill/Template 名称仅允许 `[a-z0-9_-]+`，`resolve()` 后必须在基准目录内，拒绝符号链接逃逸。
- **DA-OPT-007 — Fixed**：`resolve_temperature()` 保留显式 `0.0`，planner 与 LLM client 统一使用。
- **DA-OPT-008 — Fixed**：模型/认证类失败且无分析证据时，Run 直接标记 `failed` 并停止产物生成；已有证据时仍走自动恢复报告。
- **DA-OPT-011 — Fixed（默认安全）**：Prompt 快照默认不再持久化，需显式设置 `DATA_AGENT_TRACE_PERSIST_PROMPT_SNAPSHOTS=true`。
- **DA-OPT-006 — Partial**：新增 `planner_max_code_executions` 执行预算，达到上限后移除 `execute_code`/`save_semantic_finding`；Token/费用/时间总预算仍待实现。
- **DA-OPT-013 — Partial**：Web CI 固定 Bun 版本，新增 Desktop CI（构建、测试、`npm audit`）；Ruff/mypy 门禁与工具链固定仍待实现。
- **DA-OPT-001 — Partial**：分析代码执行改为异步子进程（`run_analysis_code_async`），子进程独立进程组，超时/取消会终止整个进程组；新增 `POST /api/runs/{run_id}/cancel` 与前端“取消”按钮；SSE 断开取消会同步终止分析子进程。Quarto 渲染已改为 `asyncio.to_thread` 避免阻塞事件循环，但 Quarto 子进程级取消尚未覆盖。
- **DA-OPT-005 — Partial**：新增 `analysis_max_total_output_bytes` 总输出发现上限；子进程应用 POSIX rlimit（CPU、文件大小、FD 数、地址空间、进程数）；运行后文件清理与真正沙箱后端仍未实现。
- **DA-OPT-009 — Fixed**：Web Report iframe 移除 `allow-same-origin`（`sandbox="allow-scripts"`），同源 DOM/存储不再可被生成 HTML 访问；“导出为图片”改为“下载 HTML”；文件图表 iframe 保持 `allow-scripts`；资产端点 CSP 维持 `connect-src 'none'`。
- **DA-OPT-010 — Partial**：`GET /api/runs` 支持 `limit`/`offset` 分页；新增 `DELETE /api/runs/{run_id}`（运行中任务返回 409，删除数据库行、事件与 artifacts 目录）；SQLite 启用 WAL 与 busy_timeout。正式 migration 机制、运行摘要列、UI 删除入口、FK 强制（需级联设计）仍待实现。
- **DA-OPT-012 — Partial**：CSV 超过 `profile_sampling_threshold_rows`（默认 20 万行）时改用采样画像（前 `profile_sampling_max_rows` 行），行数用 DuckDB 流式统计；按文件指纹（路径+大小+mtime+版本）缓存画像，重复运行不再重扫。Excel 工作表选择、DuckDB 全链路分块、近似 distinct、性能基准仍待实现。
- **DA-OPT-014 — Partial**：从 `ArtifactModule.tsx` 拆分出 `WebReportPreview.tsx`、`FileChartPreview.tsx`、`utils/download.ts`，保留兼容再导出；ArtifactModule 主体拆分、重型渲染器动态导入与按需加载仍待实现。

优化条目已全部处理（部分完成项见上）。

## DA-OPT-001 — 同步子进程阻塞异步服务，缺少可靠取消

### 现状

- `server/app/agent/execution_service.py` 中的异步 `execute_step()` 直接调用同步 `run_analysis_code()`。
- `server/app/tools/execution.py` 使用 `subprocess.run()` 执行生成代码，默认超时可达 600 秒。
- `server/app/agent/quarto_renderer.py` 同样使用同步 `subprocess.run()`。
- `server/app/api/stream_routes.py` 在连接结束时仅取消异步 Task；若 Task 正阻塞于同步子进程，取消不能立即终止底层进程。
- `apps/web/src/api/runs.ts` 的流式请求没有暴露 `AbortSignal`，目前缺少真正的“停止运行”闭环。

### 风险

- 一个长分析步骤可能阻塞 FastAPI 事件循环。
- SSE 心跳和其他 API 请求可能延迟或停顿。
- 用户关闭页面或取消请求后，Python/Quarto 子进程仍可能继续运行。
- 应用退出时可能留下未清理进程或不完整产物。

### 建议修复

1. 使用 `asyncio.create_subprocess_exec()` 管理 Python 和 Quarto 子进程；最低限度也应先通过 `asyncio.to_thread()` 避免阻塞事件循环。
2. 每个 Run 保存当前子进程或进程组句柄。
3. 增加取消 API，例如 `POST /api/runs/{run_id}/cancel`。
4. 前端使用 `AbortController`，并显示明确的“正在取消 / 已取消”状态。
5. Unix/macOS 下启动独立进程组，取消时终止整个进程组，而不是只杀父进程。
6. 增加取消、超时、客户端断开、应用退出的回归测试。

### 验收标准

- 一个 Run 执行 `sleep` 时，其他健康检查和列表接口仍可正常响应。
- 用户点击取消后，子进程在短时间内退出，Run 最终状态为 `cancelled`。
- SSE 断开不会留下后台分析进程。

---

## DA-OPT-002 — Run 缺少顶层异常收尾

### 现状

- Orchestrator 在运行开始时创建并持久化 `running` 状态。
- 数据画像发生在 Planner 局部 `try/except` 之前。
- Planner 之后的 Markdown、HTML、Notebook、Manifest 和验证环节没有统一的顶层异常收尾。
- `stream_routes.py` 捕获异常后只向客户端发送错误消息，未统一把 Run 更新为失败。

主要文件：

- `server/app/agent/orchestrator.py`
- `server/app/api/stream_routes.py`
- `server/app/memory/store.py`

### 风险

- 数据解析、产物写入或验证抛异常后，数据库记录可能永久停留在 `running`。
- 用户无法区分“仍在运行”“异常退出”“应用被关闭”。
- 已生成的部分证据和失败阶段无法可靠保留。

### 建议修复

在 `AgentOrchestrator.run()` 最外层建立统一状态收尾：

```text
try:
  执行完整流程
except asyncio.CancelledError:
  status = cancelled
  保存取消阶段和已有产物
  raise
except Exception:
  status = failed
  保存 failure_stage / error_type / error_id
finally:
  持久化最终状态、更新时间和已有产物
```

同时建议：

- Run 增加 `updated_at`、`failure_stage`、`error_code`、`cancel_requested_at`。
- 应用启动时，将超过阈值且无活动进程的 `running` Run 标记为 `interrupted`。
- 对画像失败、报告写入失败、验证异常分别增加测试。

### 验收标准

- 任意阶段抛异常后，Run 不会继续显示 `running`。
- 历史页面可看到明确的失败阶段和安全错误摘要。
- 应用异常退出后，下次启动能识别并修正孤儿 Run 状态。

---

## DA-OPT-003 — Excel 上传未验证真实文件结构

### 现状

`server/app/tools/files.py` 当前主要验证：

- 文件后缀；
- Content-Type；
- 上传大小；
- CSV 前 4096 字节是否含 NUL。

对 `.xlsx` 和 `.xls` 没有真实格式验证。`server/tests/test_uploads.py` 当前测试允许任意字节以 Excel 后缀保存。

之后 `server/app/tools/dataframes.py` 会直接调用 `pandas.read_excel()`，无效文件将在运行画像阶段失败。

### 风险

- 后缀伪装文件被当作合法数据集记录。
- 损坏 Excel 在 Run 开始后才失败，并可能触发 DA-OPT-002。
- XLSX 属于 ZIP 容器，缺少解压大小控制时存在 ZIP bomb 风险。

### 建议修复

- XLSX：检查 ZIP 签名、必要目录/文件，并限制压缩包解压后的总大小和文件数。
- XLS：检查 OLE Compound File 签名。
- 上传完成后进行轻量解析预检，至少能读取 workbook 元信息和首张工作表。
- 预检失败时删除上传文件，不创建 DatasetRecord。
- 增加损坏 XLSX、伪造 XLS、ZIP bomb、加密 workbook 的测试。

### 验收标准

- 任意字节伪装的 `.xlsx/.xls` 在上传阶段被拒绝。
- 合法 Excel 仍可上传。
- 超大解压比或异常 ZIP 不会造成内存/磁盘失控。

---

## DA-OPT-004 — Skill / Template 路径缺少边界校验

### 现状

`server/app/agent/skills.py` 中：

```python
path = self.skills_dir / f"{skill_id}.md"
```

没有限制 `skill_id` 字符，也没有检查 `resolve()` 后是否仍在 `skills_dir` 内。模型可以通过 `load_skill(skill_id)` 提供工具参数。

`server/app/agent/templates.py` 对模板名称采用相似的路径拼接方式。

### 风险

- `../docs/...` 一类 ID 可能读取 Skill 目录外的 Markdown。
- 被读取内容会进入模型上下文。
- 后续若扩展支持其他文件类型，风险会进一步扩大。

### 建议修复

1. Skill ID 和模板名称只允许 `[a-z0-9_-]+`。
2. 仅允许加载 Registry 已枚举出的 Skill ID。
3. 所有路径 `resolve()` 后必须满足 `is_relative_to(base_dir.resolve())`。
4. 拒绝符号链接和非普通文件。
5. 对 `../`、绝对路径、Unicode 分隔符、符号链接增加测试。

### 验收标准

- 目录穿越参数只返回安全错误，不读取文件。
- 正常 Skill 和模板加载不受影响。

---

## DA-OPT-005 — `local-dev` 执行资源与隔离控制不足

### 现状

项目已明确声明 `local-dev` 不是安全沙箱。但当前 AST 检查仅封锁部分模块和函数：

- 生成代码仍可通过 `open()`、`pathlib`、`shutil` 等读取宿主可访问文件。
- 包装代码主动注入 `os` 和 `sys`。
- 输出文件数量和单文件大小限制只影响“产物发现”，不会阻止文件实际创建。
- 当前默认上限为最多 500 个发现文件、单文件 200MB，缺少 Run 总量限制。
- 缺少 CPU、内存和进程数约束。

主要文件：

- `server/app/tools/execution.py`
- `server/app/core/settings.py`

### 风险

- 生成代码可读取宿主文件。
- 可写入大量不受产物收集规则覆盖的文件。
- 可造成磁盘、CPU 或内存耗尽。
- AST 黑名单可能给开发者造成“已经隔离”的错觉。

### 建议修复

短期：

- UI 和文档持续明确标注“可信本地执行，不是沙箱”。
- 增加 Run 总输出大小和目录总大小限制。
- 运行结束后扫描并清理超限、不支持或临时文件。
- 使用 OS resource limits 限制 CPU、地址空间、文件大小和子进程数。

中期：

- 落地真正的 SandboxRunner，优先考虑无网络、只读输入挂载、独立临时目录、资源配额的容器/轻量虚拟化方案。
- 对 Sandbox 能力进行独立功能检测，不可用时不得自动降级到 `local-dev`。

### 验收标准

- 超过总输出配额时任务被终止并标记为资源超限。
- 生成代码不能访问工作目录外的文件（Sandbox 模式）。
- 生产/共享场景无法误开启 `local-dev`。

---

## DA-OPT-006 — Planner 调用、执行和上下文预算过宽

### 现状

`server/app/core/settings.py` 默认：

- `planner_max_tool_iterations = 80`
- `planner_context_warn_chars = 300_000`
- `planner_context_hard_chars = None`
- 每步执行超时 600 秒

`server/app/agent/planner.py` 中即便超过配置的 hard threshold，也只是发送告警并继续执行。`_available_tools(execution_count)` 当前直接忽略执行次数。

另有状态不一致：

- `ENABLE_DETACHED_FINALIZER = False`
- 但长度截断路径仍可切换到 detached finalizer。

### 风险

- 单次分析模型调用、Token、费用和时间不可控。
- 多次工具失败可能持续重试。
- 上下文已经过大时仍继续堆积，最终报告输出空间不足。
- 配置和实际行为不一致，调优困难。

### 建议修复

为每个 Run 建立明确预算：

- 最大模型调用次数；
- 最大代码执行次数；
- 最大失败重试次数；
- 最大输入/输出 Token；
- 预估费用上限；
- 最终报告预留 Token；
- 总运行时间上限。

超过预算后的行为应是：

1. 停止调用新工具；
2. 压缩已有证据；
3. 进入 finalizer；
4. 无法完成时返回 `completed_degraded` 或明确失败。

同时统一 detached finalizer 开关和测试语义。

### 验收标准

- 任意 Run 的最大模型请求和执行次数可预测。
- 达到硬预算后不再继续调用工具。
- 运行日志能展示预算消耗和停止原因。

---

## DA-OPT-007 — `temperature=0` 被错误替换为 `0.2`

### 现状

以下代码使用真值判断：

```python
self.config.temperature or 0.2
```

因此显式配置 `0.0` 时，实际请求仍使用 `0.2`。

涉及：

- `server/app/agent/planner.py`
- `server/app/core/llm.py`

### 建议修复

```python
temperature = 0.2 if self.config.temperature is None else self.config.temperature
```

同时在 Pydantic Schema 中限制合理范围，并增加 `0.0` 回归测试。

### 验收标准

- 配置 `temperature: 0` 时，请求参数确实为 `0`。

---

## DA-OPT-008 — Planner 异常被普通 fallback 报告掩盖

### 现状

`server/app/agent/orchestrator.py` 对较广泛的 Planner 异常生成 fallback 报告，包括可能的：

- API Key / 认证问题；
- 模型服务不可用；
- Prompt 或响应格式故障；
- 代码内部异常。

Fallback 最终仍可能进入常规产物生成流程。

### 风险

- 用户看到一份报告后误以为完整模型分析成功。
- 模型故障和可接受的降级场景没有区分。
- 监控数据难以准确统计真正成功率。

### 建议修复

明确状态分类：

- `failed`：认证、模型调用或内部异常，没有足够可靠证据；
- `completed_degraded`：已有可靠数据画像/证据，但模型最终化失败；
- `completed_with_warnings`：分析完成但验证有警告；
- `completed`：正常闭环。

Fallback 报告必须带醒目的降级标记和失败原因类别，不能只作为普通 caveat。

### 验收标准

- 模型认证失败不会生成看似正常的完成报告。
- 历史列表能区分成功、警告、降级和失败。

---

## DA-OPT-009 — Web Report iframe sandbox 组合过宽

### 现状

普通文件图表 iframe 使用：

```text
sandbox="allow-scripts"
```

完整 Web Report 预览使用：

```text
sandbox="allow-scripts allow-same-origin"
```

主要文件：`apps/web/src/components/ArtifactModule.tsx`。

当前加入 `allow-same-origin` 的主要原因之一，是父页面需要访问 iframe DOM 以导出图片。

### 风险

对于包含生成内容的 HTML，`allow-scripts + allow-same-origin` 会明显削弱 sandbox 隔离。即使当前 CSP 较严格，也不应把浏览器隔离建立在生成 HTML 永远安全的假设上。

### 建议修复

- 移除 Web Report iframe 的 `allow-same-origin`。
- 图片/PDF 导出改为后端或独立受控渲染流程。
- 保持 `connect-src 'none'`，并审查生成报告中的外部资源。
- 增加恶意 HTML、外部请求、父页面访问的浏览器安全测试。

### 验收标准

- 生成报告脚本不能访问父页面或同源存储。
- 报告导出功能不依赖放宽 sandbox。

---

## DA-OPT-010 — SQLite、运行历史和文件缺少生命周期管理

### 现状

- `runs` 表把完整 `RunResponse` 作为 JSON Payload 存储。
- 历史列表会读取并反序列化完整 Payload 后再生成摘要。
- 没有明显的 Run、Dataset、Project 及产物级联删除闭环。
- 工作区产物、导出包和桌面后端日志没有自动保留策略。
- Schema 演进主要在 `_init()` 中手工 `ALTER TABLE`，部分异常被直接忽略。

主要文件：

- `server/app/memory/store.py`
- `server/app/api/trace_routes.py`
- `apps/desktop/src/backend.ts`

### 风险

- 数据库和工作区持续膨胀。
- 历史列表随 Run 数量增长而变慢。
- 手工迁移难以回滚和验证。
- 删除数据库记录后可能遗留物理文件，反之亦然。

### 建议修复

- `runs` 增加独立摘要列和 `updated_at`，历史列表只查摘要。
- API 增加分页和上限。
- 增加 Project / Run / Dataset 删除与文件级联清理。
- 增加按天数、总大小或数量的保留策略。
- 桌面日志轮转。
- SQLite 开启 WAL、foreign keys、busy timeout。
- 引入正式 migration 机制。

### 验收标准

- 数千条 Run 时历史列表仍只读取分页摘要。
- 删除 Run 后相关产物和事件按规则清理。
- Schema 可从旧版本稳定升级。

---

## DA-OPT-011 — Trace 默认持久化较多 Prompt 内容

### 现状

Planner 事件会记录 Prompt 快照，包括：

- 消息正文的头尾预览；
- 工具调用参数预览；
- 上下文预算；
- 模型响应预览。

这些事件直接写入 SQLite；导出时虽然有脱敏逻辑，但持久化前未统一完成同等级脱敏。

主要文件：

- `server/app/agent/planner.py`
- `server/app/memory/store.py`
- `server/app/api/trace_routes.py`

### 风险

- 项目上下文、业务描述、字段样例和局部数据可能长期保留。
- 用户可能以为普通运行日志不保存 Prompt 内容。
- 数据删除和 Trace 删除可能不同步。

### 建议修复

- 默认只保存 Token、时延、工具名、状态和安全摘要。
- 完整 diagnostic trace 改为显式开启。
- 写入数据库前统一脱敏。
- 增加 Trace 保留天数和一键清理。
- UI 明确展示当前诊断记录级别。

### 验收标准

- 默认模式下数据库不保存项目正文和数据样例预览。
- 开启诊断模式时用户能明确看到隐私提示和保留策略。

---

## DA-OPT-012 — 数据画像重复全表扫描

### 现状

`server/app/tools/dataframes.py`：

- CSV/Excel 完整读入 pandas；
- 每列执行 `dropna`、数值转换、空值统计、`nunique`、去重样例和 min/max；
- Excel 固定读取第一张工作表。

### 风险

- 50MB 宽表或高基数文本列可能占用较多内存和时间。
- 同一数据集多次运行会重复计算画像。
- 用户无法选择 Excel Sheet。

### 建议修复

- CSV 使用 DuckDB 或分块扫描。
- 超过阈值时使用采样画像，并在 UI 明确标记。
- 高基数字段使用近似 distinct count。
- 按文件 Hash 和画像版本缓存结果。
- Excel 增加 Sheet 选择和 workbook 元信息。
- 对宽表、高基数、大 CSV 做性能基准测试。

### 验收标准

- 相同数据集重复运行可复用画像。
- 大文件画像有稳定内存上限。
- 用户能看到画像是完整还是采样结果。

---

## DA-OPT-013 — CI 不完整且部分环境未固定

### 现状

当前有：

- `.github/workflows/server.yml`
- `.github/workflows/web.yml`

缺少 Desktop CI。Web CI 使用 `bun-version: latest`。Server CI 当前主要执行测试，没有看到 Ruff 和 mypy 作为门禁。

Desktop 本地脚本已包含测试、TypeScript 构建和 macOS 打包能力，但未进入持续集成。

### 建议修复

- 固定 Bun、Python 和 uv 版本。
- Server：compile、pytest、ruff、mypy。
- Web：test、build。
- Desktop：test、TypeScript build、`npm audit`。
- 在 macOS Runner 上定期执行 DMG 打包烟测。
- 增加一组代表性报告截图或 DOM 结构回归。
- 将关键 Workflow 设置为 main 分支保护的 required checks。

### 验收标准

- 相同提交使用固定工具链。
- Desktop 变更不能绕过 CI。
- 关键分支合并前必须通过所需检查。

---

## DA-OPT-014 — 前端报告模块体积和职责过重

### 现状

`apps/web/src/components/ArtifactModule.tsx` 同时负责：

- 历史 Run 列表；
- 产物导航；
- Markdown、表格、图表、Notebook、HTML 和 Visual Report 渲染；
- 验证结果；
- 证据展示；
- 报告导出；
- Web Report iframe；
- 多种 Visual Block 分派。

构建记录中也保留了较大单 JS chunk 警告；此前手动 vendor 拆分曾导致 Electron 循环依赖白屏。

### 风险

- 单文件变更影响面大。
- 测试难以隔离。
- 报告渲染代码难以按需加载。
- 后续继续增加 Visual Block 会放大维护成本。

### 建议修复

按职责拆分：

- `ArtifactRail`
- `ArtifactRenderer`
- `ManifestReport`
- `ReportExportMenu`
- `FileChartPreview`
- `WebReportPreview`
- `ValidationSummary`
- `ManifestBlockRegistry`

对重型渲染器使用动态导入，但必须通过构建级 Electron 烟测防止重新引入循环依赖。

### 验收标准

- 核心组件可独立单测。
- 报告 Block 新增不需要修改一个超大分派文件。
- Web 与 Electron 构建均通过，且不再出现白屏回归。

---

## 推荐修复批次

### 第一批：确定性、小范围修复

建议先完成：

1. DA-OPT-004：Skill / Template 路径边界。
2. DA-OPT-007：`temperature=0` 配置错误。
3. DA-OPT-003：Excel 上传预检。
4. DA-OPT-002：Orchestrator 顶层失败状态持久化。

这批修复影响面相对可控，且可通过明确的单元/接口测试验证。

### 第二批：运行引擎重构

1. DA-OPT-001：异步子进程和取消机制。
2. DA-OPT-005：资源限制与 Sandbox 边界。
3. DA-OPT-006：模型、工具、Token 和时间预算。
4. DA-OPT-008：运行结果状态分类。

这批建议先写运行状态设计，再分阶段提交，避免一次重写整个 Orchestrator。

### 第三批：工程化和长期维护

1. DA-OPT-009：iframe 隔离与导出方案。
2. DA-OPT-010：SQLite、分页、迁移和保留策略。
3. DA-OPT-011：Trace 隐私等级。
4. DA-OPT-012：画像性能和缓存。
5. DA-OPT-013：完整 CI。
6. DA-OPT-014：前端报告模块拆分。

---

## 每项修复建议记录格式

完成一项后，在本文件对应条目下追加：

```text
Status: Fixed / Accepted Risk / Deferred
Fix commit: <sha>
Validation:
- <command> -> <result>
- <command> -> <result>
Notes:
- <兼容性、迁移或剩余风险>
```

同时建议把重要安全或架构决策同步到：

- `docs/agent-handoff.md`
- `docs/progress.md`
- `docs/reviews.md`
- 新的 `docs/project-status-YYYY-MM-DD.md`（形成稳定 checkpoint 时）

---

## 当前不建议优先扩展的方向

在以上 P0/P1 问题处理前，不建议优先继续增加新的 Visual Block、报告样式或额外导出格式。当前更高收益的工作是确保：

- Run 一定能正确结束；
- 用户可以真正停止任务；
- 资源消耗有硬上限；
- 模型故障不会伪装成成功；
- 生成代码和生成 HTML 的边界清楚、可验证。
