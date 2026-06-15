import json
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple


MAJORS_JSON = "output/majors.normalized.json"
JOBS_JSON = "output/jobs.normalized.json"
INFERENCE_RULES_JSON = "config/major_name_inference_rules.json"

OUT_JOB_TITLES = "output/all_job_titles.json"
OUT_MAJOR_DIRECTIONS = "output/major_employment_directions.json"
OUT_RULES = "output/major_job_rules.auto.json"
OUT_SUMMARY = "output/major_job_rules.auto.summary.json"
OUT_REPORT = "output/major_rule_generation_report.json"


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_text(s: Any) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("、", "")
    s = re.sub(r"\s+", "", s)
    return s


def split_title_variants(title: str) -> List[str]:
    parts = {title}
    for sep in ["/", "、", "／", "|"]:
        if sep in title:
            for x in title.split(sep):
                x = x.strip()
                if x:
                    parts.add(x)
    return sorted(parts, key=len, reverse=True)


def build_alias_map(jobs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], Dict[str, str], Dict[str, List[str]]]:
    manual_alias_map = {
        "内容创作者/编辑": ["编辑", "内容编辑", "文案", "新媒体编辑", "内容创作者", "编辑记者"],
        "新闻记者": ["记者", "新闻记者", "采编"],
        "平面设计师": ["平面设计", "视觉设计", "美工", "设计师"],
        "数据分析师": ["数据分析", "分析师", "商业分析"],
        "测试工程师": ["测试工程师", "软件测试", "测试"],
        "软件工程师": ["软件工程师", "开发工程师", "程序员", "后端", "前端", "研发工程师"],
        "会计与出纳": ["会计", "出纳", "财务"],
        "银行柜员": ["柜员", "银行柜员"],
        "证券分析师": ["证券分析师", "投研", "研究员", "证券研究"],
        "高中教师": ["高中教师", "高中老师", "中学教师"],
        "初中教师": ["初中教师", "初中老师"],
        "大学教师": ["大学教师", "高校教师", "讲师", "教授"],
        "教师": ["教师", "老师"],
        "行政专员/助理": ["行政", "行政专员", "行政助理", "助理"],
        "公务员": ["公务员", "公务员(中央国家机关)", "公务员(省级机关)", "公务员(地市级机关)", "公务员(区县级及以下机关)", "事业单位人员", "事业单位", "选调生"],
        "私营企业主": ["企业主", "创业", "创业者", "老板", "私营企业主"],
        "医生": ["医生", "医师", "临床医生"],
        "护士": ["护士", "护理"],
        "律师": ["律师", "法务"],
        "销售": ["销售", "销售专员", "门店销售", "线下门店销售"],
        "产品经理": ["产品经理", "产品"],
        "考研": ["考研", "继续深造", "读研", "升学"]
    }

    all_titles = []
    title_to_category = {}
    title_aliases = {}

    for item in jobs:
        title = str(item.get("job_title", "")).strip()
        category = str(item.get("category", "")).strip()
        if not title:
            continue

        all_titles.append({"title": title, "category": category})
        title_to_category[title] = category

        aliases = set(split_title_variants(title))
        for alias in manual_alias_map.get(title, []):
            aliases.add(alias)

        title_aliases[title] = sorted(
            [x for x in aliases if x],
            key=lambda x: len(normalize_text(x)),
            reverse=True
        )

    for std_title, aliases in manual_alias_map.items():
        if std_title not in title_aliases:
            title_aliases[std_title] = sorted(
                [x for x in set([std_title] + aliases) if x],
                key=lambda x: len(normalize_text(x)),
                reverse=True
            )
            title_to_category.setdefault(std_title, "")

    return all_titles, title_to_category, title_aliases


def extract_direction_tokens(raw_text: str, title_aliases: Dict[str, List[str]]) -> List[Dict[str, str]]:
    text = normalize_text(raw_text)
    if not text:
        return []

    alias_items = []
    for std_title, aliases in title_aliases.items():
        for alias in aliases:
            alias_norm = normalize_text(alias)
            if alias_norm:
                alias_items.append((std_title, alias, alias_norm))

    alias_items.sort(key=lambda x: len(x[2]), reverse=True)

    matched = []
    used_spans = []

    for std_title, alias, alias_norm in alias_items:
        start = 0
        while True:
            idx = text.find(alias_norm, start)
            if idx == -1:
                break
            end = idx + len(alias_norm)

            overlap = False
            for s, e in used_spans:
                if not (end <= s or idx >= e):
                    overlap = True
                    break

            if not overlap:
                matched.append({
                    "standard_title": std_title,
                    "matched_alias": alias
                })
                used_spans.append((idx, end))

            start = idx + 1

    uniq = []
    seen = set()
    for x in matched:
        key = (x["standard_title"], x["matched_alias"])
        if key not in seen:
            seen.add(key)
            uniq.append(x)

    return uniq


