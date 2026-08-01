"""Artifact manifest building: report blocks, chart/table manifest, evidence linking, snapshots.

This module is now a thin orchestration facade. Implementation details live in:
  artifact_manifest_helpers.py  – path, tokenize, heading, directory-section helpers
  artifact_manifest_charts.py   – chart scoring, spec matching, encoding, row finding
  artifact_manifest_tables.py   – table scoring
  artifact_manifest_semantics.py – metric cards, angle linking, conflict detection
  artifact_manifest_blocks.py    – build_report_blocks
"""
import datetime as dt
import re
from typing import Any
from uuid import uuid4

from app.models.schemas import (
    AnalysisProject,
    AnalysisRequest,
    ArtifactBlock,
    ArtifactBlockType,
    ArtifactManifest,
    ArtifactSnapshot,
    DatasetProfile,
    EvidenceEntry,
    EvidenceLink,
    ManifestChart,
    ManifestSource,
    ManifestTable,
    ProjectContext,
    SourceQuery,
    TableColumn,
    VisualPlanItem,
)
from app.tools.chart_contract import FILE_CHART_TYPES
from app.agent.report_planning import (
    apply_report_plan_to_blocks,
    attach_claims_to_blocks,
    build_report_plan,
    evidence_priority_for_text,
    extract_action_items,
    infer_report_intent,
)
from app.agent.visual_report_planner import (
    build_visual_report_blocks,
    merge_visual_blocks_into_reading_flow,
)
from app.tools.chart_contract import normalize_chart_specs
from app.tools.evidence_linking import link_evidence_with_explanations

# Re-export from sub-modules for backward compatibility
from app.agent.artifact_manifest_helpers import (
    _asset_path_for_package,
    _looks_like_directory_section,
    _normalize_markdown_heading,
)
from app.agent.artifact_manifest_charts import (
    _chart_score,
    _chart_spec_for,
    _find_rows_for_chart,
    _merge_chart_info_and_spec,
    _promote_native_chart_if_possible,
    infer_chart_encodings,
    normalize_chart_type,
)
from app.agent.artifact_manifest_tables import _table_score
from app.agent.artifact_manifest_semantics import (
    _build_metric_cards,
    link_angles_to_items,
)


