from _plugins.coverage_gate import failing_packages


def test_failing_packages_keeps_order_and_threshold_is_inclusive() -> None:
    coverage = {"domain": 95.0, "dedup": 89.9, "reporting": 90.0}
    assert failing_packages(coverage, 90.0) == ["dedup"]


def test_no_failing_package() -> None:
    assert failing_packages({"domain": 100.0}, 90.0) == []
    assert failing_packages({}, 90.0) == []
