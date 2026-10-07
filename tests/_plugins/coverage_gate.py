"""Per-package coverage threshold checked by every full ``pytest`` run (ENF-QUA-04).

pytest-cov only offers a global ``--cov-fail-under``. This plugin wraps
``pytest_runtestloop`` outside pytest-cov's own wrapper, so that it runs once
coverage data is complete, and fails the session when one of the packages listed
in the ``coverage_gate_packages`` ini option is below ``coverage_gate_fail_under``.

The threshold only makes sense on the whole suite: it is skipped (with a notice)
for partial runs (explicit paths, ``-k``, another ``-m``, ``--lf``, ``--deselect``),
``--no-cov``, ``--collect-only`` and runs that already have failing tests.
"""

import io
from collections.abc import Generator, Mapping, Sequence

import pytest
from coverage import Coverage
from coverage.exceptions import NoDataError

DEFAULT_MARKEXPR = "not integration"

# (message, markup) shown in the terminal summary, after pytest-cov's report.
_message_key = pytest.StashKey[tuple[str, dict[str, bool]]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        "coverage_gate_packages",
        "Packages of revue_portee that must each reach coverage_gate_fail_under.",
        type="linelist",
        default=[],
    )
    parser.addini(
        "coverage_gate_fail_under",
        "Minimum coverage percentage for each package of coverage_gate_packages.",
        default="90",
    )


def failing_packages(coverage: Mapping[str, float], threshold: float) -> list[str]:
    """Packages whose coverage is below ``threshold``, in input order."""
    return [package for package, percent in coverage.items() if percent < threshold]


def skip_reason(config: pytest.Config, testsfailed: int) -> str | None:
    """Why the threshold is not checked on this run, or ``None`` if it is."""
    option = config.option
    if option.collectonly:
        return "collecte seulement"
    if testsfailed:
        return "des tests échouent"
    if config.args_source is not pytest.Config.ArgsSource.TESTPATHS:
        return "chemins de tests explicites"
    if option.keyword:
        return "sélection par -k"
    if option.markexpr != DEFAULT_MARKEXPR:
        return "sélection par -m"
    if config.getoption("lf", False) or config.getoption("deselect", None):
        return "sélection partielle (--lf ou --deselect)"
    return None


def measure(cov: Coverage, packages: Sequence[str]) -> dict[str, float]:
    """Coverage percentage of each package, from a ``coverage.Coverage`` object.

    A package with no measured file (e.g. a misspelled name) counts as 0 %.
    """
    coverage: dict[str, float] = {}
    for package in packages:
        try:
            coverage[package] = cov.report(
                include=[f"*/revue_portee/{package}/*"], file=io.StringIO()
            )
        except NoDataError:
            coverage[package] = 0.0
    return coverage


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtestloop(session: pytest.Session) -> Generator[None, object, object]:
    result = yield
    config = session.config
    packages: list[str] = config.getini("coverage_gate_packages")
    cov_plugin = config.pluginmanager.getplugin("_cov")
    controller = getattr(cov_plugin, "cov_controller", None)
    if not packages or controller is None or getattr(cov_plugin, "cov_total", None) is None:
        return result  # coverage disabled (--no-cov) or not reported

    threshold = float(config.getini("coverage_gate_fail_under"))
    reason = skip_reason(config, session.testsfailed)
    if reason is not None:
        message = f"Seuil de couverture par paquet non vérifié\u00a0: {reason}."
        config.stash[_message_key] = (message, {"yellow": True})
        return result

    coverage = measure(controller.cov, packages)
    failing = failing_packages(coverage, threshold)
    summary = ", ".join(f"{package} {percent:.1f}\u00a0%" for package, percent in coverage.items())
    if failing:
        message = (
            f"ÉCHEC\u00a0: couverture sous {threshold:g}\u00a0% pour "
            f"{', '.join(failing)} ({summary})."
        )
        config.stash[_message_key] = (message, {"red": True, "bold": True})
        session.testsfailed += 1  # exit code 1, as pytest-cov does for --cov-fail-under
    else:
        message = f"Seuil de couverture de {threshold:g}\u00a0% atteint\u00a0: {summary}."
        config.stash[_message_key] = (message, {"green": True})
    return result


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    if _message_key in config.stash:
        message, markup = config.stash[_message_key]
        terminalreporter.write_line(message, **markup)
