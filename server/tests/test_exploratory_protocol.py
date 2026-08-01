import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    CandidateAngle, RunResponse, Artifact, ArtifactType,
    MAX_CANDIDATE_ANGLES, MAX_SELECTED_ANGLES,
)
from app.agent.semantic_findings import enforce_angle_boundaries
from app.memory.store import MemoryStore


class TestCandidateAngleModel:
    def test_create_minimal(self):
        angle = CandidateAngle(question="How has revenue changed over time?")
        assert angle.question == "How has revenue changed over time?"
        assert angle.id is not None
        assert len(angle.id) == 8

    def test_defaults(self):
        angle = CandidateAngle(question="test")
        assert angle.selected is False
        assert angle.dimensions == []
        assert angle.measures == []
        assert angle.expected_evidence == ""
        assert angle.impact_score == 0.0
        assert angle.confidence_score == 0.0
        assert angle.actionability_score == 0.0
        assert angle.novelty_score == 0.0
        assert angle.relevance_score == 0.0
        assert angle.data_sufficiency_score == 0.0
        assert angle.rejected_reason is None

    def test_full_creation(self):
        angle = CandidateAngle(
            question="Revenue trend by category",
            dimensions=["month", "category"],
            measures=["revenue", "orders"],
            expected_evidence="line chart, monthly aggregation",
            impact_score=0.9,
            confidence_score=0.85,
            actionability_score=0.7,
            novelty_score=0.3,
            relevance_score=0.95,
            data_sufficiency_score=0.8,
            selected=True,
            rejected_reason=None,
        )
        assert angle.question == "Revenue trend by category"
        assert angle.dimensions == ["month", "category"]
        assert angle.measures == ["revenue", "orders"]
        assert angle.selected is True

    def test_serialization(self):
        angle = CandidateAngle(
            question="Revenue vs orders correlation",
            dimensions=["month"],
            measures=["revenue", "orders"],
            expected_evidence="scatter plot",
            impact_score=0.8,
            confidence_score=0.6,
            actionability_score=0.5,
            novelty_score=0.4,
            relevance_score=0.9,
            data_sufficiency_score=0.7,
            selected=False,
            rejected_reason="correlation too weak",
        )
        dumped = angle.model_dump(mode="json")
        assert dumped["question"] == "Revenue vs orders correlation"
        assert dumped["dimensions"] == ["month"]
        assert dumped["measures"] == ["revenue", "orders"]
        assert dumped["expected_evidence"] == "scatter plot"
        assert dumped["selected"] is False
        assert dumped["rejected_reason"] == "correlation too weak"
        assert dumped["id"] == angle.id
        assert dumped["id"] is not None

    def test_json_roundtrip(self):
        angle = CandidateAngle(
            question="Monthly active users by region",
            dimensions=["month", "region"],
            measures=["active_users"],
            expected_evidence="bar chart, regional faceting",
            impact_score=0.85,
            confidence_score=0.9,
            actionability_score=0.75,
            novelty_score=0.2,
            relevance_score=0.88,
            data_sufficiency_score=0.95,
            selected=True,
        )
        json_str = json.dumps(angle.model_dump(mode="json"))
        reloaded = CandidateAngle(**json.loads(json_str))
        assert reloaded.question == angle.question
        assert reloaded.dimensions == angle.dimensions
        assert reloaded.measures == angle.measures
        assert reloaded.selected == angle.selected
        assert reloaded.impact_score == angle.impact_score

    def test_scoring_fields_range(self, subtests):
        """All scoring fields must accept values in 0.0-1.0 range."""
        valid_scores = [0.0, 0.5, 1.0]
        score_fields = [
            "impact_score", "confidence_score", "actionability_score",
            "novelty_score", "relevance_score", "data_sufficiency_score",
        ]
        for field in score_fields:
            for score in valid_scores:
                with subtests.test(msg=f"{field}={score}"):
                    angle = CandidateAngle(question="test", **{field: score})
                    assert getattr(angle, field) == score

    def test_scoring_fields_reject_out_of_range(self):
        """Each score field must raise ValidationError for values < 0.0 or > 1.0."""
        score_fields = [
            "impact_score", "confidence_score", "actionability_score",
            "novelty_score", "relevance_score", "data_sufficiency_score",
        ]
        for field in score_fields:
            with pytest.raises(ValidationError, match=field):
                CandidateAngle(question="test", **{field: -0.1})
            with pytest.raises(ValidationError, match=field):
                CandidateAngle(question="test", **{field: 1.1})

    def test_id_is_unique(self):
        angles = [CandidateAngle(question="test") for _ in range(20)]
        ids = {a.id for a in angles}
        assert len(ids) == 20


