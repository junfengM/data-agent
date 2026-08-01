"""Dataset profiling helpers for analysis runs."""
from __future__ import annotations

from app.agent.preflight_context import profile_table_data, profile_chart_data
from app.memory.store import MemoryStore
from app.models.schemas import Artifact, ArtifactType, DatasetProfile, RunResponse
from app.tools.dataframes import profile_dataset
from app.tools.markdown import profiles_to_markdown


def profile_datasets(store: MemoryStore, dataset_ids: list[str]) -> list[DatasetProfile]:
    profiles: list[DatasetProfile] = []
    for dataset_id in dataset_ids:
        dataset = store.get_dataset(dataset_id)
        if dataset is None:
            continue
        profiles.append(profile_dataset(dataset))
    return profiles


def build_profile_artifacts(profiles: list[DatasetProfile], run: RunResponse) -> None:
    if not profiles:
        return
    profile_markdown = profiles_to_markdown(profiles)
    run.artifacts.append(
        Artifact(
            type=ArtifactType.table,
            title="\u6570\u636e\u753b\u50cf",
            content=profile_markdown,
            data=profile_table_data(profiles),
        )
    )
    chart_data = profile_chart_data(profiles)
    if chart_data:
        run.artifacts.append(
            Artifact(
                type=ArtifactType.chart,
                title="\u5b57\u6bb5\u5b8c\u6574\u6027\u6982\u89c8",
                content="\u5b57\u6bb5\u975e\u7a7a\u884c\u6570\u4e0e\u7a7a\u503c\u6570\u5bf9\u6bd4\u3002",
                data=chart_data,
            )
        )
