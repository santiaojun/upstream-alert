"""Evaluate the alert generator: how often the LLM's first draft is right, before any regeneration.

Usage:  python ai/evaluate_alerts.py [rounds]      (default 5 rounds x every village)
Writes ai/eval_results.json and prints a Markdown summary. Uses the same `claude -p` calls
as ai/generate_alerts.py, so it needs the Claude Code CLI, logged in.
"""
import concurrent.futures
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_alerts import MODEL, SCENARIO, WORKERS, cli_version, generate_one  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ai", "eval_results.json")


def share(n, total):
    return f"{n}/{total} ({100 * n / total:.0f}%)" if total else "0/0"


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    with open(SCENARIO, encoding="utf-8") as f:
        scenario = json.load(f)
    delay = scenario["alert_delay_min"]
    jobs = [(r, v) for r in range(1, rounds + 1) for v in scenario["villages"]]

    def run(job):
        r, v = job
        alert, _, problems, model = generate_one(v, delay, max_attempts=1)
        return {"round": r, "village_id": v["id"], "passed": alert is not None, "problems": problems,
                "model": model, "text_en": alert and alert["text_en"], "text_ne": alert and alert["text_ne"]}

    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        drafts = list(pool.map(run, jobs))

    answered = [d for d in drafts if not any(p.startswith("call failed") for p in d["problems"])]
    numbers_ok = sum(not any("numbers" in p for p in d["problems"]) for d in answered)
    names_ok = sum(not any("does not name" in p for p in d["problems"]) for d in answered)
    passed = sum(d["passed"] for d in answered)
    summary = {"rounds": rounds, "villages": len(scenario["villages"]), "drafts": len(drafts),
               "call_failures": len(drafts) - len(answered), "numbers_correct": numbers_ok,
               "names_correct": names_ok, "first_try_passed": passed}
    doc = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "model": ", ".join(sorted({d["model"] for d in drafts})) or MODEL,
           "generator": f"claude -p ({cli_version()})", "summary": summary, "drafts": drafts}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    n = len(answered)
    print(f"{rounds} rounds x {len(scenario['villages'])} villages = {len(drafts)} first drafts "
          f"({summary['call_failures']} failed calls excluded), model {doc['model']}\n")
    print("| Check | First drafts that pass |")
    print("|---|---|")
    print(f"| Both lead times correct, no other numbers (English and Nepali) | {share(numbers_ok, n)} |")
    print(f"| Village named in English and Nepali | {share(names_ok, n)} |")
    print(f"| All checks (passes the validator on the first try) | {share(passed, n)} |")
    for d in drafts:
        if d["problems"]:
            print(f"  round {d['round']} {d['village_id']}: {'; '.join(d['problems'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
