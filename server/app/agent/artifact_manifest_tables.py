"""Table manifest helpers (extracted from artifact_manifest.py)."""
from app.models.schemas import ManifestTable
from app.agent.artifact_manifest_helpers import _tokenize


def _table_score(block_text: str, table: ManifestTable) -> int:
    text = block_text.lower()
    score = 0
    if table.title.lower() in text:
        score += 8
    score += len(_tokenize(text) & _tokenize(table.title))
    for col in table.columns:
        if col.field.lower() in text:
            score += 1
    return score
