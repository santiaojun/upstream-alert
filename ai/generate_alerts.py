"""Generate data/alerts.json: one English + Nepali alert per village, written by an LLM.

Usage:  python ai/generate_alerts.py      then  python ai/validate_alerts.py
No third-party packages. Needs the Claude Code CLI (`claude`), logged in; it calls `claude -p`
with tools, skills, plugins and hooks switched off, so it runs on the caller's Claude account.

The pipeline computes every number; the LLM only words the message. Each draft is checked with
ai/validate_alerts.py and regenerated (with the problems fed back) up to MAX_ATTEMPTS times.
If any village's alert never passes, nothing is written and the script exits with an error.
"""
import concurrent.futures
import datetime as dt
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_alerts import SCHEMA_VERSION, check_texts, lead_minutes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIO = os.path.join(ROOT, "data", "scenario.json")
OUT = os.path.join(ROOT, "data", "alerts.json")
MODEL = "sonnet"  # Claude Code model alias; the exact model id is recorded in alerts.json
MAX_ATTEMPTS = 3
WORKERS = 4
TIMEOUT_S = 180

SYSTEM_PROMPT = (
    "You write short flood evacuation alerts for villages in Nepal, sent as SMS. "
    "Use plain words that are easy to understand under stress. Reply with JSON only."
)
SCHEMA = {
    "type": "object",
    "properties": {"text_en": {"type": "string"}, "text_ne": {"type": "string"}},
    "required": ["text_en", "text_ne"],
    "additionalProperties": False,
}


def prompt_for(village, lead, problems=None):
    p = (f"Village: {village['name_en']} (Nepali: {village['name_ne']}).\n"
         f"A flood from upstream may reach it in as little as {lead[0]} minutes and at most {lead[1]} minutes "
         "from now.\n"
         "Write text_en (English, at most 35 words) and text_ne (the same message in Nepali, Devanagari script).\n"
         "Rules: name the village in both; give both numbers of minutes, written as digits; use no other "
         "numbers at all (no clock times, distances or magnitudes); tell people to move to high ground away "
         "from the river now and not wait to see the water. In Nepali, give instructions in the polite command "
         "form (for example जानुहोस्, नपर्खनुहोस्), not as statements.")
    if problems:
        p += "\nYour previous draft had these problems, fix them:\n- " + "\n- ".join(problems)
    return p


def clean_env():
    """Environment without an enclosing Claude Code session's variables, so `claude` uses the user's own login."""
    return {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k == "ANTHROPIC_BASE_URL")}


def call_llm(prompt):
    """Return (texts dict, model ids) from one headless Claude Code call."""
    cmd = ["claude", "-p", "--safe-mode", "--no-session-persistence", "--model", MODEL, "--tools", "",
           "--output-format", "json", "--system-prompt", SYSTEM_PROMPT, "--json-schema", json.dumps(SCHEMA), prompt]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, cwd=ROOT, env=clean_env())
    reply = json.loads(out.stdout)
    if reply.get("is_error"):
        raise RuntimeError(reply.get("result") or out.stderr.strip())
    texts = reply.get("structured_output")
    if texts is None:  # fall back to parsing the text result
        raw = reply["result"].strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        texts = json.loads(raw)
    model = ", ".join(sorted(reply.get("modelUsage") or {})) or MODEL
    return texts, model


def generate_one(village, delay, max_attempts=MAX_ATTEMPTS):
    """Return (alert or None, attempts, problems of the last draft, model ids)."""
    lead = lead_minutes(village, delay)
    problems, model = None, MODEL
    for attempt in range(1, max_attempts + 1):
        try:
            texts, model = call_llm(prompt_for(village, lead, problems))
            problems = check_texts(texts.get("text_en"), texts.get("text_ne"), village, lead)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, AttributeError, RuntimeError) as e:
            problems = [f"call failed: {e}"]
            texts = {}
        if not problems:
            return ({"village_id": village["id"], "name_en": village["name_en"], "lead_min": lead,
                     "text_en": texts["text_en"].strip(), "text_ne": texts["text_ne"].strip(),
                     "attempts": attempt}, attempt, [], model)
    return None, max_attempts, problems, model


def cli_version():
    try:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30,
                              env=clean_env()).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def main():
    with open(SCENARIO, encoding="utf-8") as f:
        scenario = json.load(f)
    delay = scenario["alert_delay_min"]
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(lambda v: (v, *generate_one(v, delay)), scenario["villages"]))

    alerts, failed, models = [], [], set()
    for v, alert, attempts, problems, model in results:
        models.update(m.strip() for m in model.split(","))
        if alert:
            alerts.append(alert)
            print(f"  {v['id']:14} ok after {attempts} attempt(s)")
        else:
            failed.append(v["id"])
            print(f"  {v['id']:14} FAILED: {'; '.join(problems)}")

    if failed:
        print(f"not writing {os.path.relpath(OUT, ROOT)}: {len(failed)} village(s) failed; existing file left as is")
        return 1
    doc = {"schema_version": SCHEMA_VERSION, "scenario_event_id": scenario["event"]["id"],
           "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "model": ", ".join(sorted(models)), "generator": f"claude -p ({cli_version()})",
           "alert_delay_min": delay,
           "note": "Machine-generated; the Nepali text has not been reviewed by a native speaker.",
           "alerts": alerts}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}: {len(alerts)} alerts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
