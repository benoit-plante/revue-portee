"""Search strategy versions, queries, runs, key articles, sensitivity tests, descriptor
checks and AI term suggestions (tranche 1.3)."""

import json
from typing import Any

from sqlalchemy import Connection, select

from revue_portee.domain.search import (
    DescriptorCheck,
    KeyArticle,
    KeyArticleSetVersion,
    QueryVersion,
    SearchRun,
    SearchStrategy,
    StrategyVersion,
    TermSuggestion,
    TermSuggestionReview,
    Translation,
)
from revue_portee.domain.sensitivity import SensitivityCheck, SensitivityResult
from revue_portee.storage.db import (
    descriptor_check,
    key_article_set_version,
    query,
    search_run,
    search_strategy_version,
    sensitivity_check,
    term_suggestion,
    term_suggestion_review,
)

__all__ = [
    "get_query",
    "get_strategy_version",
    "get_term_suggestion",
    "insert_descriptor_checks",
    "insert_key_article_set",
    "insert_queries",
    "insert_run",
    "insert_sensitivity_check",
    "insert_strategy_version",
    "insert_term_review",
    "insert_term_suggestions",
    "latest_descriptor_checks",
    "latest_key_article_set",
    "latest_strategy_version",
    "list_queries",
    "list_runs",
    "list_sensitivity_checks",
    "list_strategy_versions",
    "list_term_reviews",
    "list_term_suggestions",
]


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _row(row: Any) -> dict[str, Any]:  # noqa: ANN401 - SQLAlchemy row mapping
    return {k: v for k, v in dict(row).items() if k != "journal_entry_id"}


# --- Strategy versions and queries --------------------------------------------------


def insert_strategy_version(
    connection: Connection, value: StrategyVersion, *, journal_entry_id: str
) -> None:
    connection.execute(
        search_strategy_version.insert().values(
            id=value.id,
            number=value.number,
            created_at=value.created_at,
            author_id=value.author_id,
            rationale=value.rationale,
            strategy_json=_dumps(value.strategy.model_dump(mode="json")),
            journal_entry_id=journal_entry_id,
        )
    )


def _to_strategy(row: dict[str, Any]) -> StrategyVersion:
    strategy = SearchStrategy.model_validate(json.loads(row.pop("strategy_json")))
    return StrategyVersion.model_validate(row | {"strategy": strategy})


