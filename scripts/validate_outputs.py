import json
import os
import sys
from collections import Counter


MAJOR_RATE_FILE = "output/major_ai_rate.json"
ZERO_OVERRIDE_FILE = "config/major_zero_override.json"

MIN_MAJOR_COUNT = 1000
MAX_FALLBACK_TOP20 = 8


def load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fail(message):
    print(f"VALIDATION ERROR: {message}", file=sys.stderr)
    return 1


def metric(row):
    if row.get("adjusted_impact_rate") is not None:
        return float(row.get("adjusted_impact_rate") or 0)
    if row.get("adjusted_replace_rate") is not None:
        return float(row.get("adjusted_replace_rate") or 0)
    return float(row.get("replace_rate") or 0)


def main():
    rows = load_json(MAJOR_RATE_FILE, [])
    if len(rows) < MIN_MAJOR_COUNT:
        return fail(f"major count too low: {len(rows)} < {MIN_MAJOR_COUNT}")

    missing_evidence = [
        row.get("major_code", "")
        for row in rows
        if not row.get("evidence_level")
    ]
    if missing_evidence:
        return fail(f"rows missing evidence_level: {missing_evidence[:10]}")

    top20 = sorted(rows, key=metric, reverse=True)[:20]
    fallback_top20 = [
        row.get("major_name", "")
        for row in top20
        if row.get("evidence_level") == "fallback"
    ]
    if len(fallback_top20) > MAX_FALLBACK_TOP20:
        return fail(f"too many fallback rows in top20: {len(fallback_top20)} {fallback_top20[:10]}")

    zero_cfg = load_json(ZERO_OVERRIDE_FILE, {})
    keep_zero = set(zero_cfg.get("zero_keep_names", []))
    violated = []
    for row in rows:
        if row.get("major_name") in keep_zero and row.get("zero_override_reason") == "keep_zero":
            if metric(row) != 0:
                violated.append({
                    "major_name": row.get("major_name"),
                    "adjusted_impact_rate": metric(row)
                })
    if violated:
        return fail(f"explicit keep-zero rows have non-zero adjusted impact: {violated[:10]}")

    evidence_counts = Counter(row.get("evidence_level", "unknown") for row in rows)
    print("validated:", MAJOR_RATE_FILE)
    print("major_count:", len(rows))
    print("evidence_counts:", dict(evidence_counts))
    print("top20_fallback_count:", len(fallback_top20))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