def build_artifact_manifest(
    title: str,
    report_md: str,
    step_results: list[dict],
    profiles: list[DatasetProfile],
    project_contexts: list[ProjectContext] | None = None,
    candidate_angles: list[Any] | None = None,
    chart_specs: list[dict] | None = None,
    plan_caveats: list[str] | None = None,
    semantic_layer: dict | None = None,
    visual_plan: list[dict[str, Any]] | None = None,
    visual_recipes: list[dict[str, Any]] | None = None,
) -> tuple[ArtifactManifest, ArtifactSnapshot]:
    """Build manifest + snapshot from step results and report markdown."""
    now = dt.datetime.now(dt.UTC).isoformat()
    chart_specs = normalize_chart_specs(chart_specs)
    report_intent = infer_report_intent(title, report_md)

    all_tables: list[dict] = []
    all_charts: list[dict] = []
    for result in step_results:
        all_tables.extend(result.get("tables", []))
        all_charts.extend(result.get("charts", []))

    chart_names = [c.get("name", "") for c in all_charts]
    table_names = [t.get("name", "") for t in all_tables]
    chart_angle_links = link_angles_to_items(chart_names, candidate_angles)
    table_angle_links = link_angles_to_items(table_names, candidate_angles)

    manifest_charts: list[ManifestChart] = []
    chart_id_map: dict[str, str] = {}
    chart_info_by_id: dict[str, dict[str, Any]] = {}
    chart_spec_by_id: dict[str, dict[str, Any]] = {}
    for chart_info in all_charts:
        cid = f"chart_{uuid4().hex[:8]}"
        chart_name = chart_info.get("name", "Chart")
        chart_spec = _chart_spec_for(chart_name, chart_specs)
        chart_type = chart_spec.get("chart_type") or chart_info.get("type", "bar")
        dataset_key = f"ds_{cid}"
        encoding_input = _merge_chart_info_and_spec(chart_info, chart_spec, chart_type)

        is_file_chart = chart_info.get("type") in FILE_CHART_TYPES
        manifest_charts.append(ManifestChart(
            id=cid,
            title=chart_name,
            type=normalize_chart_type(chart_type),
            dataset=dataset_key,
            encodings=infer_chart_encodings(encoding_input),
            intent=chart_info.get("intent") or chart_spec.get("intent"),
            compatible_types=chart_info.get("compatible_types", []) or chart_spec.get("compatible_types", []) or [],
            unit=chart_info.get("unit") or chart_spec.get("unit"),
            source_id=chart_info.get("source_id"),
            x_axis_title=chart_info.get("x_axis_title") or chart_info.get("x_axis") or chart_spec.get("x_field"),
            y_axis_title=chart_info.get("y_axis_title") or chart_info.get("y_axis") or ", ".join(str(v) for v in chart_spec.get("y_fields", []) or []),
            value_format=chart_info.get("value_format") or chart_spec.get("value_format"),
            description=chart_info.get("description") or chart_spec.get("title"),
            render_mode="file" if is_file_chart else "vega",
            asset_path=_asset_path_for_package(chart_info.get("path", "")),
            linked_angle_ids=chart_angle_links.get(chart_name, []),
        ))
        chart_id_map[chart_name.lower()] = cid
        chart_info_by_id[cid] = chart_info
        chart_spec_by_id[cid] = chart_spec

    manifest_tables: list[ManifestTable] = []
    table_id_map: dict[str, str] = {}
    for table_info in all_tables:
        tid = f"table_{uuid4().hex[:8]}"
        table_name = table_info.get("name", "Table")
        columns = table_info.get("columns", [])
        dataset_key = f"ds_{tid}"
        priority = "appendix" if table_name.lower() in {"full_sales_data", "raw_data"} else "secondary"

        manifest_tables.append(ManifestTable(
            id=tid,
            title=table_name,
            dataset=dataset_key,
            columns=[TableColumn(field=col, label=col) for col in columns],
            linked_angle_ids=table_angle_links.get(table_name, []),
            evidence_priority=priority,
        ))
        table_id_map[table_name.lower()] = tid

    cards, card_datasets = _build_metric_cards(semantic_layer, all_tables)

    heading_pattern = re.compile(r'^(#{1,4})\s+(.+)$', re.MULTILINE)
    blocks: list[ArtifactBlock] = []
    headings = [
        {"level": len(m.group(1)), "text": m.group(2).strip(), "start": m.start(), "end": m.end()}
        for m in heading_pattern.finditer(report_md)
    ]

    used_chart_ids: set[str] = set()
    used_table_ids: set[str] = set()
    has_h1 = False
    inserted_cards = False

    if headings:
        if headings[0]["start"] > 0:
            preamble = report_md[:headings[0]["start"]].strip()
            if preamble:
                blocks.append(ArtifactBlock(
                    id=f"block_{uuid4().hex[:8]}",
                    type=ArtifactBlockType.markdown,
                    body=preamble,
                    evidence_priority=evidence_priority_for_text(preamble, has_evidence=False),
                    report_intent=report_intent,
                ))

        for i, heading in enumerate(headings):
            content = report_md[heading["end"]:headings[i + 1]["start"]].strip() if i + 1 < len(headings) else report_md[heading["end"]:].strip()
            is_directory_section = _looks_like_directory_section(heading["text"], content)

            markdown_body, level = _normalize_markdown_heading(heading["text"], content, heading["level"], has_h1=has_h1)
            has_h1 = has_h1 or level == 1
            block_text = f"{heading['text']} {content}"

            evidence_items: list[dict] = []
            for chart_info in all_charts:
                chart_name = chart_info.get("name", "")
                cid = chart_id_map.get(chart_name.lower(), "")
                if cid:
                    evidence_items.append({"id": cid, "type": "chart", "title": chart_name, "source": chart_info.get("source") or chart_info.get("path", ""), "dataset": f"ds_{cid}", "spec_id": chart_info.get("spec_id", "")})
            for table_info in all_tables:
                table_name = table_info.get("name", "")
                tid = table_id_map.get(table_name.lower(), "")
                if tid:
                    evidence_items.append({"id": tid, "type": "table", "title": table_name, "source": table_info.get("source") or table_info.get("path", ""), "dataset": f"ds_{tid}", "spec_id": ""})

            linked_evidence_ids, evidence_link_dicts = link_evidence_with_explanations(block_text, evidence_items, top_k=3)
            evidence_priority = evidence_priority_for_text(block_text, has_evidence=bool(linked_evidence_ids))
            if is_directory_section:
                evidence_priority = "appendix"

            chart_scores = [(c.id, _chart_score(block_text, c, chart_specs)) for c in manifest_charts if c.id not in used_chart_ids]
            chart_scores = sorted((item for item in chart_scores if item[1] > 0), key=lambda x: x[1], reverse=True)
            matched_chart_id = chart_scores[0][0] if chart_scores else None

            table_scores = [(t.id, _table_score(block_text, t)) for t in manifest_tables if t.id not in used_table_ids]
            table_scores = sorted((item for item in table_scores if item[1] > 1), key=lambda x: x[1], reverse=True)
            matched_table_id = table_scores[0][0] if table_scores else None

            block_angle_ids: list[str] = []
            if matched_chart_id:
                block_angle_ids.extend(next((list(c.linked_angle_ids) for c in manifest_charts if c.id == matched_chart_id), []))
            if matched_table_id:
                block_angle_ids.extend(next((list(t.linked_angle_ids) for t in manifest_tables if t.id == matched_table_id), []))
            block_angle_ids = list(dict.fromkeys(block_angle_ids))

            blocks.append(ArtifactBlock(
                id=f"block_{uuid4().hex[:8]}",
                type=ArtifactBlockType.markdown,
                body=markdown_body,
                evidence_ids=list(linked_evidence_ids),
                evidence_links=[EvidenceLink(**d) for d in evidence_link_dicts],
                linked_angle_ids=block_angle_ids,
                evidence_priority=evidence_priority,
                report_intent=report_intent,
                block_origin="artifact_manifest",
            ))

            if cards and not inserted_cards and len(blocks) <= 3:
                blocks.append(ArtifactBlock(
                    id=f"block_{uuid4().hex[:8]}",
                    type=ArtifactBlockType.metric_strip,
                    card_ids=[card.id for card in cards],
                    evidence_priority="primary",
                    report_intent=report_intent,
                    renderer_target="evidence_component",
                    block_origin="artifact_manifest",
                ))
                inserted_cards = True

            if matched_chart_id is not None:
                blocks.append(ArtifactBlock(
                    id=f"block_{uuid4().hex[:8]}",
                    type=ArtifactBlockType.chart,
                    chart_id=matched_chart_id,
                    evidence_ids=[matched_chart_id],
                    evidence_priority=evidence_priority,
                    report_intent=report_intent,
                    renderer_target="evidence_component",
                    block_origin="artifact_manifest",
                ))
                used_chart_ids.add(matched_chart_id)

            if matched_table_id is not None:
                table_priority = evidence_priority if evidence_priority != "diagnostic" else "secondary"
                blocks.append(ArtifactBlock(
                    id=f"block_{uuid4().hex[:8]}",
                    type=ArtifactBlockType.table,
                    table_id=matched_table_id,
                    evidence_ids=[matched_table_id],
                    evidence_priority=table_priority,
                    report_intent=report_intent,
                    renderer_target="evidence_component",
                    block_origin="artifact_manifest",
                ))
                used_table_ids.add(matched_table_id)
    else:
        if report_md.strip():
            body, level = _normalize_markdown_heading(title, report_md.strip(), 1, has_h1=False)
            blocks.append(ArtifactBlock(
                id=f"block_{uuid4().hex[:8]}",
                type=ArtifactBlockType.markdown,
                body=body,
                evidence_priority=evidence_priority_for_text(body, has_evidence=False),
                report_intent=report_intent,
                block_origin="artifact_manifest",
            ))
        if cards:
            blocks.append(ArtifactBlock(
                id=f"block_{uuid4().hex[:8]}",
                type=ArtifactBlockType.metric_strip,
                card_ids=[card.id for card in cards],
                evidence_priority="primary",
                report_intent=report_intent,
                renderer_target="evidence_component",
                block_origin="artifact_manifest",
            ))
            inserted_cards = True

    # Build datasets early so visual_blocks can use them before appendix calculation.
    datasets: dict[str, list[dict]] = dict(card_datasets)
    for chart in manifest_charts:
        chart_data = chart_info_by_id.get(chart.id)
        chart_spec = chart_spec_by_id.get(chart.id)
        rows = _find_rows_for_chart(chart, chart_data, chart_spec, all_tables)
        datasets[chart.dataset] = rows
        if rows:
            _promote_native_chart_if_possible(chart, rows, chart_data)

    for table in manifest_tables:
        table_data = next((t for t in all_tables if t.get("name", "").lower() == table.title.lower()), None)
        if table_data:
            rows = table_data.get("preview", table_data.get("rows", []))
            datasets[table.dataset] = rows if isinstance(rows, list) else []

    visual_blocks = build_visual_report_blocks(
        title=title,
        report_md=report_md,
        cards=cards,
        tables=manifest_tables,
        datasets=datasets,
        plan_caveats=plan_caveats,
        charts=manifest_charts,
        used_chart_ids=set(used_chart_ids),
    )
    for block in visual_blocks:
        block.report_intent = report_intent
        if block.evidence_priority == "secondary":
            block.evidence_priority = "primary"

    promoted_chart_ids = {
        str(block.chart_id)
        for block in visual_blocks
        if block.chart_id
    }
    used_chart_ids.update(promoted_chart_ids)

    unused_chart_ids = [c.id for c in manifest_charts if c.id not in used_chart_ids]
    unused_table_ids = [t.id for t in manifest_tables if t.id not in used_table_ids and t.title.lower() not in {"full_sales_data", "raw_data"}]
    if unused_chart_ids or unused_table_ids:
        blocks.append(ArtifactBlock(
            id=f"block_{uuid4().hex[:8]}",
            type=ArtifactBlockType.markdown,
            body="## 附录：补充图表与数据表\n\n以下材料未放入主报告正文，用于补充审阅。",
            evidence_priority="appendix",
            report_intent=report_intent,
            renderer_target="appendix",
            block_origin="artifact_manifest",
        ))
        for cid in unused_chart_ids:
            blocks.append(ArtifactBlock(
                id=f"block_{uuid4().hex[:8]}",
                type=ArtifactBlockType.chart,
                chart_id=cid,
                evidence_ids=[cid],
                evidence_priority="appendix",
                report_intent=report_intent,
                renderer_target="appendix",
                block_origin="artifact_manifest",
            ))
        for tid in unused_table_ids:
            blocks.append(ArtifactBlock(
                id=f"block_{uuid4().hex[:8]}",
                type=ArtifactBlockType.table,
                table_id=tid,
                evidence_ids=[tid],
                evidence_priority="appendix",
                report_intent=report_intent,
                renderer_target="appendix",
                block_origin="artifact_manifest",
            ))

    sources: list[ManifestSource] = []
    for profile in profiles:
        sid = f"source_{uuid4().hex[:8]}"
        sources.append(ManifestSource(
            id=sid,
            label=profile.filename,
            query=SourceQuery(description=f"Dataset profile: {profile.row_count} rows, {profile.column_count} columns", tables_used=[profile.filename]),
        ))
    for i, result in enumerate(step_results):
        if result.get("code"):
            sid = f"source_step_{uuid4().hex[:8]}"
            sources.append(ManifestSource(
                id=sid,
                label=f"Step {i+1}: {result.get('name', 'Unknown')}",
                query=SourceQuery(engine="python", description=result.get("description", ""), tables_used=[p.filename for p in profiles] if profiles else []),
                step_id=result.get("name", f"step_{i+1}"),
            ))

    if visual_blocks:
        blocks = merge_visual_blocks_into_reading_flow(blocks, visual_blocks)

    claims = attach_claims_to_blocks(blocks, sources, plan_caveats)
    actions = extract_action_items(report_md, claims)
    if actions:
        action_block = ArtifactBlock(
            id=f"block_{uuid4().hex[:8]}",
            type=ArtifactBlockType.next_action_list,
            title="建议行动",
            subtitle="从报告中明确出现的建议/下一步提取，不新增未支持动作。",
            items=[action.model_dump(mode="json") for action in actions],
            action_ids=[action.id for action in actions],
            evidence_ids=list(dict.fromkeys(eid for action in actions for eid in action.evidence_ids)),
            evidence_priority="primary",
            report_intent=report_intent,
            section_role="actions",
            renderer_target="md_visual",
            block_origin="report_plan",
        )
        blocks = merge_visual_blocks_into_reading_flow(blocks, [action_block])

    report_plan = build_report_plan(report_intent, claims, actions)
    blocks = apply_report_plan_to_blocks(blocks, report_plan)

    evidence_map: list[EvidenceEntry] = []
    for i, result in enumerate(step_results):
        step_id = result.get("name", f"step_{i+1}")
        for chart_info in result.get("charts", []):
            chart_name = chart_info.get("name", "Chart")
            cid = chart_id_map.get(chart_name.lower())
            if cid:
                chart_data = chart_info.get("data", chart_info.get("preview", []))
                if not isinstance(chart_data, list):
                    chart_data = datasets.get(next((c.dataset for c in manifest_charts if c.id == cid), ""), [])
                priority = "primary" if any(cid in claim.evidence_ids for claim in claims) else "secondary"
                evidence_map.append(EvidenceEntry(id=cid, type="chart", title=chart_name, source_dataset=profiles[0].filename if profiles else None, step_id=step_id, row_count=len(chart_data) if isinstance(chart_data, list) else None, caveats=plan_caveats or [], linked_angle_ids=chart_angle_links.get(chart_name, []), priority=priority))
        for table_info in result.get("tables", []):
            table_name = table_info.get("name", "Table")
            tid = table_id_map.get(table_name.lower())
            if tid:
                table_data = table_info.get("preview", table_info.get("rows", []))
                priority = "primary" if any(tid in claim.evidence_ids for claim in claims) else "secondary"
                if table_name.lower() in {"full_sales_data", "raw_data"}:
                    priority = "appendix"
                evidence_map.append(EvidenceEntry(id=tid, type="table", title=table_name, source_dataset=profiles[0].filename if profiles else None, step_id=step_id, row_count=len(table_data) if isinstance(table_data, list) else None, caveats=plan_caveats or [], linked_angle_ids=table_angle_links.get(table_name, []), priority=priority))

    manifest = ArtifactManifest(
        version=1,
        surface="report",
        title=title,
        generated_at=now,
        report_intent=report_intent,
        report_plan=report_plan,
        claims=claims,
        actions=actions,
        blocks=blocks,
        charts=manifest_charts,
        tables=manifest_tables,
        cards=cards,
        sources=sources,
        candidate_angles=[a.model_dump(mode="json") for a in candidate_angles] if candidate_angles else [],
        chart_specs=chart_specs,
        visual_plan=_normalize_visual_plan(visual_plan),
        visual_recipes=list(visual_recipes or [])[:40],
        semantic_layer=semantic_layer,
    )

    snapshot = ArtifactSnapshot(version=1, status="ready", generated_at=now, datasets=datasets, evidence_map=evidence_map)
    return manifest, snapshot