def infer_from_major_name(major_name: str, rules: Dict[str, Any]) -> Dict[str, List[str]]:
    text = normalize_text(major_name)
    hit_titles = set()
    hit_categories = set()

    for rule in rules.get("major_name_rules", []):
        keywords = rule.get("keywords", [])
        if any(k in text for k in keywords):
            for t in rule.get("include_titles", []):
                hit_titles.add(t)
            for c in rule.get("include_categories", []):
                hit_categories.add(c)

    return {
        "include_titles": sorted(hit_titles),
        "include_categories": sorted(hit_categories)
    }


def build_major_code_rules(
    majors: List[Dict[str, Any]],
    title_to_category: Dict[str, str],
    title_aliases: Dict[str, List[str]],
    inference_rules: Dict[str, Any]
):
    rules = {}
    extracted_rows = []
    unmapped = []
    report = []

    for row in majors:
        code = row["major_code"]
        raw = row.get("employment_direction_raw", "")
        major_name = row.get("major_name", "")

        source = None
        titles = []
        categories = []

        tokens = extract_direction_tokens(raw, title_aliases)
        if tokens:
            titles = sorted(list({x["standard_title"] for x in tokens if x["standard_title"]}))
            categories = sorted(list({
                title_to_category.get(t, "")
                for t in titles
                if title_to_category.get(t, "")
            }))
            source = "employment_direction"

        if not titles and not categories:
            inferred = infer_from_major_name(major_name, inference_rules)
            titles = inferred["include_titles"]
            categories = inferred["include_categories"]
            if titles or categories:
                source = "major_name_inference"

        extracted_rows.append({
            "major_code": row["major_code"],
            "major_name": row["major_name"],
            "degree_level": row["degree_level"],
            "discipline": row["discipline"],
            "major_category": row["major_category"],
            "employment_direction_raw": raw,
            "matched_titles": titles,
            "matched_details": tokens,
            "rule_source": source or "unmapped"
        })

        if titles or categories:
            rules[code] = {
                "include_categories": categories,
                "include_titles": titles,
                "exclude_titles": []
            }
            report.append({
                "major_code": row["major_code"],
                "major_name": row["major_name"],
                "rule_source": source,
                "include_categories": categories,
                "include_titles": titles
            })
        else:
            unmapped.append({
                "major_code": row["major_code"],
                "major_name": row["major_name"],
                "major_category": row["major_category"],
                "discipline": row["discipline"],
                "employment_direction_raw": raw
            })

    return rules, extracted_rows, unmapped, report


def build_major_category_rules(majors, major_code_rules):
    code_to_major = {x["major_code"]: x for x in majors}
    bucket = defaultdict(lambda: {
        "categories": Counter(),
        "titles": Counter(),
        "major_codes": [],
        "examples": []
    })

    for code, rule in major_code_rules.items():
        major = code_to_major.get(code)
        if not major:
            continue

        mc = major["major_category"]
        if not mc:
            continue

        b = bucket[mc]

        for c in rule.get("include_categories", []):
            b["categories"][c] += 1
        for t in rule.get("include_titles", []):
            b["titles"][t] += 1

        b["major_codes"].append(code)
        if len(b["examples"]) < 8:
            b["examples"].append({
                "major_code": code,
                "major_name": major["major_name"]
            })

    out = {}
    for mc, b in bucket.items():
        out[mc] = {
            "_meta": {
                "derived_from_major_count": len(b["major_codes"]),
                "examples": b["examples"]
            },
            "include_categories": [k for k, v in b["categories"].most_common(10) if v >= 1],
            "include_titles": [k for k, v in b["titles"].most_common(15) if v >= 1],
            "exclude_titles": []
        }

    return out


def build_discipline_rules(majors, major_category_rules):
    discipline_to_categories = defaultdict(Counter)

    for row in majors:
        discipline = row.get("discipline", "")
        major_category = row.get("major_category", "")
        if discipline and major_category:
            discipline_to_categories[discipline][major_category] += 1

    out = {}
    for discipline, counter in discipline_to_categories.items():
        agg_categories = Counter()
        agg_titles = Counter()
        top_major_categories = [k for k, _ in counter.most_common(20)]

        for mc in top_major_categories:
            rule = major_category_rules.get(mc)
            if not rule:
                continue

            for c in rule.get("include_categories", []):
                agg_categories[c] += 1
            for t in rule.get("include_titles", []):
                agg_titles[t] += 1

        out[discipline] = {
            "_meta": {
                "derived_from_major_categories": top_major_categories
            },
            "include_categories": [k for k, _ in agg_categories.most_common(10)],
            "include_titles": [k for k, _ in agg_titles.most_common(15)],
            "exclude_titles": []
        }

    return out


