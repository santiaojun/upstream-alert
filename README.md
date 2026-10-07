# Upstream Alert

Cross-border flood warnings from the first upstream signal.

> **Status: work in progress.** All data in this repository is currently placeholder data
> (`"placeholder": true` in `data/scenario.json`). River geometry, village locations and wave speeds
> will be replaced with calibrated values before submission.

Built for **ForgeHacks 2026** (AI + Climate track) during the hackathon period, October 3–10, 2026.

## The problem

On August 26, 2026, a glacier or ice-rock collapse inside Tibet sent a debris flow down the
Lhende Khola and Trishuli valleys into Nepal's Rasuwa district. Global seismic networks recorded
the collapse at 08:37 local time, but the flood started on one side of a border and hit communities
on the other, and no automated alert reached them.

## What this project does

Upstream Alert is a prototype of an upstream-triggered early warning system, demonstrated by
replaying the August 26 event:

1. **Trigger**: detects a collapse-like seismic event near glaciers or headwater rivers.
2. **Routing**: estimates when the flood reaches each downstream village, as a time window
   calibrated against reported arrival times.
3. **Alerts**: an LLM writes short alerts in English and Nepali. All numbers come from the routing
   step, and a validator rejects any alert whose numbers do not match.

It does **not** forecast whether a flood will happen. It turns an upstream signal into
village-level alerts within minutes.

## Repository layout

| Folder | Contents |
|---|---|
| `web/` | Map replay (Leaflet) |
| `data/` | Hand-off files between modules, plus `validate_scenario.py` |
| `pipeline/` | GIS export, calibration, trigger and trigger evaluation |
| `ai/` | Alert generation, validation and evaluation |

## Run locally

```
cd web
python -m http.server 8765
```

Then open http://localhost:8765. Opening the HTML file directly (`file://`) blocks the base map tiles.

Validate the data contract:

```
python data/validate_scenario.py
```

## Team

- Yunhong Huang: AI layer, frontend, integration
- TODO: teammate name and role

## Sources

TODO: list every news report and dataset used, with links.