def _normalize_visual_plan(value: list[dict[str, Any]] | None) -> list[VisualPlanItem]:
    items: list[VisualPlanItem] = []
    for raw in value or []:
        if not isinstance(raw, dict):
            continue
        try:
            payload = dict(raw)
            payload["priority"] = str(payload.get("priority") or "primary")
            items.append(VisualPlanItem(**payload))
        except Exception:
            continue
    return items[:24]


def draft_fallback_report(
    request: AnalysisRequest,
    skill_id: str,
    profiles: list[DatasetProfile],
    profile_markdown: str,
    project: AnalysisProject | None,
    context_markdown: str,
    step_results: list[dict],
    plan: dict,
) -> str:
    dataset_line = ", ".join(request.dataset_ids) if request.dataset_ids else "No dataset selected"
    project_line = f"{project.name} ({project.id})" if project else "No analysis project"

    successful = [r for r in step_results if r.get("returncode") == 0]
    failed = [r for r in step_results if r.get("returncode") not in (0, None)]
    all_tables: list[dict] = []
    all_charts: list[dict] = []
    for r in step_results:
        all_tables.extend(r.get("tables", []))
        all_charts.extend(r.get("charts", []))

    lines = [
        "# 分析报告（自动恢复版）",
        "",
        "> LLM 最终报告合成未完成，但系统已恢复本次运行中成功生成的分析证据。以下内容来自已执行步骤、表格、图表和运行日志。",
        "",
        f"**问题:** {request.question}",
        f"**项目:** {project_line}",
        f"**技能:** {skill_id}",
        f"**数据集:** {dataset_line}",
        "",
        "## 一、运行状态",
        "",
        "- Planner synthesis: 未完成/降级",
        f"- 证据生成: {'已完成' if successful else '部分完成'}",
        f"- 成功步骤: {len(successful)}",
        f"- 失败步骤: {len(failed)}",
        "",
    ]

    if successful:
        findings: list[str] = []
        for r in successful:
            stdout = (r.get("stdout") or "").strip()
            if stdout:
                for line_text in stdout.splitlines()[:5]:
                    line_text = line_text.strip()
                    if line_text and len(line_text) > 10:
                        findings.append(f"- {line_text[:200]}")
                        if len(findings) >= 6:
                            break
            if len(findings) >= 6:
                break
        if findings:
            lines.extend([
                "## 二、核心发现摘要",
                "",
                "从成功步骤输出中提取的关键发现：",
                "",
                *findings,
                "",
            ])
        else:
            lines.extend([
                "## 二、核心发现摘要",
                "",
                "成功步骤已执行，详情见下方表格和图表证据。",
                "",
            ])

    if all_charts:
        lines.extend(["## 三、已生成图表", ""])
        for c in all_charts:
            chart_name = c.get("name", "Chart")
            chart_path = c.get("path", "")
            asset_name = chart_path.split("/")[-1] if "/" in chart_path else chart_path
            chart_type = c.get("type", "unknown")
            title = c.get("title") or chart_name
            if asset_name:
                lines.append(f"- [{title}]({asset_name}) （类型: {chart_type}）")
            else:
                lines.append(f"- {title} （类型: {chart_type}）")
        lines.append("")

    if all_tables:
        lines.extend(["## 四、关键表格证据", ""])
        for t in all_tables[:8]:
            t_name = t.get("name", "Table")
            columns = t.get("columns", [])
            preview = t.get("preview", [])
            lines.append(f"### {t_name}")
            if columns:
                lines.append("")
                lines.append("| " + " | ".join(str(c) for c in columns[:6]) + " |")
                lines.append("|" + "|".join("---" for _ in columns[:6]) + "|")
                for row in preview[:5]:
                    if isinstance(row, dict):
                        vals = [str(row.get(c, ""))[:40] for c in columns[:6]]
                    elif isinstance(row, list):
                        vals = [str(v)[:40] for v in row[:6]]
                    else:
                        vals = [str(row)[:40]]
                    lines.append("| " + " | ".join(vals) + " |")
            lines.append("")

    if failed:
        lines.extend(["## 五、失败步骤与影响", ""])
        for r in failed:
            name = r.get("name", "Step")
            rc = r.get("returncode", "?")
            stderr = (r.get("stderr") or "")[:500]
            lines.append(f"- **{name}**: returncode={rc}")
            if stderr:
                lines.append(f"  ```\n  {stderr}\n  ```")
        lines.append("")

    lines.extend([
        "## 六、建议下一步",
        "",
        "- 重新运行 synthesis 以获得完整的 LLM 生成报告",
        "- 检查失败步骤的变量定义和数据可用性",
        "- 检查增长率分母为 0 的展示（如出现 inf%）",
        "- 检查数据质量异常分类和商品名称",
        "",
    ])

    if plan.get("caveats"):
        lines.extend(["## 附录：注意事项", ""])
        for caveat in plan.get("caveats", []):
            lines.append(f"- {caveat}")
        lines.append("")

    if context_markdown and context_markdown.strip():
        lines.extend([
            "## 项目上下文",
            "",
            context_markdown,
            "",
        ])

    if profile_markdown and profile_markdown.strip():
        lines.extend([
            "## 数据集概况",
            "",
            profile_markdown,
            "",
        ])

    return "\n".join(lines)
