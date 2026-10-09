"""The « Études et rapports » page (tranche 2.3): pairs proposed, examined by the AI in
the background, decided by the person; primary report; reports joined by hand."""

import html
import re
from pathlib import Path

from fastapi.testclient import TestClient

from demo import FILLER, build
from revue_portee.domain.screening import DecisionValue
from revue_portee.fulltext import retrieval
from revue_portee.jobs.runner import BackgroundJobs
from revue_portee.screening import fulltext, studies
from revue_portee.web.app import STUDY_JOB, create_app
from support import TOOL_VERSION, fake_factory, make_clock, make_pdf

BASE = "http://127.0.0.1:8000"
# A follow-up of the loneliness study: both texts give the same trial number.
TRIAL = "Trial registration: NCT01234567."
FOLLOW_UP = "One-year follow-up\nWe interviewed 24 older adults again.\n" + TRIAL + FILLER
MAIN = "Loneliness among older adults after residential relocation\n" + TRIAL + FILLER


def text(response: object) -> str:
    return html.unescape(response.text).replace(" ", " ")  # type: ignore[attr-defined]


def token(client: TestClient) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text(client.get("/textes/etudes")))
    assert match is not None
    return match.group(1)


def answer(_item: object) -> dict[str, object]:
    return {
        "verdict": "same",
        "evidence": [{"aspect": "sample", "quote_a": "older adults", "page_a": 1,
                      "quote_b": "older adults", "page_b": 1}],
        "rationale": "Même échantillon, suivi à un an.",
    }  # fmt: skip


def test_studies_page(tmp_path: Path) -> None:
    demo = build(tmp_path)
    try:
        ids = demo.ids()
        # the caregivers record becomes the follow-up of the loneliness study
        retrieval.add_upload(
            demo.folder, ids["caregivers"], make_pdf([FOLLOW_UP]), filename="f.pdf",
            now=demo.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        retrieval.add_upload(
            demo.folder, ids["loneliness"], make_pdf([MAIN]), filename="m.pdf",
            now=demo.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        fulltext.add_new_texts(demo.folder, now=demo.clock, tool_version=TOOL_VERSION)
        fulltext.record_decision(
            demo.folder, demo.fulltext_round_id, ids["caregivers"], DecisionValue.INCLUDE,
            now=demo.clock, tool_version=TOOL_VERSION,
        )  # fmt: skip
        jobs = BackgroundJobs()
        app = create_app(
            demo.folder, now=make_clock(), tool_version=TOOL_VERSION, jobs=jobs,
            provider_factory=fake_factory({"GroupReportsInput": answer}),
        )  # fmt: skip
        client = TestClient(app, base_url=BASE, follow_redirects=False)
        page = text(client.get("/textes/etudes"))
        assert "Études incluses : 2, à partir de 2 rapports" in page
        state = studies.study_state(demo.folder)
        candidates = [(c.reference_a_id, c.reference_b_id, c.rule) for c in state.candidates]
        a, b, rule = candidates[0]
        assert rule == "registration"
        estimate = client.post("/textes/etudes/ia/estimation", data={"csrf_token": token(client)})
        assert "Plafond du lot en dollars américains" in text(estimate)
        started = client.post(
            "/textes/etudes/ia", data={"csrf_token": token(client), "plafond": "1"}
        )
        assert started.status_code == 303
        jobs.wait(STUDY_JOB, timeout=30)
        assert jobs.error(STUDY_JOB) is None
        page = text(client.get("/textes/etudes"))
        assert "IA : même étude. Même échantillon, suivi à un an." in page
        assert "« older adults » (page 1) — trouvée à cette page" in page
        decided = client.post(
            "/textes/etudes/decision",
            data={"csrf_token": token(client), "a": a, "b": b, "issue": "same"},
        )
        assert decided.status_code == 303
        page = text(client.get("/textes/etudes?ok=decision"))
        assert "Études incluses : 1, à partir de 2 rapports" in page
        assert "À décider : 0 sur 1." in page
        primary = client.post(
            "/textes/etudes/principal",
            data={"csrf_token": token(client), "reference": ids["caregivers"]},
        )
        assert primary.status_code == 303
        assert "Rapport principal choisi." in text(client.get("/textes/etudes?ok=principal"))
        refused = client.post(
            "/textes/etudes/decision",
            data={"csrf_token": token(client), "a": ids["housing"], "b": a, "issue": "same"},
        )
        assert refused.status_code == 422
        empty = client.post(
            "/textes/etudes/decision", data={"csrf_token": token(client), "a": a, "b": b}
        )
        assert empty.status_code == 422
        bad = client.post("/textes/etudes/principal", data={"csrf_token": token(client)})
        assert bad.status_code == 422
        ceiling = client.post(
            "/textes/etudes/ia", data={"csrf_token": token(client), "plafond": "x"}
        )
        assert ceiling.status_code == 422
        diagram = text(client.get("/rapports/diagramme?langue=fr"))
    finally:
        demo.folder.close()
    assert "Sources de données probantes incluses dans la revue (n = 1)" in diagram
    assert "Rapports des sources de données probantes incluses (n = 2)" in diagram
