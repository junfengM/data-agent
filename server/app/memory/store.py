import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.schemas import (
    AnalysisProject,
    AnalysisProjectCreate,
    AnalysisProjectUpdate,
    DatasetRecord,
    ProjectContext,
    ProjectContextCreate,
    ProjectContextUpdate,
    RunResponse,
)


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def create_project(self, project: AnalysisProjectCreate) -> AnalysisProject:
        project_id = uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                insert into analysis_projects (id, name, description)
                values (?, ?, ?)
                """,
                (project_id, project.name.strip(), project.description.strip()),
            )
        created = self.get_project(project_id)
        if created is None:
            raise RuntimeError("Failed to create analysis project")
        return created

    def get_project(self, project_id: str) -> AnalysisProject | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                select id, name, description, status, created_at, updated_at
                from analysis_projects
                where id = ?
                """,
                (project_id,),
            ).fetchone()
        return self._project_from_row(row) if row else None

    def list_projects(self, include_archived: bool = False) -> list[AnalysisProject]:
        where = "" if include_archived else "where status != 'archived'"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select id, name, description, status, created_at, updated_at
                from analysis_projects
                {where}
                order by updated_at desc, created_at desc
                """
            ).fetchall()
        return [self._project_from_row(row) for row in rows]

    def update_project(
        self, project_id: str, project: AnalysisProjectUpdate
    ) -> AnalysisProject | None:
        current = self.get_project(project_id)
        if current is None:
            return None

        next_name = project.name.strip() if project.name is not None else current.name
        next_description = (
            project.description.strip() if project.description is not None else current.description
        )
        next_status = project.status if project.status is not None else current.status
        with self._connect() as conn:
            conn.execute(
                """
                update analysis_projects
                set name = ?, description = ?, status = ?, updated_at = current_timestamp
                where id = ?
                """,
                (next_name, next_description, next_status, project_id),
            )
        return self.get_project(project_id)

    def create_project_context(
        self, project_id: str, context: ProjectContextCreate
    ) -> ProjectContext | None:
        if self.get_project(project_id) is None:
            return None

        context_id = uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                insert into project_contexts (id, project_id, kind, title, body)
                values (?, ?, ?, ?, ?)
                """,
                (
                    context_id,
                    project_id,
                    context.kind.strip(),
                    context.title.strip(),
                    context.body.strip(),
                ),
            )
            conn.execute(
                """
                update analysis_projects
                set updated_at = current_timestamp
                where id = ?
                """,
                (project_id,),
            )
        return self.get_project_context(project_id, context_id)

    def get_project_context(self, project_id: str, context_id: str) -> ProjectContext | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                select id, project_id, kind, title, body, created_at, updated_at
                from project_contexts
                where project_id = ? and id = ?
                """,
                (project_id, context_id),
            ).fetchone()
        return self._context_from_row(row) if row else None

    def list_project_contexts(self, project_id: str) -> list[ProjectContext]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select id, project_id, kind, title, body, created_at, updated_at
                from project_contexts
                where project_id = ?
                order by kind asc, updated_at desc, created_at desc
                """,
                (project_id,),
            ).fetchall()
        return [self._context_from_row(row) for row in rows]

    def update_project_context(
        self, project_id: str, context_id: str, context: ProjectContextUpdate
    ) -> ProjectContext | None:
        current = self.get_project_context(project_id, context_id)
        if current is None:
            return None

        next_kind = context.kind.strip() if context.kind is not None else current.kind
        next_title = context.title.strip() if context.title is not None else current.title
        next_body = context.body.strip() if context.body is not None else current.body
        with self._connect() as conn:
            conn.execute(
                """
                update project_contexts
                set kind = ?, title = ?, body = ?, updated_at = current_timestamp
                where project_id = ? and id = ?
                """,
                (next_kind, next_title, next_body, project_id, context_id),
            )
            conn.execute(
                """
                update analysis_projects
                set updated_at = current_timestamp
                where id = ?
                """,
                (project_id,),
            )
        return self.get_project_context(project_id, context_id)

    def delete_project_context(self, project_id: str, context_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                delete from project_contexts
                where project_id = ? and id = ?
                """,
                (project_id, context_id),
            )
            deleted = cursor.rowcount > 0
            if deleted:
                conn.execute(
                    """
                    update analysis_projects
                    set updated_at = current_timestamp
                    where id = ?
                    """,
                    (project_id,),
                )
        return deleted

    def record_dataset(self, path: Path, filename: str, content_type: str | None, project_id: str | None = None) -> str:
        dataset_id = uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                insert into datasets (id, filename, path, content_type, project_id)
                values (?, ?, ?, ?, ?)
                """,
                (dataset_id, filename, str(path), content_type, project_id),
            )
        return dataset_id

    def get_dataset(self, dataset_id: str, project_id: str | None = None) -> DatasetRecord | None:
        with self._connect() as conn:
            if project_id is not None:
                row = conn.execute(
                    """
                    select id, filename, path, content_type, created_at, project_id
                    from datasets
                    where id = ? and (project_id = ? or project_id is null)
                    """,
                    (dataset_id, project_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    select id, filename, path, content_type, created_at, project_id
                    from datasets
                    where id = ?
                    """,
                    (dataset_id,),
                ).fetchone()
        return self._dataset_from_row(row) if row else None

    def list_datasets(self, project_id: str | None = None) -> list[DatasetRecord]:
        with self._connect() as conn:
            if project_id is not None:
                rows = conn.execute(
                    """
                    select id, filename, path, content_type, created_at, project_id
                    from datasets
                    where project_id = ? or project_id is null
                    order by created_at desc
                    """,
                    (project_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    select id, filename, path, content_type, created_at, project_id
                    from datasets
                    order by created_at desc
                    """
                ).fetchall()
        return [self._dataset_from_row(row) for row in rows]

    def record_run(self, run: RunResponse) -> None:
        payload = run.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                insert into runs (id, project_id, status, skill_id, question, payload)
                values (?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  project_id = excluded.project_id,
                  status = excluded.status,
                  skill_id = excluded.skill_id,
                  question = excluded.question,
                  payload = excluded.payload
                """,
                (
                    run.id,
                    run.project_id,
                    run.status,
                    run.skill_id,
                    run.question,
                    json.dumps(payload),
                ),
            )

    def record_run_event(
        self,
        run_id: str,
        event_type: str,
        summary: str,
        data: dict[str, Any] | None = None,
        elapsed_ms: int | None = None,
    ) -> int:
        with self._connect() as conn:
            conn.execute("begin immediate")
            row = conn.execute(
                "select coalesce(max(sequence), 0) + 1 from run_events where run_id = ?",
                (run_id,),
            ).fetchone()
            sequence = int(row[0]) if row else 1
            conn.execute(
                """
                insert into run_events (
                  run_id, sequence, event_type, summary, data, elapsed_ms
                )
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sequence,
                    event_type,
                    summary,
                    json.dumps(data or {}, ensure_ascii=False),
                    elapsed_ms,
                ),
            )
        return sequence

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select sequence, event_type, summary, data, elapsed_ms, created_at
                from run_events
                where run_id = ?
                order by sequence asc
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "sequence": row[0],
                "type": row[1],
                "summary": row[2],
                "data": json.loads(row[3]) if row[3] else {},
                "elapsed_ms": row[4],
                "created_at": row[5],
            }
            for row in rows
        ]

    def get_run(self, run_id: str, project_id: str | None = None) -> RunResponse | None:
        with self._connect() as conn:
            if project_id is not None:
                row = conn.execute(
                    "select payload from runs where id = ? and project_id = ?",
                    (run_id, project_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "select payload from runs where id = ?",
                    (run_id,),
                ).fetchone()
        if row is None:
            return None
        return RunResponse.model_validate(json.loads(row[0]))

    def list_runs(self, project_id: str | None = None) -> list[RunResponse]:
        with self._connect() as conn:
            if project_id is not None:
                rows = conn.execute(
                    "select payload from runs where project_id = ? order by created_at desc",
                    (project_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "select payload from runs order by created_at desc"
                ).fetchall()
        return [RunResponse.model_validate(json.loads(row[0])) for row in rows]

    def list_runs_paginated(
        self,
        project_id: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RunResponse]:
        """List runs with explicit pagination bounds."""
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        with self._connect() as conn:
            if project_id is not None:
                rows = conn.execute(
                    "select payload from runs where project_id = ? "
                    "order by created_at desc limit ? offset ?",
                    (project_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "select payload from runs order by created_at desc limit ? offset ?",
                    (limit, offset),
                ).fetchall()
        return [RunResponse.model_validate(json.loads(row[0])) for row in rows]

    def count_runs(self, project_id: str | None = None) -> int:
        with self._connect() as conn:
            if project_id is not None:
                row = conn.execute(
                    "select count(*) from runs where project_id = ?",
                    (project_id,),
                ).fetchone()
            else:
                row = conn.execute("select count(*) from runs").fetchone()
        return int(row[0]) if row else 0

    def delete_run(self, run_id: str) -> bool:
        """Delete a run and its persisted events. Returns True if the run existed."""
        with self._connect() as conn:
            conn.execute("delete from run_events where run_id = ?", (run_id,))
            cursor = conn.execute("delete from runs where id = ?", (run_id,))
        return cursor.rowcount > 0

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        # NOTE: foreign_keys stays OFF on purpose — run/project lifecycle does not
        # cascade yet, and enabling it would reject runs referencing archived
        # projects. Enable together with a formal migration/cascade design.
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error:
            pass
        return conn

    @staticmethod
    def _dataset_from_row(row: tuple) -> DatasetRecord:
        return DatasetRecord(
            id=row[0],
            filename=row[1],
            path=Path(row[2]),
            content_type=row[3],
            created_at=row[4],
            project_id=row[5] if len(row) > 5 else None,
        )

    @staticmethod
    def _project_from_row(row: tuple[str, str, str, str, str | None, str | None]) -> AnalysisProject:
        return AnalysisProject(
            id=row[0],
            name=row[1],
            description=row[2],
            status=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    @staticmethod
    def _context_from_row(
        row: tuple[str, str, str, str, str, str | None, str | None]
    ) -> ProjectContext:
        return ProjectContext(
            id=row[0],
            project_id=row[1],
            kind=row[2],
            title=row[3],
            body=row[4],
            created_at=row[5],
            updated_at=row[6],
        )

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists analysis_projects (
                  id text primary key,
                  name text not null,
                  description text not null default '',
                  status text not null default 'active',
                  created_at text default current_timestamp,
                  updated_at text default current_timestamp
                )
                """
            )
            conn.execute(
                """
                create table if not exists project_contexts (
                  id text primary key,
                  project_id text not null,
                  kind text not null,
                  title text not null,
                  body text not null,
                  created_at text default current_timestamp,
                  updated_at text default current_timestamp,
                  foreign key(project_id) references analysis_projects(id)
                )
                """
            )
            conn.execute(
                """
                create table if not exists datasets (
                  id text primary key,
                  filename text not null,
                  path text not null,
                  content_type text,
                  created_at text default current_timestamp
                )
                """
            )
            conn.execute(
                """
                create table if not exists runs (
                  id text primary key,
                  project_id text,
                  status text not null,
                  skill_id text not null,
                  question text not null,
                  payload text not null,
                  created_at text default current_timestamp,
                  foreign key(project_id) references analysis_projects(id)
                )
                """
            )
            conn.execute(
                """
                create table if not exists run_events (
                  id integer primary key autoincrement,
                  run_id text not null,
                  sequence integer not null,
                  event_type text not null,
                  summary text not null default '',
                  data text not null default '{}',
                  elapsed_ms integer,
                  created_at text default current_timestamp,
                  unique(run_id, sequence),
                  foreign key(run_id) references runs(id)
                )
                """
            )
            conn.execute(
                """
                create index if not exists idx_run_events_run_sequence
                on run_events(run_id, sequence)
                """
            )
            columns = {
                row[1]
                for row in conn.execute("pragma table_info(runs)").fetchall()
            }
            if "project_id" not in columns:
                conn.execute("alter table runs add column project_id text")

            # datasets: ensure project_id column exists for project-scoped isolation
            ds_columns = {
                row[1]
                for row in conn.execute("pragma table_info(datasets)").fetchall()
            }
            if "project_id" not in ds_columns:
                conn.execute("alter table datasets add column project_id text")

            # source_routing: ensure project_id column exists (migrate from old single-key schema)
            sr_columns = {
                row[1]
                for row in conn.execute("pragma table_info(source_routing)").fetchall()
            }
            if sr_columns:
                if "project_id" not in sr_columns:
                    # old schema: category-only primary key → recreate with project_id
                    existing = conn.execute(
                        "select category, preference from source_routing"
                    ).fetchall()
                    conn.execute("drop table source_routing")
                    conn.execute(
                        """
                        create table source_routing (
                          category text not null,
                          project_id text not null default '',
                          preference text not null default 'neutral',
                          created_at text default current_timestamp,
                          updated_at text default current_timestamp,
                          primary key (category, project_id)
                        )
                        """
                    )
                    for category, preference in existing:
                        conn.execute(
                            "insert into source_routing (category, project_id, preference) values (?, ?, ?)",
                            (category, "", preference),
                        )
            else:
                conn.execute(
                    """
                    create table if not exists source_routing (
                      category text not null,
                      project_id text not null default '',
                      preference text not null default 'neutral',
                      created_at text default current_timestamp,
                      updated_at text default current_timestamp,
                      primary key (category, project_id)
                    )
                    """
                )
            conn.execute(
                """
                create table if not exists semantic_layers (
                  id text primary key,
                  project_id text,
                  name text not null,
                  path text not null,
                  is_active integer not null default 0,
                  created_at text default current_timestamp,
                  updated_at text default current_timestamp,
                  foreign key(project_id) references analysis_projects(id)
                )
                """
            )
            # Migration: add is_active column for existing DBs (silently ignore if exists)
            try:
                conn.execute(
                    "alter table semantic_layers add column is_active integer default 0"
                )
            except Exception:
                pass
            conn.execute(
                """
                create table if not exists onboarding_progress (
                  id text primary key default 'default',
                  project_id text,
                  step text not null default 'welcome',
                  completed_steps text not null default '[]',
                  created_at text default current_timestamp,
                  updated_at text default current_timestamp,
                  foreign key(project_id) references analysis_projects(id)
                )
                """
            )

    def get_source_routing(self, project_id: str | None = None) -> dict[str, str]:
        # Never return all routing when no project_id is specified.
        # Source routing is project-scoped; no-project runs get empty routing.
        if not project_id:
            return {}
        with self._connect() as conn:
            rows = conn.execute(
                "select category, preference from source_routing where project_id = ?",
                (project_id,),
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def update_source_routing(self, project_id: str, routing: dict[str, str]) -> None:
        with self._connect() as conn:
            for category, preference in routing.items():
                conn.execute(
                    """
                    insert into source_routing (category, project_id, preference, updated_at)
                    values (?, ?, ?, current_timestamp)
                    on conflict(category, project_id) do update set
                      preference = excluded.preference,
                      updated_at = excluded.updated_at
                    """,
                    (category, project_id, preference),
                )

    def list_semantic_layers(self, project_id: str | None = None) -> list[dict[str, str]]:
        # Never return all layers when no project_id is specified.
        # This prevents cross-project semantic-layer leakage.
        if not project_id:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "select id, project_id, name, path, is_active, created_at from semantic_layers where project_id = ? order by created_at desc, rowid desc",
                (project_id,),
            ).fetchall()
        return [
            {
                "id": row[0],
                "project_id": row[1],
                "name": row[2],
                "path": row[3],
                "is_active": bool(row[4]),
                "created_at": row[5],
            }
            for row in rows
        ]

    def create_semantic_layer(self, layer: dict[str, str]) -> dict[str, str]:
        layer_id = uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                insert into semantic_layers (id, project_id, name, path)
                values (?, ?, ?, ?)
                """,
                (layer_id, layer.get("project_id"), layer["name"], layer["path"]),
            )
        return {"id": layer_id, **layer}

    def promote_active_layer(self, project_id: str, layer_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "select id from semantic_layers where id = ? and project_id = ?",
                (layer_id, project_id),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "update semantic_layers set is_active = 0 where project_id = ?",
                (project_id,),
            )
            conn.execute(
                "update semantic_layers set is_active = 1 where id = ?",
                (layer_id,),
            )
        return True

    def get_onboarding_progress(self, project_id: str | None = None) -> dict[str, Any]:
        # Onboarding is project-scoped. No-project runs get default empty progress.
        if not project_id:
            return {"step": "welcome", "completed_steps": []}
        with self._connect() as conn:
            row = conn.execute(
                "select step, completed_steps from onboarding_progress where project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            return {"step": "welcome", "completed_steps": []}
        return {"step": row[0], "completed_steps": json.loads(row[1])}

    def update_onboarding_progress(self, project_id: str, progress: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into onboarding_progress (id, project_id, step, completed_steps, updated_at)
                values (?, ?, ?, ?, current_timestamp)
                on conflict(id) do update set
                  step = excluded.step,
                  completed_steps = excluded.completed_steps,
                  updated_at = excluded.updated_at
                """,
                (f"default_{project_id}", project_id, progress["step"], json.dumps(progress.get("completed_steps", []))),
            )