def fill_unmapped_with_fallbacks(majors, major_code_rules, major_category_rules, discipline_rules, report):
    for row in majors:
        code = row["major_code"]
        if code in major_code_rules:
            continue

        major_category = row.get("major_category", "")
        discipline = row.get("discipline", "")

        fallback = None
        source = None

        if major_category in major_category_rules:
            fallback = major_category_rules[major_category]
            source = "major_category_fallback"
        elif discipline in discipline_rules:
            fallback = discipline_rules[discipline]
            source = "discipline_fallback"

        if fallback:
            major_code_rules[code] = {
                "include_categories": fallback.get("include_categories", []),
                "include_titles": fallback.get("include_titles", []),
                "exclude_titles": [],
                "rule_source": source,
                "evidence_level": "fallback"
            }
            report.append({
                "major_code": row["major_code"],
                "major_name": row["major_name"],
                "rule_source": source,
                "include_categories": fallback.get("include_categories", []),
                "include_titles": fallback.get("include_titles", [])
            })

    return major_code_rules, report


def enrich_rule_metadata(major_code_rules, report):
    report_source = {
        item.get("major_code"): item.get("rule_source", "unmapped")
        for item in report
    }
    source_to_evidence = {
        "employment_direction": "direct",
        "major_name_inference": "inferred",
        "major_category_fallback": "fallback",
        "discipline_fallback": "fallback"
    }

    for code, rule in major_code_rules.items():
        source = rule.get("rule_source") or report_source.get(code, "unmapped")
        rule["rule_source"] = source
        rule["evidence_level"] = source_to_evidence.get(source, "unknown")

    for item in report:
        source = item.get("rule_source", "unmapped")
        item["evidence_level"] = source_to_evidence.get(source, "unknown")

    return major_code_rules, report


def main() -> None:
    majors = load_json(MAJORS_JSON)
    jobs = load_json(JOBS_JSON)
    inference_rules = load_json(INFERENCE_RULES_JSON)

    all_titles, title_to_category, title_aliases = build_alias_map(jobs)

    major_code_rules, extracted_rows, unmapped, report = build_major_code_rules(
        majors, title_to_category, title_aliases, inference_rules
    )

    major_category_rules = build_major_category_rules(majors, major_code_rules)
    discipline_rules = build_discipline_rules(majors, major_category_rules)

    major_code_rules, report = fill_unmapped_with_fallbacks(
        majors, major_code_rules, major_category_rules, discipline_rules, report
    )

    major_code_rules, report = enrich_rule_metadata(major_code_rules, report)

    source_counter = Counter([x["rule_source"] for x in report])

    rules = {
        "_meta": {
            "description": "由专业就业方向 + 专业名称推断 + 专业类/学科兜底自动生成",
            "priority": "major_code_rules > major_category_rules > discipline_rules"
        },
        "major_code_rules": major_code_rules,
        "major_category_rules": major_category_rules,
        "discipline_rules": discipline_rules
    }

    summary = {
        "major_total": len(majors),
        "job_title_total": len(all_titles),
        "major_code_rules_generated": len(major_code_rules),
        "major_category_rules_generated": len(major_category_rules),
        "discipline_rules_generated": len(discipline_rules),
        "rule_source_count": dict(source_counter),
        "unmapped_major_count": len([m for m in majors if m["major_code"] not in major_code_rules]),
        "unmapped_examples": [m for m in majors if m["major_code"] not in major_code_rules][:100]
    }

    save_json(OUT_JOB_TITLES, {
        "job_titles": all_titles,
        "title_aliases": title_aliases
    })
    save_json(OUT_MAJOR_DIRECTIONS, extracted_rows)
    save_json(OUT_RULES, rules)
    save_json(OUT_SUMMARY, summary)
    save_json(OUT_REPORT, report)

    print("generated:")
    print("-", OUT_JOB_TITLES)
    print("-", OUT_MAJOR_DIRECTIONS)
    print("-", OUT_RULES)
    print("-", OUT_SUMMARY)
    print("-", OUT_REPORT)


if __name__ == "__main__":
    main()
