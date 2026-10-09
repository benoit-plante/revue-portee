"""The PRISMA-ScR checklist of the demonstration (tests/fixtures/demo/README.md): the
proposals carry the numbers counted by hand there."""

from pathlib import Path
from typing import Any

import pytest

from demo import build_extracted
from revue_portee.declaration import checklist
from revue_portee.reporting.prisma_scr import fill_checklist
from revue_portee.resources import reporting_checklists
from support import TOOL_VERSION


def test_demonstration_checklist(tmp_path: Path) -> None:
    demo = build_extracted(tmp_path)
    kwargs: dict[str, Any] = {"now": demo.clock, "tool_version": TOOL_VERSION}
    try:
        facts = checklist.checklist_facts(demo.folder, **kwargs)
        paths = checklist.export_checklist(demo.folder, language="fr", **kwargs)
        with pytest.raises(checklist.UnknownChecklistError):
            checklist.export_checklist(demo.folder, checklist="prisma-2099", language="fr",
                                       **kwargs)  # fmt: skip
    finally:
        demo.folder.close()
    filled = {f.item.id: " ".join(f.proposals)
              for f in fill_checklist(reporting_checklists()["prisma-scr-2018"], facts,
                                      language="fr")}  # fmt: skip
    # 9 records (APA PsycInfo 4, CINAHL 3, PubMed 2), 4 duplicates, 5 screened, 2 excluded;
    # full texts: 2 assessed, 1 excluded for P1, 1 included
    assert filled["7"].startswith(
        "Bases de données, selon les références importées : APA PsycInfo (EBSCOhost) (4)"
    )
    assert "9 références repérées, 4 doublons retirés, 5 triées, 2 exclues." in filled["14"]
    assert "évalués : 2 ; exclus avec motifs : P1 1 ; inclus : 1." in filled["14"]
    assert "D1 Devis ; D2 Milieu ; D3 Pays" in filled["11"]
    assert "extraites 3" in filled["10"]
    assert "1 rapports non obtenus" in filled["20"]
    # no framing, protocol text, registration nor search run in the demonstration
    assert [k for k, v in filled.items() if not v] == ["3", "4", "5", "8", "18", "19", "21", "22"]
    assert [p.name for p in paths] == ["prisma-scr-2018-fr.md", "prisma-scr-2018-fr.docx"]
    assert "Éléments avec une proposition : 14 sur 22." in paths[0].read_text(encoding="utf-8")
