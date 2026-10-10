"""Validate data/alerts.json against data/scenario.json.

Usage:  python ai/validate_alerts.py [alerts_path] [scenario_path]
Exit code 0 = valid, 1 = invalid. No third-party packages needed.

Every alert must name its village (English and Nepali) and contain exactly the two lead times the
pipeline computed, as digits, and no other number. Lead times are minutes from when the alert is
sent: arrival window minus alert_delay_min. Devanagari digits count as digits.
"""
import json
import re
import sys

SCHEMA_VERSION = "1.0"
MAX_CHARS = 400
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
NUMBER_RE = re.compile(r"\d+")


def lead_minutes(village, alert_delay_min):
    """[earliest, latest] minutes from sending the alert to the flood's possible arrival."""
    return [round(village["eta_min"][0] - alert_delay_min), round(village["eta_min"][1] - alert_delay_min)]


def numbers_in(text):
    return [int(n) for n in NUMBER_RE.findall(text.translate(DEVANAGARI_DIGITS))]


def compact(text):
    # Ignore spaces, zero-width joiners and case so "स्याप्रुबेसी" matches "स्याप्रु बेसी".
    return re.sub(r"[\s‌‍]+", "", text).lower()


def check_texts(text_en, text_ne, village, lead):
    """Return a list of problems with one village's alert; empty means it passes."""
    problems = []
    for lang, text in (("text_en", text_en), ("text_ne", text_ne)):
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{lang} is empty")
            continue
        if len(text) > MAX_CHARS:
            problems.append(f"{lang} is longer than {MAX_CHARS} characters")
        nums = numbers_in(text)
        if sorted(set(nums)) != sorted(set(lead)):
            problems.append(f"{lang} numbers {nums} must be exactly {lead[0]} and {lead[1]}")
    if isinstance(text_en, str) and compact(village["name_en"]) not in compact(text_en):
        problems.append(f"text_en does not name {village['name_en']}")
    if isinstance(text_ne, str) and village.get("name_ne") and compact(village["name_ne"]) not in compact(text_ne):
        problems.append(f"text_ne does not name {village['name_ne']}")
    return problems


def validate(alerts, scenario):
    errors = []
    if alerts.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: expected '{SCHEMA_VERSION}', got {alerts.get('schema_version')!r}")
    if alerts.get("scenario_event_id") != scenario["event"]["id"]:
        errors.append(f"scenario_event_id {alerts.get('scenario_event_id')!r} != scenario {scenario['event']['id']!r}")
    villages = {v["id"]: v for v in scenario["villages"]}
    seen = set()
    for i, a in enumerate(alerts.get("alerts", [])):
        p = f"alerts[{i}]"
        v = villages.get(a.get("village_id"))
        if v is None:
            errors.append(f"{p}: unknown village_id {a.get('village_id')!r}")
            continue
        if v["id"] in seen:
            errors.append(f"{p}: duplicate alert for {v['id']}")
        seen.add(v["id"])
        lead = lead_minutes(v, scenario["alert_delay_min"])
        if a.get("lead_min") != lead:
            errors.append(f"{p}: lead_min {a.get('lead_min')} != scenario {lead}")
        errors += [f"{p} ({v['id']}): {msg}" for msg in check_texts(a.get("text_en"), a.get("text_ne"), v, lead)]
    for vid in villages.keys() - seen:
        errors.append(f"no alert for village {vid}")
    return errors


def main():
    alerts_path = sys.argv[1] if len(sys.argv) > 1 else "data/alerts.json"
    scenario_path = sys.argv[2] if len(sys.argv) > 2 else "data/scenario.json"
    try:
        with open(alerts_path, encoding="utf-8") as f:
            alerts = json.load(f)
        with open(scenario_path, encoding="utf-8") as f:
            scenario = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: {e}")
        return 1
    errors = validate(alerts, scenario)
    if errors:
        print(f"FAIL: {len(errors)} problem(s) in {alerts_path}")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK: {alerts_path} matches {scenario_path} ({len(alerts['alerts'])} alerts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
