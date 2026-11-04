"""Smoke tests for the 1000-order benchmark.

python -m planner.random_benchmark_test
Does not touch RobotStudio, GUI, or ABB sockets.
"""
from tempfile import TemporaryDirectory
from pathlib import Path
import csv
import json
import random

from planner.random_benchmark import (
    generate_order, necessary_bound, p95, run_benchmark, SKUS,
)


def main():
    one = random.Random(2026)
    two = random.Random(2026)
    assert [
        generate_order(one, i) for i in range(30)
    ] == [
        generate_order(two, i) for i in range(30)
    ], "same seed should produce identical input orders"

    for i in range(30):
        profile, order = generate_order(random.Random(i), i)
        assert profile
        assert set(order) == set(SKUS)
        assert sum(order.values()) > 0
        assert all(q >= 0 for q in order.values())

    pallet = {"length": 1300., "width": 1300., "height": 800., "weight": 1000.}
    assert necessary_bound({"20L": 40, "10L": 0, "1L": 0, "4L": 0}, pallet) == "weight"
    assert necessary_bound({"20L": 1, "10L": 0, "1L": 0, "4L": 0}, pallet) == ""
    assert p95([1, 2, 3, 4, 5]) == 4.8

    with TemporaryDirectory() as tmp:
        summary = run_benchmark(7, 2026, output=tmp, progress=0)
        assert summary["case_count"] == 7
        assert sum(summary["status_counts"].values()) == 7
        assert (Path(tmp) / "cases.csv").exists()
        assert (Path(tmp) / "summary.txt").exists()
        loaded = json.loads((Path(tmp) / "summary.json").read_text())
        assert loaded["seed"] == 2026
        with (Path(tmp) / "cases.csv").open(newline="") as file:
            rows = list(csv.DictReader(file))
        assert len(rows) == 7
        assert all(row["status"] in ("PASS", "REJECT", "INVALID", "CRASH")
                   for row in rows)
    print("PASS: random benchmark generation, bounds, CSV/JSON report")


if __name__ == "__main__":
    main()
