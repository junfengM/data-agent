from app.models.schemas import CandidateAngle, MAX_CANDIDATE_ANGLES, MAX_SELECTED_ANGLES, MIN_ANGLE_SCORE, MIN_DATA_SUFFICIENCY


def _bounded_angles(angles: list[CandidateAngle], max_selected_count: int) -> list[CandidateAngle]:
    angles = angles[:MAX_CANDIDATE_ANGLES]

    for i, angle in enumerate(angles):
        if angle.composite_score < MIN_ANGLE_SCORE and angle.selected:
            data = angle.model_dump()
            data.update(selected=False, rejected_reason=f"score {angle.composite_score:.2f} below {MIN_ANGLE_SCORE}")
            angles[i] = CandidateAngle(**data)

    for i, angle in enumerate(angles):
        if angle.data_sufficiency_score < MIN_DATA_SUFFICIENCY and angle.selected:
            data = angle.model_dump()
            data.update(selected=False, rejected_reason=f"data sufficiency {angle.data_sufficiency_score:.2f} below {MIN_DATA_SUFFICIENCY}")
            angles[i] = CandidateAngle(**data)

    selected = sorted([angle for angle in angles if angle.selected], key=lambda angle: angle.composite_score, reverse=True)
    capped_ids = {angle.id for angle in selected[max_selected_count:]}
    for i, angle in enumerate(angles):
        if angle.selected and angle.id in capped_ids:
            data = angle.model_dump()
            data.update(selected=False, rejected_reason=f"outside top {max_selected_count} by score")
            angles[i] = CandidateAngle(**data)

    for i, angle in enumerate(angles):
        if not angle.selected and not angle.rejected_reason:
            data = angle.model_dump()
            data["rejected_reason"] = "not selected"
            angles[i] = CandidateAngle(**data)

    return angles


def enforce_angle_boundaries(
    angles: list[CandidateAngle] | None = None,
    *,
    report_md: str | None = None,
    candidate_angles: list[CandidateAngle] | None = None,
    min_selected: int | None = None,
    max_selected: int | None = None,
):
    active_angles = candidate_angles if candidate_angles is not None else angles
    return_tuple = candidate_angles is not None or report_md is not None

    if not active_angles:
        return (report_md or "", []) if return_tuple else []

    bounded = _bounded_angles(active_angles, max_selected or MAX_SELECTED_ANGLES)

    if min_selected:
        selected_count = sum(1 for angle in bounded if angle.selected)
        if selected_count < min_selected:
            selected_ids = {angle.id for angle in bounded if angle.selected}
            candidates = sorted(
                [angle for angle in bounded if angle.id not in selected_ids],
                key=lambda angle: angle.composite_score,
                reverse=True,
            )
            promote_ids = {angle.id for angle in candidates[: min_selected - selected_count]}
            next_bounded: list[CandidateAngle] = []
            for angle in bounded:
                if angle.id in promote_ids:
                    data = angle.model_dump()
                    data.update(selected=True, rejected_reason=None)
                    next_bounded.append(CandidateAngle(**data))
                else:
                    next_bounded.append(angle)
            bounded = _bounded_angles(next_bounded, max_selected or MAX_SELECTED_ANGLES)

    if return_tuple:
        return report_md or "", bounded
    return bounded
