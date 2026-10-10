"""Trigger rule and its evaluation against ten years of the USGS catalogue.

Usage:  python pipeline/trigger.py      prints the evaluation as Markdown tables
No third-party packages needed.

Trigger: an upstream signal of magnitude >= MIN_MAG within MAX_DIST_KM of the watch zone fires.
The watch zone is the mapped Lende Khola in Tibet (from pipeline/osm/corridor.json), the part
of the flood path upstream of the border. It does not use the USGS "landslide" label: USGS
assigns that only after review, and in real time the 26 Aug signal first appeared as an earthquake.

Ground truth: an event is a true collapse if USGS later typed it "landslide". Only the two
26 Aug 2026 events are, so this measures false alarms, not missed collapses.

Input: pipeline/usgs/catalog.json, committed so the evaluation is reproducible. To refresh it:
  curl -s 'https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minlatitude=27.8&maxlatitude=28.9&minlongitude=84.8&maxlongitude=86.0&minmagnitude=4&starttime=2015-01-01&endtime=2026-10-09' \
    -o pipeline/usgs/catalog.json
"""
import datetime as dt
import json
import math
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_MAG = 4.0
MAX_DIST_KM = 30
EVAL_START = dt.datetime(2016, 1, 1, tzinfo=dt.timezone.utc)  # 2015 is reported separately (Gorkha aftershocks)
CATALOG_END = "2026-10-09"  # endtime of the catalogue query above
NPT = dt.timezone(dt.timedelta(hours=5, minutes=45))


def hav_km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def load_json(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def watch_zone():
    """(lat, lon) vertices of the mapped Lende Khola."""
    lende = re.compile(r"Lende|东林")
    return [(g["lat"], g["lon"]) for e in load_json("pipeline", "osm", "corridor.json")["elements"]
            if e["type"] == "way" and (lende.search(e["tags"].get("name", "")) or lende.search(e["tags"].get("name:en", "")))
            for g in e["geometry"]]


def dist_to_zone_km(event, zone):
    lon, lat = event["geometry"]["coordinates"][:2]
    return min(hav_km((lat, lon), z) for z in zone)


def fires(event, zone, min_mag=MIN_MAG, max_dist_km=MAX_DIST_KM, max_depth_km=None):
    mag, depth = event["properties"]["mag"], event["geometry"]["coordinates"][2]
    return (mag is not None and mag >= min_mag and dist_to_zone_km(event, zone) <= max_dist_km
            and (max_depth_km is None or depth <= max_depth_km))


def when(event):
    return dt.datetime.fromtimestamp(event["properties"]["time"] / 1000, dt.timezone.utc)


def is_collapse(event):
    return event["properties"]["type"] == "landslide"


def main():
    zone = watch_zone()
    catalog = load_json("pipeline", "usgs", "catalog.json")["features"]
    period = [e for e in catalog if when(e) >= EVAL_START]

    print(f"Rule: M >= {MIN_MAG} within {MAX_DIST_KM} km of the mapped Lende Khola. "
          f"Period {EVAL_START.date()} to {CATALOG_END}, {len(period)} USGS events M >= 4 in the search box.\n")
    print("| Date (Nepal time) | Mag | Depth (km) | Distance to watch zone (km) | USGS type | Result |")
    print("|---|---|---|---|---|---|")
    for e in sorted((e for e in period if fires(e, zone)), key=when):
        p, c = e["properties"], e["geometry"]["coordinates"]
        result = "hit" if is_collapse(e) else "false alarm"
        print(f"| {when(e).astimezone(NPT):%Y-%m-%d %H:%M} | {p['mag']} | {c[2]:.0f} | {dist_to_zone_km(e, zone):.1f} "
              f"| {p['type']} | {result} |")

    print("\nSensitivity to the rule's parameters (same period, M >= 4):\n")
    print("| Radius (km) | Depth filter | Alarms | Hits | False alarms |")
    print("|---|---|---|---|---|")
    for radius in (10, 20, 30, 50):
        for depth in (None, 10):
            hits = [e for e in period if fires(e, zone, max_dist_km=radius, max_depth_km=depth)]
            n_true = sum(map(is_collapse, hits))
            label = "none" if depth is None else f"<= {depth} km"
            print(f"| {radius} | {label} | {len(hits)} | {n_true} | {len(hits) - n_true} |")

    y2015 = [e for e in catalog if when(e).year == 2015 and fires(e, zone)]
    print(f"\n2015 (Gorkha earthquake aftershocks), main rule: {len(y2015)} alarms.")


if __name__ == "__main__":
    main()
