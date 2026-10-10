# ai/

Owner: Yunhong.

Reads `data/scenario.json`, generates English and Nepali alerts with an LLM, validates every number
against the pipeline output, and writes `data/alerts.json`. Includes the evaluation script.

## Run

Needs the Claude Code CLI (`claude`), logged in. The scripts call `claude -p` with tools, skills,
plugins and hooks switched off, so they run on the caller's Claude account.

```
python ai/generate_alerts.py      # writes data/alerts.json only if every village's alert passes
python ai/validate_alerts.py      # checks data/alerts.json against data/scenario.json
python ai/evaluate_alerts.py 5    # 5 rounds of first drafts per village -> ai/eval_results.json
```

## How numbers stay correct

The pipeline computes each village's lead time: its arrival window minus `alert_delay_min`, in
minutes from when the alert is sent. The LLM only words the message. `validate_alerts.py` rejects a
draft unless both texts contain exactly those two numbers as digits (Devanagari digits count) and no
other number, and name the village in English and Nepali. A rejected draft is regenerated with the
problems fed back, up to 3 attempts.

## data/alerts.json (schema_version 1.0)

```
{
  "schema_version": "1.0",
  "scenario_event_id": "us7000tbwb",          // must match scenario event.id
  "generated_at": "...", "model": "...", "generator": "claude -p (...)",
  "alert_delay_min": 1,
  "note": "Machine-generated; the Nepali text has not been reviewed by a native speaker.",
  "alerts": [
    { "village_id": "syabru-bensi", "name_en": "Syabru Bensi",
      "lead_min": [38, 64],                    // eta_min minus alert_delay_min
      "text_en": "...", "text_ne": "...", "attempts": 1 }
  ]
}
```

The Nepali alerts are machine-generated and have not been reviewed by a native speaker.
