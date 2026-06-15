import json
import os
from statistics import mean


INPUT_FILE = "output/major_ai_rate.json"
OUTPUT_FILE = "output/major_ai_rate.json"
BASELINE_FILE = "config/major_baseline_rules.json"

K_LOW = 12
K_MID = 6

CONFIDENCE_FACTOR = {
    "high": 1.00,
    "medium": 0.92,
    "low": 0.75
}

EVIDENCE_FACTOR = {
    "direct": 1.00,
    "inferred": 0.82,
    "fallback": 0.55,
    "unknown": 0.45
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json_with_default(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def to_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def match_rule(row, rule):
    cond = rule.get("when", {})

    major_name = row.get("major_name", "") or ""
    major_category = row.get("major_category", "") or row.get("category", "") or ""
    discipline = row.get("discipline", "") or ""

    name_contains = cond.get("major_name_contains", [])
    if name_contains and not any(x in major_name for x in name_contains):
        return False

    category_in = cond.get("major_category_in", [])
    if category_in and major_category not in category_in:
        return False

    discipline_in = cond.get("discipline_in", [])
    if discipline_in and discipline not in discipline_in:
        return False

    return True


def get_baseline_rate(row, baseline_rules):
    best = 0.0
    for rule in baseline_rules:
        if match_rule(row, rule):
            val = to_float(rule.get("min_replace_rate", 0))
            if val > best:
                best = val
    return best


def safe_text(v, fallback="未分类"):
    s = str(v or "").strip()
    return s if s else fallback


def get_raw_rate(row):
    if row.get("raw_replace_rate") is not None:
        return float(row.get("raw_replace_rate") or 0)
    return float(row.get("replace_rate") or 0)


def get_confidence(row):
    return str(row.get("confidence") or "low").lower()


def get_job_count(row):
    return int(row.get("job_count") or 0)


def get_evidence_level(row):
    return str(row.get("evidence_level") or "unknown").lower()


def is_explicit_keep_zero(row):
    return row.get("zero_override_reason") == "keep_zero"


def build_category_stats(rows):
    bucket = {}

    for row in rows:
        category = safe_text(row.get("major_category"), "未分类")
        raw_rate = get_raw_rate(row)

        if category not in bucket:
            bucket[category] = {
                "major_count": 0,
                "total_raw_rate": 0.0,
                "total_job_count": 0
            }

        bucket[category]["major_count"] += 1
        bucket[category]["total_raw_rate"] += raw_rate
        bucket[category]["total_job_count"] += get_job_count(row)

    category_stats = {}
    for category, item in bucket.items():
        major_count = item["major_count"]
        category_stats[category] = {
            "category_replace_rate": round(
                item["total_raw_rate"] / major_count if major_count else 0.0,
                4
            ),
            "category_major_count": major_count,
            "category_job_count": item["total_job_count"]
        }

    return category_stats


def compute_adjusted_rate(raw_rate, job_count, confidence, category_rate, baseline_rate, evidence_level):
    raw_rate = float(raw_rate or 0)
    job_count = int(job_count or 0)
    confidence = (confidence or "low").lower()
    category_rate = float(category_rate or 0)
    baseline_rate = float(baseline_rate or 0)
    evidence_factor = EVIDENCE_FACTOR.get(evidence_level, EVIDENCE_FACTOR["unknown"])

    if confidence in {"high", "medium"}:
        confidence_weight = CONFIDENCE_FACTOR.get(confidence, 0.92) * evidence_factor
        adjusted = raw_rate * confidence_weight + category_rate * (1 - confidence_weight)
        return round(clamp(adjusted), 4), round(confidence_weight, 4), "confidence_blend_raw_category"

    if job_count <= 0:
        adjusted = max(raw_rate, baseline_rate)
        return round(clamp(adjusted), 4), 0.0, "no_job_use_raw_or_baseline"

    sample_weight = job_count / (job_count + K_LOW)
    confidence_weight = clamp(sample_weight * CONFIDENCE_FACTOR["low"] * evidence_factor)
    floor_rate = max(baseline_rate, raw_rate)
    blended = raw_rate * confidence_weight + category_rate * (1 - confidence_weight)
    adjusted = max(floor_rate, blended)
    return round(clamp(adjusted), 4), round(confidence_weight, 4), "low_confidence_weighted_blend"


def main():
    rows = load_json(INPUT_FILE)

    if not rows:
        save_json(OUTPUT_FILE, rows)
        print(f"recomputed: {OUTPUT_FILE} (empty)")
        return

    baseline_rules = load_json_with_default(BASELINE_FILE, {}).get("baseline_rules", [])

    for row in rows:
        row["raw_replace_rate"] = round(get_raw_rate(row), 4)
        row["raw_impact_rate"] = row["raw_replace_rate"]

    global_mean = mean(row["raw_replace_rate"] for row in rows)
    category_stats = build_category_stats(rows)

    for row in rows:
        category = safe_text(row.get("major_category"), "未分类")
        cat_info = category_stats.get(category, {
            "category_replace_rate": round(global_mean, 4),
            "category_major_count": 0,
            "category_job_count": 0
        })

        category_rate = float(cat_info["category_replace_rate"])
        baseline_rate = get_baseline_rate(row, baseline_rules)

        if is_explicit_keep_zero(row):
            adjusted_rate, confidence_weight, adjust_mode = 0.0, 0.0, "explicit_keep_zero"
        else:
            adjusted_rate, confidence_weight, adjust_mode = compute_adjusted_rate(
                raw_rate=row["raw_replace_rate"],
                job_count=get_job_count(row),
                confidence=get_confidence(row),
                category_rate=category_rate,
                baseline_rate=baseline_rate,
                evidence_level=get_evidence_level(row)
            )

        row["adjusted_replace_rate"] = adjusted_rate
        row["adjusted_impact_rate"] = adjusted_rate
        row["impact_rate"] = adjusted_rate
        row["confidence_weight"] = confidence_weight
        row["global_mean_replace_rate"] = round(global_mean, 4)
        row["category_replace_rate"] = round(category_rate, 4)
        row["baseline_replace_rate"] = round(baseline_rate, 4)
        row["category_major_count"] = int(cat_info["category_major_count"])
        row["category_job_count"] = int(cat_info["category_job_count"])
        row["adjust_mode"] = adjust_mode

    rows.sort(
        key=lambda x: (
            -float(x.get("adjusted_replace_rate", 0) or 0),
            -int(x.get("job_count", 0) or 0),
            x.get("major_code", "")
        )
    )

    save_json(OUTPUT_FILE, rows)
    print(f"recomputed: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
