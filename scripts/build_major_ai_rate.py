import json
import os
from statistics import mean


MAJORS_JSON = "output/majors.normalized.json"
JOBS_JSON = "output/jobs.normalized.json"
RULES_JSON = "output/major_job_rules.auto.json"
AI_RULES_JSON = "config/ai_replace_rules.json"

OUTPUT_FILE = "output/major_ai_rate.json"

K = 10

CONFIDENCE_FACTOR = {
    "high": 1.00,
    "medium": 0.85,
    "low": 0.70
}

EVIDENCE_FACTOR = {
    "direct": 1.00,
    "inferred": 0.78,
    "fallback": 0.45,
    "unknown": 0.35
}

MATCH_FACTOR = {
    "title": 1.00,
    "category": 0.70,
    "title_and_category": 1.15
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clamp(x, lo=0, hi=1):
    return max(lo, min(hi, x))


def score_job(job, replace_rules):
    text = (
        str(job.get("job_title", "")) + " " +
        str(job.get("category", "")) + " " +
        str(job.get("job_desc", ""))
    ).lower()

    score = replace_rules.get("base", 0.35)

    for kw in replace_rules.get("high_plus", []):
        if kw.lower() in text:
            score += 0.12

    for kw in replace_rules.get("mid_plus", []):
        if kw.lower() in text:
            score += 0.06

    for kw in replace_rules.get("minus", []):
        if kw.lower() in text:
            score -= 0.10

    exposure = job.get("exposure", 0)
    if isinstance(exposure, int):
        score += min(exposure, 5) * 0.03

    return round(clamp(score), 4)


def get_evidence_level(rule):
    level = str(rule.get("evidence_level") or "").strip()
    if level:
        return level

    source = str(rule.get("rule_source") or "").strip()
    if source == "employment_direction":
        return "direct"
    if source == "major_name_inference":
        return "inferred"
    if source in {"major_category_fallback", "discipline_fallback"}:
        return "fallback"
    return "unknown"


def get_match_type(job, include_titles, include_categories):
    title_hit = job.get("job_title", "") in include_titles
    category_hit = job.get("category", "") in include_categories
    if title_hit and category_hit:
        return "title_and_category"
    if title_hit:
        return "title"
    if category_hit:
        return "category"
    return ""


def compute_job_weight(job, match_type, evidence_level):
    employment_workers = max(0, int(job.get("employment_workers") or 0))
    worker_weight = 1.0
    if employment_workers > 0:
        worker_weight += min(employment_workers, 1000) / 1000

    match_weight = MATCH_FACTOR.get(match_type, 0)
    evidence_weight = EVIDENCE_FACTOR.get(evidence_level, EVIDENCE_FACTOR["unknown"])
    return round(worker_weight * match_weight * evidence_weight, 4)


def match_jobs_for_major(rule, jobs):
    include_titles = set(rule.get("include_titles", []))
    include_categories = set(rule.get("include_categories", []))
    exclude_titles = set(rule.get("exclude_titles", []))
    evidence_level = get_evidence_level(rule)

    matched = []
    for job in jobs:
        jt = job.get("job_title", "")

        if jt in exclude_titles:
            continue

        match_type = get_match_type(job, include_titles, include_categories)
        if match_type:
            item = dict(job)
            item["match_type"] = match_type
            item["match_weight"] = compute_job_weight(item, match_type, evidence_level)
            matched.append(item)

    return matched


def compute_confidence(job_count):
    if job_count >= 8:
        return "high"
    if job_count >= 3:
        return "medium"
    return "low"


def compute_weighted_rate(matched_jobs):
    weighted_sum = 0.0
    total_weight = 0.0
    for job in matched_jobs:
        weight = float(job.get("match_weight") or 0)
        if weight <= 0:
            continue
        weighted_sum += float(job.get("ai_replace_score") or 0) * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.0, 0.0
    return round(clamp(weighted_sum / total_weight), 4), round(total_weight, 4)


def build_job_contributions(matched_jobs, limit=12):
    rows = []
    for job in matched_jobs:
        rows.append({
            "job_title": job.get("job_title", ""),
            "category": job.get("category", ""),
            "ai_impact_score": job.get("ai_replace_score", 0),
            "employment_workers": job.get("employment_workers", 0),
            "match_type": job.get("match_type", ""),
            "weight": job.get("match_weight", 0),
            "weighted_contribution": round(
                float(job.get("ai_replace_score") or 0) * float(job.get("match_weight") or 0),
                4
            )
        })

    rows.sort(key=lambda x: (-float(x["weighted_contribution"] or 0), x["job_title"]))
    return rows[:limit]


def compute_adjusted_rate(raw_rate, job_count, confidence, global_mean, k=K):
    raw_rate = float(raw_rate or 0)
    job_count = int(job_count or 0)
    confidence = (confidence or "low").lower()

    conf_factor = CONFIDENCE_FACTOR.get(confidence, 0.70)
    sample_weight = job_count / (job_count + k) if job_count >= 0 else 0.0
    shrink_weight = clamp(sample_weight * conf_factor)

    adjusted = raw_rate * shrink_weight + global_mean * (1 - shrink_weight)
    return round(clamp(adjusted), 4), round(shrink_weight, 4)


def main():
    majors = load_json(MAJORS_JSON)
    jobs = load_json(JOBS_JSON)
    rules_data = load_json(RULES_JSON)
    replace_rules = load_json(AI_RULES_JSON)

    code_rules = rules_data.get("major_code_rules", {})

    scored_jobs = []
    for job in jobs:
        job = dict(job)
        job["ai_replace_score"] = score_job(job, replace_rules)
        scored_jobs.append(job)

    result = []
    for major in majors:
        code = major["major_code"]
        rule = code_rules.get(code, {
            "include_titles": [],
            "include_categories": [],
            "exclude_titles": [],
            "rule_source": "unmapped",
            "evidence_level": "unknown"
        })
        matched_jobs = match_jobs_for_major(rule, scored_jobs)

        replace_rate, total_match_weight = compute_weighted_rate(matched_jobs)

        job_titles = sorted(list({j["job_title"] for j in matched_jobs}))[:20]
        job_count = len(matched_jobs)
        confidence = compute_confidence(job_count)
        evidence_level = get_evidence_level(rule)
        rule_source = rule.get("rule_source", "unmapped")

        result.append({
            "major_code": code,
            "major_name": major["major_name"],
            "degree_level": major.get("degree_level", ""),
            "discipline": major.get("discipline", ""),
            "major_category": major.get("major_category", ""),
            "replace_rate": replace_rate,
            "impact_rate": replace_rate,
            "raw_replace_rate": replace_rate,
            "raw_impact_rate": replace_rate,
            "job_count": job_count,
            "total_match_weight": total_match_weight,
            "rule_source": rule_source,
            "evidence_level": evidence_level,
            "matched_job_titles_sample": job_titles,
            "matched_job_contributions": build_job_contributions(matched_jobs),
            "confidence": confidence
        })

    global_mean = mean(float(r.get("raw_replace_rate", 0) or 0) for r in result) if result else 0.0

    for row in result:
        adjusted_rate, confidence_weight = compute_adjusted_rate(
            raw_rate=row["raw_replace_rate"],
            job_count=row["job_count"],
            confidence=row["confidence"],
            global_mean=global_mean,
            k=K
        )

        row["adjusted_replace_rate"] = adjusted_rate
        row["confidence_weight"] = confidence_weight
        row["global_mean_replace_rate"] = round(global_mean, 4)

    result.sort(
        key=lambda x: (
            -float(x.get("adjusted_replace_rate", 0) or 0),
            -int(x.get("job_count", 0) or 0),
            x.get("major_code", "")
        )
    )

    save_json(OUTPUT_FILE, result)
    print(f"generated: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
