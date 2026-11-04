"""Seeded mixed-order stress benchmark for the current NewPalletPlanner.

python -m planner.random_benchmark --cases 1000 --seed 2026

Writes benchmark_results/cases.csv, summary.json, summary.txt.
Rejects not violating a necessary bound are UNRESOLVED, not impossible.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from statistics import mean, median
import time
import traceback

from config.products import PRODUCTS
from planner.new_planner import NewPalletPlanner
from planner.rules import can_stack
from planner.validation_test import (
    PALLETS, GAP_X, GAP_Y, EDGE_MARGIN_X, EDGE_MARGIN_Y, validate_success,
)

SKUS = ("20L", "10L", "1L", "4L")
PRIORITY = {sku: index for index, sku in enumerate(SKUS)}
PROFILES = ("sparse", "bucket_heavy", "carton_heavy", "balanced",
            "single_sku", "dense", "boundary")
EPS = 1e-5


def generate_order(rng, case_index):
    """Repeatable SKU mixes, including easy, hard and capacity-edge orders."""
    profile = PROFILES[case_index % len(PROFILES)]
    quantities = dict.fromkeys(SKUS, 0)
    if profile == "sparse":
        quantities.update({sku: rng.randint(0, 5) for sku in SKUS})
    elif profile == "bucket_heavy":
        quantities.update({"20L": rng.randint(2, 19), "10L": rng.randint(3, 25),
                           "1L": rng.randint(0, 5), "4L": rng.randint(0, 5)})
    elif profile == "carton_heavy":
        quantities.update({"20L": rng.randint(0, 3), "10L": rng.randint(0, 5),
                           "1L": rng.randint(5, 38), "4L": rng.randint(5, 23)})
    elif profile == "balanced":
        quantities.update({sku: rng.randint(1, 13) for sku in SKUS})
    elif profile == "single_sku":
        quantities[rng.choice(SKUS)] = rng.randint(1, 45)
    elif profile == "dense":
        quantities.update({sku: rng.randint(10, 27) for sku in SKUS})
    else:
        focus = rng.choice(SKUS)
        quantities[focus] = max(1, rng.choice((8, 9, 10, 15, 16, 17, 18, 24, 32))
                                + rng.choice((-1, 0, 1)))
        for sku in SKUS:
            if sku != focus:
                quantities[sku] = rng.randint(0, 5)
    if not any(quantities.values()):
        quantities[rng.choice(SKUS)] = 1
    return profile, quantities


def necessary_bound(quantities, pallet):
    """Returns only a provable necessary-condition violation, never a fit claim."""
    mass = sum(PRODUCTS[s].weight * q for s, q in quantities.items())
    if mass > pallet["weight"] + EPS:
        return "weight"
    volume = sum(PRODUCTS[s].length * PRODUCTS[s].width * PRODUCTS[s].height * q
                 for s, q in quantities.items())
    if volume > pallet["length"] * pallet["width"] * pallet["height"] + EPS:
        return "volume"
    for sku, q in quantities.items():
        if q and PRODUCTS[sku].height > pallet["height"] + EPS:
            return "height_" + sku
        if q and min(PRODUCTS[sku].length, PRODUCTS[sku].width) > max(
                pallet["length"], pallet["width"]) + EPS:
            return "footprint_" + sku
    return ""


def check_layout(result, quantities, pallet):
    """Current geometry checks PLUS independent stack, gap and order checks."""
    errors = validate_success(result, quantities, pallet)
    if [PRIORITY.get(s.sku, 999) for s in result.slots] != sorted(
            PRIORITY.get(s.sku, 999) for s in result.slots):
        errors.append("SKU priority order violated")
    stacks = defaultdict(list)
    for slot in result.slots:
        stacks[slot.stack_id].append(slot)
        if slot.x - slot.length / 2 < EDGE_MARGIN_X - EPS:
            errors.append(f"left margin: slot {slot.id}")
        if slot.x + slot.length / 2 > pallet["length"] - EDGE_MARGIN_X + EPS:
            errors.append(f"right margin: slot {slot.id}")
        if slot.y - slot.width / 2 < EDGE_MARGIN_Y - EPS:
            errors.append(f"bottom margin: slot {slot.id}")
        if slot.y + slot.width / 2 > pallet["width"] - EDGE_MARGIN_Y + EPS:
            errors.append(f"top margin: slot {slot.id}")

    rectangles = []
    for sid, members in stacks.items():
        members.sort(key=lambda s: s.level)
        if [m.level for m in members] != list(range(1, len(members) + 1)):
            errors.append(f"stack {sid}: nonconsecutive levels")
        if len(members) > PRODUCTS[members[0].sku].max_layers:
            errors.append(f"stack {sid}: exceeds SKU max layers")
        z = 0.0
        for i, item in enumerate(members):
            if i and not can_stack(members[i - 1].sku, item.sku):
                errors.append(f"stack {sid}: incompatible support")
            if abs(item.x - members[0].x) > EPS or abs(item.y - members[0].y) > EPS:
                errors.append(f"stack {sid}: centres differ")
            if abs(item.z - (z + item.height / 2)) > EPS:
                errors.append(f"stack {sid}: centre Z is incorrect")
            z += item.height
        length = max(m.length for m in members)
        width = max(m.width for m in members)
        rectangles.append((sid, members[0].x - length/2,
                           members[0].y - width/2, members[0].x + length/2,
                           members[0].y + width/2))
    for index, (sid, ax1, ay1, ax2, ay2) in enumerate(rectangles):
        for _, bx1, by1, bx2, by2 in rectangles[index + 1:]:
            separation_x = max(bx1 - ax2, ax1 - bx2)
            separation_y = max(by1 - ay2, ay1 - by2)
            if separation_x < GAP_X - EPS and separation_y < GAP_Y - EPS:
                errors.append(f"stack {sid}: insufficient XY gap")
    return errors


def run_case(index, profile, quantities, pallet):
    row = {
        "case_id": index + 1, "profile": profile, "pallet": pallet["name"],
        **{f"quantity_{sku}": quantities[sku] for sku in SKUS},
        "items": sum(quantities.values()),
        "requested_kg": sum(PRODUCTS[s].weight * q for s, q in quantities.items()),
        "status": "", "rejection_class": "", "necessary_bound": "",
        "runtime_ms": 0, "columns": 0, "highest_level": 0,
        "volume_utilization_pct": 0, "detail": "",
    }
    bound = necessary_bound(quantities, pallet)
    row["necessary_bound"] = bound
    t0 = time.perf_counter()
    try:
        planner = NewPalletPlanner()
        result = planner.generate(
            quantities=quantities,
            pallet_length=pallet["length"], pallet_width=pallet["width"],
            max_height=pallet["height"], max_weight=pallet["weight"],
            overhang=0.0, gap_x=GAP_X, gap_y=GAP_Y,
            edge_margin_x=EDGE_MARGIN_X, edge_margin_y=EDGE_MARGIN_Y,
        )
        if not result.success:
            row["status"] = "REJECT"
            row["rejection_class"] = (
                "PROVEN_NECESSARY_BOUND" if bound else "UNRESOLVED_HEURISTIC_REJECT"
            )
            row["detail"] = result.error
        else:
            problems = check_layout(result, quantities, pallet)
            row["status"] = "INVALID" if problems else "PASS"
            row["detail"] = " | ".join(problems[:10])
            row["columns"] = len({s.stack_id for s in result.slots})
            row["highest_level"] = max((s.level for s in result.slots), default=0)
            product_volume = sum(s.length*s.width*s.height for s in result.slots)
            pallet_volume = pallet["length"]*pallet["width"]*pallet["height"]
            row["volume_utilization_pct"] = round(100*product_volume/pallet_volume, 3)
    except Exception:
        row["status"] = "CRASH"
        row["detail"] = traceback.format_exc(limit=6).strip()
    row["runtime_ms"] = round((time.perf_counter()-t0)*1000, 3)
    return row


def p95(values):
    if not values:
        return 0
    values = sorted(values)
    pos = (len(values)-1)*0.95
    i = int(pos)
    return round(values[i]*(1-(pos-i)) + values[min(i+1, len(values)-1)]*(pos-i), 3)


def run_benchmark(cases=1000, seed=2026, output="benchmark_results", progress=50):
    if cases < 1:
        raise ValueError("cases must be >= 1")
    rng = random.Random(seed)
    rows = []
    for index in range(cases):
        profile, quantities = generate_order(rng, index)
        pallet = PALLETS[index % len(PALLETS)]
        rows.append(run_case(index, profile, quantities, pallet))
        if progress and (index+1) % progress == 0:
            statuses = Counter(r["status"] for r in rows)
            print(f"{index+1}/{cases}: {dict(statuses)}", flush=True)
    statuses = Counter(row["status"] for row in rows)
    passed = [r for r in rows if r["status"] == "PASS"]
    times = [r["runtime_ms"] for r in rows]
    profiles = {
        name: dict(Counter(r["status"] for r in rows if r["profile"] == name))
        for name in PROFILES
    }
    pallets = {
        pallet["name"]: dict(Counter(r["status"] for r in rows
                                    if r["pallet"] == pallet["name"]))
        for pallet in PALLETS
    }
    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed, "case_count": cases,
        "status_counts": {s: statuses[s] for s in ("PASS","REJECT","INVALID","CRASH")},
        "rejection_classes": dict(Counter(
            r["rejection_class"] for r in rows if r["status"] == "REJECT"
        )),
        "runtime_ms": {
            "total": round(sum(times), 3), "mean": round(mean(times), 3),
            "median": round(median(times), 3), "p95": p95(times),
            "max": max(times),
        },
        "success_mean_volume_utilization_pct": (
            round(mean(r["volume_utilization_pct"] for r in passed), 3)
            if passed else None
        ),
        "by_profile": profiles, "by_pallet": pallets,
        "settings": {
            "gap_x": GAP_X, "gap_y": GAP_Y,
            "edge_margin_x": EDGE_MARGIN_X,
            "edge_margin_y": EDGE_MARGIN_Y,
            "overhang": 0, "pallets": PALLETS,
        },
        "interpretation": (
            "REJECT without violated necessary bound is unresolved, not proven "
            "infeasible. PASS means configured geometry/accounting/sequence checks "
            "passed, not physical stability or robot reachability. "
            "Volume utilization uses bounding-box volume, not floor occupancy."
        ),
    }
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/"cases.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (folder/"summary.json").write_text(
        json.dumps(summary, indent=2)+"\n", encoding="utf-8"
    )
    report = "\n".join([
        "RANDOMIZED PALLET BENCHMARK",
        f"Cases: {cases} | Seed: {seed}",
        *(f"{s}: {statuses[s]}" for s in ("PASS","REJECT","INVALID","CRASH")),
        f"Unresolved rejects: {summary['rejection_classes'].get('UNRESOLVED_HEURISTIC_REJECT',0)}",
        f"Proven bound rejects: {summary['rejection_classes'].get('PROVEN_NECESSARY_BOUND',0)}",
        f"Mean runtime: {summary['runtime_ms']['mean']} ms",
        f"P95 runtime: {summary['runtime_ms']['p95']} ms",
        "NOTE: Clean REJECT is not proof of infeasibility.",
    ]) + "\n"
    (folder/"summary.txt").write_text(report, encoding="utf-8")
    print(report)
    print("Reports saved to:", folder.resolve())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", default="benchmark_results")
    parser.add_argument("--progress-every", type=int, default=50)
    args = parser.parse_args()
    if args.cases < 1:
        parser.error("--cases must be >= 1")
    result = run_benchmark(
        cases=args.cases, seed=args.seed,
        output=args.output, progress=args.progress_every
    )
    if result["status_counts"]["INVALID"] or result["status_counts"]["CRASH"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