class TestCandidateAnglePersistence:
    @pytest.fixture
    def store(self, tmp_path: Path) -> MemoryStore:
        return MemoryStore(tmp_path / "test.db")

    def test_candidate_angles_store_roundtrip(self, store: MemoryStore):
        ca_selected = CandidateAngle(
            question="Revenue trend by month",
            dimensions=["month"],
            measures=["revenue"],
            expected_evidence="line chart, monthly aggregation",
            impact_score=0.9,
            confidence_score=0.85,
            actionability_score=0.7,
            novelty_score=0.3,
            relevance_score=0.95,
            data_sufficiency_score=0.8,
            selected=True,
        )
        ca_rejected = CandidateAngle(
            question="Revenue vs weather correlation",
            dimensions=["month", "city"],
            measures=["revenue", "temperature"],
            expected_evidence="scatter plot",
            impact_score=0.3,
            confidence_score=0.2,
            actionability_score=0.1,
            novelty_score=0.4,
            relevance_score=0.3,
            data_sufficiency_score=0.1,
            selected=False,
            rejected_reason="weather data unavailable",
        )
        run = RunResponse(
            status="completed",
            skill_id="test",
            question="Test roundtrip",
            artifacts=[
                Artifact(
                    type=ArtifactType.run_log,
                    title="工作流日志",
                    content="test",
                    data={
                        "candidate_angles": [
                            ca_selected.model_dump(mode="json"),
                            ca_rejected.model_dump(mode="json"),
                        ],
                    },
                ),
            ],
        )
        store.record_run(run)
        retrieved = store.get_run(run.id)
        assert retrieved is not None
        assert len(retrieved.artifacts) == 1
        data = retrieved.artifacts[0].data
        assert data is not None
        angles = data.get("candidate_angles", [])
        assert len(angles) == 2
        assert angles[0]["question"] == "Revenue trend by month"
        assert angles[0]["selected"] is True
        assert angles[1]["question"] == "Revenue vs weather correlation"
        assert angles[1]["selected"] is False
        assert angles[1]["rejected_reason"] == "weather data unavailable"


def test_composite_score():
    angle = CandidateAngle(
        question="test",
        impact_score=0.8, confidence_score=0.7,
        actionability_score=0.6, relevance_score=0.9,
        data_sufficiency_score=0.5,
    )
    expected = 0.8*0.25 + 0.7*0.20 + 0.6*0.20 + 0.9*0.20 + 0.5*0.15
    assert angle.composite_score == pytest.approx(expected)


class TestAngleBoundaries:
    def test_truncate_to_max_candidate_angles(self):
        angles = [
            CandidateAngle(question=f"q{i}", impact_score=0.5, selected=True)
            for i in range(MAX_CANDIDATE_ANGLES + 3)
        ]
        result = enforce_angle_boundaries(angles)
        assert len(result) == MAX_CANDIDATE_ANGLES

    def test_auto_reject_below_data_sufficiency(self):
        angles = [
            CandidateAngle(
                question="low confidence", selected=True,
                data_sufficiency_score=0.05,
                impact_score=0.9, confidence_score=0.9,
                actionability_score=0.9, relevance_score=0.9,
            ),
            CandidateAngle(
                question="good", selected=True,
                data_sufficiency_score=0.8,
                impact_score=0.5, confidence_score=0.5,
                actionability_score=0.5, relevance_score=0.5,
            ),
        ]
        result = enforce_angle_boundaries(angles)
        assert len(result) == 2
        assert not result[0].selected
        assert "below 0.15" in result[0].rejected_reason
        assert result[1].selected

    def test_cap_selected_to_max(self):
        angles = [
            CandidateAngle(
                question=f"q{i}", selected=True,
                impact_score=0.1 * i, confidence_score=0.5,
                actionability_score=0.5, relevance_score=0.5,
                data_sufficiency_score=0.8,
            )
            for i in range(1, MAX_SELECTED_ANGLES + 3)
        ]
        result = enforce_angle_boundaries(angles)
        selected_count = sum(1 for a in result if a.selected)
        assert selected_count == MAX_SELECTED_ANGLES

    def test_auto_reject_below_min_angle_score(self):
        """Angles with composite_score < MIN_ANGLE_SCORE should be auto-rejected."""
        angles = [
            CandidateAngle(
                question="very low composite", selected=True,
                impact_score=0.1, confidence_score=0.1,
                actionability_score=0.1, relevance_score=0.1,
                data_sufficiency_score=0.1,
            ),
            CandidateAngle(
                question="above threshold", selected=True,
                impact_score=0.9, confidence_score=0.9,
                actionability_score=0.9, relevance_score=0.9,
                data_sufficiency_score=0.8,
            ),
        ]
        result = enforce_angle_boundaries(angles)
        assert len(result) == 2
        assert not result[0].selected
        assert "below 0.2" in result[0].rejected_reason
        assert result[1].selected

    def test_rejected_gets_reason(self):
        angles = [
            CandidateAngle(
                question="rejected no reason", selected=False,
                impact_score=0.1,
            )
        ]
        result = enforce_angle_boundaries(angles)
        assert result[0].rejected_reason is not None
        assert "not selected" in result[0].rejected_reason
