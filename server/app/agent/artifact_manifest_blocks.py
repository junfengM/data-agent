"""Report block construction (extracted from artifact_manifest.py)."""
import re

from app.models.schemas import DatasetProfile, ProjectContext, ReportBlock, ReportBlockType
from app.tools.chart_contract import FILE_CHART_TYPES


def build_report_blocks(
    title: str,
    report_md: str,
    step_results: list[dict],
    plan_caveats: list[str],
    profiles: list[DatasetProfile],
    project_contexts: list[ProjectContext] | None = None,
) -> list[ReportBlock]:
    blocks: list[ReportBlock] = []

    blocks.append(ReportBlock(
        type=ReportBlockType.heading,
        data={"text": title, "level": 1},
    ))

    all_tables = []
    all_charts = []
    for result in step_results:
        for table_info in result.get("tables", []):
            all_tables.append(table_info)
        for chart_info in result.get("charts", []):
            all_charts.append(chart_info)

    heading_pattern = re.compile(r'^(#{2,4})\s+(.+)$', re.MULTILINE)

    headings = []
    for match in heading_pattern.finditer(report_md):
        level = len(match.group(1))
        text = match.group(2).strip()
        headings.append({
            "level": level,
            "text": text,
            "start": match.start(),
            "end": match.end(),
        })

    if headings:
        if headings[0]["start"] > 0:
            preamble = report_md[:headings[0]["start"]].strip()
            if preamble:
                blocks.append(ReportBlock(
                    type=ReportBlockType.prose,
                    data={"markdown": preamble},
                ))

        for i, heading in enumerate(headings):
            blocks.append(ReportBlock(
                type=ReportBlockType.heading,
                data={"text": heading["text"], "level": heading["level"]},
            ))

            if i + 1 < len(headings):
                content = report_md[heading["end"]:headings[i + 1]["start"]].strip()
            else:
                content = report_md[heading["end"]:].strip()

            if content:
                content_lower = content.lower()

                for table_info in all_tables:
                    table_name = table_info.get("name", "").lower()
                    if table_name and table_name in content_lower:
                        blocks.append(ReportBlock(
                            type=ReportBlockType.table,
                            data={
                                "title": table_info.get("name", "Table"),
                                "columns": [{"key": c, "label": c} for c in table_info.get("columns", [])],
                                "rows": table_info.get("preview", []),
                            },
                        ))

                blocks.append(ReportBlock(
                    type=ReportBlockType.prose,
                    data={"markdown": content},
                ))
    elif report_md.strip():
        blocks.append(ReportBlock(
            type=ReportBlockType.prose,
            data={"markdown": report_md.strip()},
        ))

    for chart_info in all_charts[:3]:
        is_file_type = chart_info.get("type") in FILE_CHART_TYPES
        blocks.append(ReportBlock(
            type=ReportBlockType.chart,
            data={
                "title": chart_info.get("name", "Chart"),
                "chart_type": chart_info.get("type", "bar"),
                "path": chart_info.get("path"),
                "description": chart_info.get("description", ""),
                "render_mode": "file" if is_file_type else "vega",
            },
        ))

    if plan_caveats:
        for caveat in plan_caveats:
            blocks.append(ReportBlock(
                type=ReportBlockType.callout,
                data={"severity": "warning", "text": caveat},
            ))

    if project_contexts:
        context_parts: list[str] = []
        for ctx in project_contexts:
            label = ctx.kind.replace("_", " ").title()
            context_parts.append(f"{label}：{ctx.body}")
        blocks.append(ReportBlock(
            type=ReportBlockType.callout,
            data={"severity": "info", "text": "\n".join(context_parts)},
        ))

    for profile in profiles:
        blocks.append(ReportBlock(
            type=ReportBlockType.source_note,
            data={"text": f"{profile.filename}: {profile.row_count} rows, {profile.column_count} columns"},
        ))

    return blocks