def latest_strategy_version(connection: Connection) -> StrategyVersion | None:
    row = (
        connection.execute(
            select(search_strategy_version)
            .order_by(search_strategy_version.c.number.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_strategy(_row(row))


def get_strategy_version(connection: Connection, version_id: str) -> StrategyVersion | None:
    row = (
        connection.execute(
            select(search_strategy_version).where(search_strategy_version.c.id == version_id)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else _to_strategy(_row(row))


def list_strategy_versions(connection: Connection) -> list[StrategyVersion]:
    rows = connection.execute(
        select(search_strategy_version).order_by(search_strategy_version.c.number)
    ).mappings()
    return [_to_strategy(_row(row)) for row in rows]


def insert_queries(connection: Connection, values: list[QueryVersion]) -> None:
    for value in values:
        translation = value.translation
        connection.execute(
            query.insert().values(
                id=value.id,
                strategy_version_id=value.strategy_version_id,
                database=translation.database.value,
                syntax_text=translation.text,
                blocks_json=_dumps(translation.blocks),
                limits_text=translation.limits,
                warnings_json=_dumps([w.model_dump(mode="json") for w in translation.warnings]),
                generated_by=value.generated_by,
                edited=value.edited,
                created_at=value.created_at,
            )
        )


def _to_query(row: dict[str, Any]) -> QueryVersion:
    translation = Translation.model_validate(
        {
            "database": row["database"],
            "text": row["syntax_text"],
            "blocks": json.loads(row["blocks_json"]),
            "limits": row["limits_text"],
            "warnings": json.loads(row["warnings_json"]),
        }
    )
    return QueryVersion(
        id=row["id"],
        strategy_version_id=row["strategy_version_id"],
        created_at=row["created_at"],
        translation=translation,
        generated_by=row["generated_by"],
        edited=bool(row["edited"]),
    )


def list_queries(
    connection: Connection, *, strategy_version_id: str | None = None
) -> list[QueryVersion]:
    statement = select(query).order_by(query.c.created_at, query.c.database)
    if strategy_version_id is not None:
        statement = statement.where(query.c.strategy_version_id == strategy_version_id)
    return [_to_query(dict(row)) for row in connection.execute(statement).mappings()]


def get_query(connection: Connection, query_id: str) -> QueryVersion | None:
    row = connection.execute(select(query).where(query.c.id == query_id)).mappings().one_or_none()
    return None if row is None else _to_query(dict(row))


# --- Runs and sensitivity tests -----------------------------------------------------


def insert_run(connection: Connection, value: SearchRun, *, journal_entry_id: str) -> None:
    connection.execute(
        search_run.insert().values(
            id=value.id,
            query_id=value.query_id,
            kind=value.kind.value,
            executed_at=value.executed_at,
            result_count=value.result_count,
            blocks_json=_dumps(value.block_counts),
            status="completed",
            raw_dir=value.raw_dir,
            reviewer_id=value.reviewer_id,
            journal_entry_id=journal_entry_id,
        )
    )


def list_runs(connection: Connection, *, query_id: str | None = None) -> list[SearchRun]:
    statement = select(search_run).order_by(search_run.c.executed_at, search_run.c.id)
    if query_id is not None:
        statement = statement.where(search_run.c.query_id == query_id)
    runs = []
    for row in connection.execute(statement).mappings():
        data = _row(row)
        data.pop("status")
        data["block_counts"] = json.loads(data.pop("blocks_json"))
        runs.append(SearchRun.model_validate(data))
    return runs


def insert_sensitivity_check(connection: Connection, value: SensitivityCheck) -> None:
    connection.execute(
        sensitivity_check.insert().values(
            id=value.id,
            search_run_id=value.search_run_id,
            key_article_set_version_id=value.key_article_set_version_id,
            found=value.result.found,
            indexed=value.result.indexed,
            outcomes_json=_dumps(value.result.model_dump(mode="json")["outcomes"]),
        )
    )


def list_sensitivity_checks(connection: Connection) -> list[SensitivityCheck]:
    statement = (
        select(sensitivity_check)
        .join(search_run, search_run.c.id == sensitivity_check.c.search_run_id)
        .order_by(search_run.c.executed_at, sensitivity_check.c.id)
    )
    return [
        SensitivityCheck(
            id=row["id"],
            search_run_id=row["search_run_id"],
            key_article_set_version_id=row["key_article_set_version_id"],
            result=SensitivityResult.model_validate({"outcomes": json.loads(row["outcomes_json"])}),
        )
        for row in connection.execute(statement).mappings()
    ]


# --- Key articles -------------------------------------------------------------------


def insert_key_article_set(
    connection: Connection, value: KeyArticleSetVersion, *, journal_entry_id: str
) -> None:
    connection.execute(
        key_article_set_version.insert().values(
            id=value.id,
            number=value.number,
            created_at=value.created_at,
            author_id=value.author_id,
            articles_json=_dumps([a.model_dump(mode="json") for a in value.articles]),
            journal_entry_id=journal_entry_id,
        )
    )


def latest_key_article_set(connection: Connection) -> KeyArticleSetVersion | None:
    row = (
        connection.execute(
            select(key_article_set_version)
            .order_by(key_article_set_version.c.number.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    data = _row(row)
    articles = tuple(KeyArticle.model_validate(a) for a in json.loads(data.pop("articles_json")))
    return KeyArticleSetVersion.model_validate(data | {"articles": articles})


# --- Descriptor checks --------------------------------------------------------------


def insert_descriptor_checks(
    connection: Connection, values: list[DescriptorCheck], *, journal_entry_id: str
) -> None:
    for value in values:
        connection.execute(
            descriptor_check.insert().values(
                **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
            )
        )


def latest_descriptor_checks(connection: Connection) -> dict[tuple[str, str], DescriptorCheck]:
    """Latest check of each heading, keyed by (vocabulary, heading folded to lower case)."""
    statement = select(descriptor_check).order_by(
        descriptor_check.c.created_at, descriptor_check.c.id
    )
    checks: dict[tuple[str, str], DescriptorCheck] = {}
    for row in connection.execute(statement).mappings():
        check = DescriptorCheck.model_validate(_row(row))
        checks[(check.vocabulary.value, check.heading.casefold())] = check
    return checks


# --- AI term suggestions ------------------------------------------------------------


def insert_term_suggestions(connection: Connection, values: list[TermSuggestion]) -> None:
    for value in values:
        connection.execute(term_suggestion.insert().values(**value.model_dump(mode="python")))


def list_term_suggestions(connection: Connection) -> list[TermSuggestion]:
    statement = select(term_suggestion).order_by(
        term_suggestion.c.created_at, term_suggestion.c.ai_call_id, term_suggestion.c.position
    )
    return [
        TermSuggestion.model_validate(dict(row)) for row in connection.execute(statement).mappings()
    ]


def get_term_suggestion(connection: Connection, suggestion_id: str) -> TermSuggestion | None:
    row = (
        connection.execute(select(term_suggestion).where(term_suggestion.c.id == suggestion_id))
        .mappings()
        .one_or_none()
    )
    return None if row is None else TermSuggestion.model_validate(dict(row))


def insert_term_review(
    connection: Connection, value: TermSuggestionReview, *, journal_entry_id: str
) -> None:
    connection.execute(
        term_suggestion_review.insert().values(
            **value.model_dump(mode="python"), journal_entry_id=journal_entry_id
        )
    )


def list_term_reviews(connection: Connection) -> dict[str, TermSuggestionReview]:
    """Review of each reviewed suggestion, keyed by suggestion id."""
    rows = connection.execute(select(term_suggestion_review)).mappings()
    reviews = (TermSuggestionReview.model_validate(_row(row)) for row in rows)
    return {review.suggestion_id: review for review in reviews}
