from pathlib import Path
from html import escape


def write_markdown_report(artifacts_dir: Path, run_id: str, title: str, body: str) -> Path:
    run_dir = artifacts_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{slugify(title)}.md"
    path.write_text(body, encoding="utf-8")
    return path


def write_html_report(artifacts_dir: Path, run_id: str, title: str, markdown_body: str) -> Path:
    run_dir = artifacts_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{slugify(title)}.html"
    html = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            f"  <title>{escape(title)}</title>",
            "  <style>",
            "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; color: #18202c; }",
            "    main { max-width: 960px; margin: 0 auto; }",
            "    pre { white-space: pre-wrap; line-height: 1.55; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            f"    <pre>{escape(markdown_body)}</pre>",
            "  </main>",
            "</body>",
            "</html>",
        ]
    )
    path.write_text(html, encoding="utf-8")
    return path


def slugify(value: str) -> str:
    return "-".join(value.lower().strip().replace("_", "-").split())
