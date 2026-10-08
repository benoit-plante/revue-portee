"""Passing to the next reference takes less than 200 ms on a project of 50 000
references (ENF-PER-01, tranche 1.7): measured through the web application, half of the
references already screened by the human and all of them by the AI."""

import re
import statistics
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select

from revue_portee.domain.criteria import CriterionKind, PccElement
from revue_portee.domain.ids import new_ulid
from revue_portee.protocol import criteria
from revue_portee.screening import main
from revue_portee.storage.db import ai_call, ai_config, decision, journal_entry, reference
from revue_portee.storage.project_folder import ProjectFolder
from revue_portee.web.app import create_app
from support import TOOL_VERSION, make_clock, new_project

REFERENCES = 50_000
SCREENED = 25_000
LIMIT_MS = 200
THRESHOLDS = '{"exclude_below": 0.1, "include_above": 0.6}'
ASSESSMENTS = (
    '[{"code": "P1", "kind": "inclusion", "status": "met", "evidence_quote": "",'
    ' "quote_found": null}, {"code": "C1", "kind": "inclusion", "status": "met",'
    ' "evidence_quote": "", "quote_found": null}]'
)
MOMENT = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
ABSTRACT = (
    "This fictional abstract stands for a real one of ordinary length, about two hundred "
    "words, so that the page renders as it would in a review. " * 6
)


def bulk_project(path: Path) -> tuple[ProjectFolder, str]:
    clock = make_clock()
    folder = new_project(path, clock)
    for element, kind, text in (
        (PccElement.POPULATION, CriterionKind.INCLUSION, "Older adults (65 and over)."),
        (PccElement.CONCEPT, CriterionKind.INCLUSION, "Housing or living conditions."),
    ):
        criteria.add_criterion(
            folder, pcc_element=element, kind=kind, text=text, now=clock,
            tool_version=TOOL_VERSION,
        )  # fmt: skip
    criteria.activate_draft(folder, rationale="", now=clock, tool_version=TOOL_VERSION)
    ids = [new_ulid(MOMENT) for _ in range(REFERENCES)]
    with folder.write() as connection:
        connection.execute(
            insert(reference),
            [
                {
                    "id": ref, "title": f"Fictional reference number {n}", "abstract": ABSTRACT,
                    "authors_json": '["Author, A."]', "year": 2020, "container_title": "Journal",
                    "volume": "", "issue": "", "pages": "", "doi": "", "pmid": "",
                    "openalex_id": "", "language": "en", "doc_type": "", "url": "",
                    "created_at": MOMENT,
                }
                for n, ref in enumerate(ids)
            ],
        )  # fmt: skip
    round_id = main.start_main(folder, seed=1, now=clock, tool_version=TOOL_VERSION).id
    with folder.write() as connection:
        members = [
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT reference_id FROM round_member WHERE round_id = ? ORDER BY position",
                (round_id,),
            )
        ]
        entry = connection.execute(select(journal_entry.c.id).limit(1)).scalar_one()
        version = connection.exec_driver_sql(
            "SELECT id FROM criteria_version WHERE status = 'active'"
        ).scalar_one()
        config_id, call_id = new_ulid(MOMENT), new_ulid(MOMENT)
        connection.execute(
            insert(ai_config).values(
                id=config_id, task="screen_reference", provider="fake", model_requested="fake",
                prompt_template_id="screen_reference", prompt_template_version="1",
                params_json="{}", created_at=MOMENT,
            )
        )  # fmt: skip
        connection.execute(
            insert(ai_call).values(
                id=call_id, ai_config_id=config_id, task="screen_reference", item_id="x",
                provider="fake", model_requested="fake", model_returned="fake",
                prompt_template_id="screen_reference", prompt_template_version="1",
                prompt_sha256="0" * 64, params_json="{}", input_tokens=0, output_tokens=0,
                cache_read_tokens=0, cache_write_tokens=0, cost_estimate=0, currency="USD",
                latency_ms=0, status="ok", created_at=MOMENT,
            )
        )  # fmt: skip
        reviewer = folder.reviewer_id
        common = {
            "stage": "title_abstract", "round_id": round_id, "reviewer_id": reviewer,
            "rationale": "", "criteria_cited_json": "[]", "per_criterion_json": "[]",
            "calibration_id": None, "criteria_version_id": version, "language": "en",
            "context": "independent", "supersedes_decision_id": None, "tool_version": "t",
            "created_at": MOMENT, "journal_entry_id": entry, "confidence_calibrated": None,
        }  # fmt: skip
        connection.execute(
            insert(decision),
            [
                common | {
                    "id": new_ulid(MOMENT), "reference_id": ref, "reviewer_kind": "ai",
                    "value": "include", "confidence_raw": (n % 100) / 100,
                    "model_decision": "include", "thresholds_json": THRESHOLDS,
                    "blinded": False, "ai_call_id": call_id, "rationale": "P1 et C1.",
                    "criteria_cited_json": '["P1"]', "per_criterion_json": ASSESSMENTS,
                }
                for n, ref in enumerate(members)
            ],
        )  # fmt: skip
        connection.execute(
            insert(decision),
            [
                common | {
                    "id": new_ulid(MOMENT), "reference_id": ref, "reviewer_kind": "human",
                    "value": "include", "confidence_raw": None, "model_decision": None,
                    "thresholds_json": None, "blinded": True, "ai_call_id": None,
                }
                for ref in members[:SCREENED]
            ],
        )  # fmt: skip
    return folder, round_id


@pytest.fixture(scope="module")
def big(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[ProjectFolder, str]]:
    folder, round_id = bulk_project(tmp_path_factory.mktemp("big"))
    yield folder, round_id
    folder.close()


def timed(action: object) -> float:
    start = time.perf_counter()
    action()  # type: ignore[operator]
    return (time.perf_counter() - start) * 1000


@pytest.mark.parametrize("priority", [False, True])
def test_next_reference_under_200_ms(big: tuple[ProjectFolder, str], priority: bool) -> None:
    folder, _round_id = big
    app = create_app(folder, now=make_clock(), tool_version=TOOL_VERSION)
    client = TestClient(app, base_url="http://127.0.0.1:8000", follow_redirects=False)
    url = "/tri/trier?priorite=1" if priority else "/tri/trier"
    page = client.get(url)  # warm-up
    assert page.status_code == 200
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert token
    durations = []
    for _ in range(15):
        ref = re.search(r'name="reference" value="([^"]+)"', client.get(url).text)
        assert ref

        def next_one(found: str = ref.group(1)) -> None:
            response = client.post(
                "/tri/decision" + ("?priorite=1" if priority else ""),
                data={"csrf_token": token.group(1), "reference": found, "valeur": "include"},
            )
            assert response.status_code == 303, re.findall(r'role="alert">([^<]+)', response.text)
            assert client.get(response.headers["location"]).status_code == 200

        durations.append(timed(next_one))
    median = statistics.median(durations)
    print(f"next reference ({'priority' if priority else 'drawn order'}): median {median:.0f} ms")
    assert median < LIMIT_MS
