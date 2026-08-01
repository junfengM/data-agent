from __future__ import annotations


def tokenize(text: str) -> set[str]:
    """Split text into lowercase tokens (split on non-alphanumeric, min length 2)."""
    import re
    return {t.lower() for t in re.split(r'[^a-zA-Z0-9\u4e00-\u9fff]+', text) if len(t) >= 2}


def score_evidence_item(block_text: str, item: dict) -> float:
    """Score a single evidence item against block text. Higher = better match.

    Scoring dimensions (weights tuned for precision):
    1. Name token overlap (weight 3.0): tokens from item title/name vs block text
    2. Source/path token overlap (weight 1.5): tokens from source or path
    3. Explicit id match (weight 5.0): block text contains the exact item id
    4. Dataset match (weight 2.0): block text contains dataset name
    5. Spec id match (weight 3.0): block text references chart spec id
    """
    block_tokens = tokenize(block_text)

    # 1. Name token overlap
    title = item.get("title", "")
    title_tokens = tokenize(title)
    intersection = block_tokens & title_tokens
    name_score = len(intersection) / max(len(title_tokens), 1) if title_tokens else 0.0

    # 2. Source/path token overlap
    source = item.get("source", "") or ""
    source_tokens = tokenize(source)
    if source_tokens:
        source_intersection = block_tokens & source_tokens
        source_score = len(source_intersection) / max(len(source_tokens), 1)
    else:
        source_score = 0.0

    # 3. Explicit id match
    item_id = item.get("id", "")
    id_match = 1.0 if item_id and item_id in block_text else 0.0

    # 4. Dataset match
    dataset = item.get("dataset", "") or ""
    dataset_tokens = tokenize(dataset)
    if dataset_tokens:
        dataset_intersection = block_tokens & dataset_tokens
        dataset_score = len(dataset_intersection) / max(len(dataset_tokens), 1)
    else:
        dataset_score = 0.0

    # 5. Spec id match
    spec_id = item.get("spec_id", "") or ""
    spec_match = 1.0 if spec_id and spec_id in block_text else 0.0

    return (
        3.0 * name_score
        + 1.5 * source_score
        + 5.0 * id_match
        + 2.0 * dataset_score
        + 3.0 * spec_match
    )


def link_evidence(
    block_text: str,
    evidence_items: list[dict],
    top_k: int = 3,
    min_score: float = 0.5,
) -> list[str]:
    """Score all evidence items against block text, return top-k item ids."""
    if not evidence_items:
        return []

    scored = [(score_evidence_item(block_text, item), item.get("id", "")) for item in evidence_items]
    scored.sort(key=lambda x: x[0], reverse=True)

    result: list[str] = []
    for score, item_id in scored:
        if score < min_score:
            break
        if len(result) >= top_k:
            break
        result.append(item_id)

    return result


def link_evidence_with_explanations(
    block_text: str,
    evidence_items: list[dict],
    top_k: int = 3,
    min_score: float = 0.5,
) -> tuple[list[str], list[dict]]:
    """Score evidence items and return both ids and link explanations."""
    if not evidence_items:
        return [], []

    scored_details = []
    for item in evidence_items:
        score = score_evidence_item(block_text, item)
        if score < min_score:
            continue
        title = item.get("title", "")
        matched_terms = list(tokenize(block_text) & tokenize(title))
        scored_details.append({
            "evidence_id": item.get("id", ""),
            "method": "text_similarity",
            "score": round(score, 4),
            "matched_terms": matched_terms[:10],
            "reason": (
                f"Matched {len(matched_terms)} term(s) from '{title}' "
                f"in block text (score={score:.2f})"
            ) if matched_terms else f"Low-confidence match (score={score:.2f})",
        })

    scored_details.sort(key=lambda x: x["score"], reverse=True)
    top = scored_details[:top_k]
    evidence_ids = [d["evidence_id"] for d in top]
    evidence_links = [{
        "evidence_id": d["evidence_id"],
        "method": d["method"],
        "score": d["score"],
        "matched_terms": d["matched_terms"],
        "reason": d["reason"],
    } for d in top]

    return evidence_ids, evidence_links
