"""Fixture of the screening tests: a project with active criteria and ten references."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from revue_portee.storage.project_folder import ProjectFolder

from .common import Clock, make_project


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[ProjectFolder, Clock]]:
    folder, clock = make_project(tmp_path)
    yield folder, clock
    folder.close()
