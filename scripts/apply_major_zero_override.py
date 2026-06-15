import json
import os

INPUT_FILE = "output/major_ai_rate.json"
CONFIG_FILE = "config/major_zero_override.json"
OUTPUT_FILE = "output/major_ai_rate.json"
SUMMARY_FILE = "output/major_zero_override.summary.json"


def load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def main():
    rows = load_json(INPUT_FILE, [])
    cfg = load_json(CONFIG_FILE, {})

    zero_keep_names = set(cfg.get("zero_keep_names", []))
    exact_name_rates = cfg.get("exact_name_rates", {})
    keyword_rules = cfg.get("keyword_rules", [])

    changed = 0
    kept_zero = 0
    examples = []

    for row in rows:
        name = (row.get("major_name") or "").strip()
        old_rate = to_float(row.get("replace_rate", 0))

        if old_rate > 0:
            continue

        if name in zero_keep_names:
            row["zero_override_reason"] = "keep_zero"
            kept_zero += 1
            continue

        new_rate = 0.0
        reasons = []

        if name in exact_name_rates:
            new_rate = float(exact_name_rates[name])
            reasons.append(f"exact:{name}")

        for rule in keyword_rules:
            keywords = rule.get("keywords", [])
            rate = float(rule.get("rate", 0))
            if any(k in name for k in keywords):
                if rate > new_rate:
                    new_rate = rate
                reasons.append(f"kw:{rule.get('name', '')}")

        if new_rate > 0:
            row["pre_override_replace_rate"] = old_rate
            row["pre_override_impact_rate"] = old_rate
            row["raw_replace_rate"] = round(new_rate, 4)
            row["raw_impact_rate"] = round(new_rate, 4)
            row["replace_rate"] = round(new_rate, 4)
            row["impact_rate"] = round(new_rate, 4)
            row["zero_override_rate"] = round(new_rate, 4)
            row["zero_override_reason"] = "|".join(dict.fromkeys(reasons))
            changed += 1
            if len(examples) < 50:
                examples.append({
                    "major_name": name,
                    "replace_rate": row["replace_rate"],
                    "reason": row["zero_override_reason"]
                })

    summary = {
        "input_file": INPUT_FILE,
        "changed_rows": changed,
        "kept_zero_rows": kept_zero,
        "examples": examples
    }

    save_json(OUTPUT_FILE, rows)
    save_json(SUMMARY_FILE, summary)

    print(f"changed_rows: {changed}")
    print(f"kept_zero_rows: {kept_zero}")
    print(f"output: {OUTPUT_FILE}")
    print(f"summary: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
