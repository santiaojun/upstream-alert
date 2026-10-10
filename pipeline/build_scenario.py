"""Build data/scenario.json for the 26 Aug 2026 replay from OpenStreetMap and the USGS upstream signal.

Usage:  python pipeline/build_scenario.py       then  python data/validate_scenario.py
No third-party packages needed.

Inputs are OpenStreetMap extracts in pipeline/osm/, committed so the build is reproducible.
To refresh them (run from the repo root):
  curl -s https://overpass-api.de/api/interpreter --data-urlencode \
    'data=[out:json][timeout:150];way["waterway"="river"](27.85,85.10,28.45,85.60);out body geom;' \
    -o pipeline/osm/corridor.json
  curl -s https://overpass-api.de/api/interpreter --data-urlencode \
    'data=[out:json][timeout:60];node["place"~"village|town|hamlet|city|suburb|locality"](27.85,85.10,28.45,85.55);out;' \
    -o pipeline/osm/places.json

Method:
  1. Keep the river ways named Lende Khola, Bhote Koshi or Trishuli and build a node graph.
  2. Flood path = shortest path from the Lende Khola node nearest the upstream signal down to Bidur.
     The signal is not on a mapped river, so the path starts with a straight-line leg from the
     signal location to that node, standing in for an unmapped tributary.
  3. Snap each village to its nearest flood path vertex; distance along the path = dist_km.
  4. One constant speed band, calibrated so the flood reaches Rasuwa Gadhi between 09:00
     (Borderlens) and 09:15 (Nepal Red Cross) after the 08:37:10 upstream signal.
  5. Sensitivity: the same arrival windows without the straight-line leg (*_no_offset fields).
"""
import heapq
import json
import math
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSM_DIR = os.path.join(ROOT, "pipeline", "osm")
OUT = os.path.join(ROOT, "data", "scenario.json")

# USGS us7000tbwb: 02:52:10 UTC = 08:37:10 Nepal time (UTC+5:45).
EVENT = {"id": "us7000tbwb", "lat": 28.271, "lon": 85.515, "mag": 5.2, "time": "2026-08-26T08:37:10+05:45"}
PATH_END = (27.88, 85.14)  # just downstream of Bidur (Trishuli Bazaar)
NAME_RE = re.compile(r"Lende|东林|Bhote Koshi|भोटे कोशी|Trishuli", re.I)
# Villages named in news reports as hit, by their OSM names.
VILLAGES = ["Rasuwa Gadhi", "Timure", "Syabru Bensi", "Haku Besi", "Mailung",
            "Shanti Bazar", "Betrawati", "Bidur"]
MAX_OFF_PATH_KM = 1.0
SIGNAL_MIN = 8 * 60 + 37 + 10 / 60
ENTRY_MIN_FAST, ENTRY_MIN_SLOW = 9 * 60 - SIGNAL_MIN, 9 * 60 + 15 - SIGNAL_MIN


def hav_km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def name_of(tags):
    return tags.get("name:en") or tags.get("name", "")


def load(name):
    with open(os.path.join(OSM_DIR, name), encoding="utf-8") as f:
        return json.load(f)["elements"]


ways = [e for e in load("corridor.json")
        if e["type"] == "way" and (NAME_RE.search(e["tags"].get("name", "")) or NAME_RE.search(e["tags"].get("name:en", "")))]
coord, graph = {}, {}
for w in ways:
    for nid, g in zip(w["nodes"], w["geometry"]):
        coord[nid] = (g["lat"], g["lon"])
    for a, b in zip(w["nodes"], w["nodes"][1:]):
        d = hav_km(coord[a], coord[b])
        graph.setdefault(a, []).append((b, d))
        graph.setdefault(b, []).append((a, d))


def nearest(pt, nodes):
    return min(nodes, key=lambda n: hav_km(pt, coord[n]))


signal = (EVENT["lat"], EVENT["lon"])
lende_nodes = {n for w in ways if "Lende" in name_of(w["tags"]) or "东林" in w["tags"].get("name", "") for n in w["nodes"]}
start = nearest(signal, lende_nodes)
end = nearest(PATH_END, coord)

# Dijkstra from the Lende Khola start node to Bidur.
dist, prev, pq = {start: 0.0}, {}, [(0.0, start)]
while pq:
    d, n = heapq.heappop(pq)
    if n == end:
        break
    if d > dist[n]:
        continue
    for m, w in graph.get(n, []):
        if d + w < dist.get(m, math.inf):
            dist[m], prev[m] = d + w, n
            heapq.heappush(pq, (d + w, m))
if end not in dist:
    raise SystemExit("river ways are not connected between the upstream signal and Bidur; bridge the gap manually")

path = [end]
while path[-1] != start:
    path.append(prev[path[-1]])
path.reverse()
cum = [0.0]
for a, b in zip(path, path[1:]):
    cum.append(cum[-1] + hav_km(coord[a], coord[b]))
leg_km = hav_km(signal, coord[start])

places = {name_of(e["tags"]): e for e in load("places.json")}
villages = []
for v in VILLAGES:
    p = places[v]
    pt = (p["lat"], p["lon"])
    i = min(range(len(path)), key=lambda k: hav_km(pt, coord[path[k]]))
    villages.append({"id": re.sub(r"[^a-z0-9]+", "-", v.lower()), "name_en": v, "name_ne": p["tags"].get("name", ""),
                     "lon": round(p["lon"], 5), "lat": round(p["lat"], 5),
                     "dist_km": round(leg_km + cum[i], 1), "dist_km_no_offset": round(cum[i], 1),
                     "off_path_km": round(hav_km(pt, coord[path[i]]), 2), "osm_id": f"node/{p['id']}"})
villages.sort(key=lambda v: v["dist_km"])
border = next(v for v in villages if v["name_en"] == "Rasuwa Gadhi")


def speed_band(border_km):
    return round(border_km / (ENTRY_MIN_SLOW / 60), 1), round(border_km / (ENTRY_MIN_FAST / 60), 1)


def arrival_window(km, low, high):
    return [round(km / high * 60), round(km / low * 60)]


low, high = speed_band(border["dist_km"])
low0, high0 = speed_band(border["dist_km_no_offset"])
for v in villages:
    v["eta_min"] = arrival_window(v["dist_km"], low, high)
    v["eta_min_no_offset"] = arrival_window(v["dist_km_no_offset"], low0, high0)

scenario = {
    "schema_version": "1.0",
    "placeholder": False,
    "event": {**EVENT, "label_en": "Upstream glacier/ice-rock collapse signal (USGS event type: landslide)",
              "snapped_to_river": {"lat": coord[start][0], "lon": coord[start][1], "offset_km": round(leg_km, 2)},
              "location_note": "USGS locations for landslide seismic sources are approximate. The signal is "
                               f"{leg_km:.1f} km from the nearest mapped Lende Khola point; the flood path bridges "
                               "this with a straight-line leg standing in for an unmapped tributary.",
              "source": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000tbwb"},
    "speed_kmh": {"low": low, "high": high,
                  "method": "constant speed; Rasuwa Gadhi distance / (09:15 or 09:00 entry - 08:37:10 upstream signal)"},
    "sensitivity": {"no_offset_speed_kmh": {"low": low0, "high": high0},
                    "note": "*_no_offset fields assume the flood starts at the Lende Khola, not at the upstream "
                            "signal. This is the largest uncertainty in downstream arrival windows."},
    "alert_delay_min": 1,
    "calibration_points": [{"name": "Nepal border entry (Rasuwa Gadhi)",
                            "observed_time": "2026-08-26T09:00:00+05:45",
                            "observed_time_window": ["2026-08-26T09:00:00+05:45", "2026-08-26T09:15:00+05:45"],
                            "dist_km": border["dist_km"],
                            "note": "used to calibrate speed_kmh, so not an independent check",
                            "source": "Borderlens 2026-08-26 ('around 9 a.m.'); Nepal Red Cross Society situation "
                                      "update 2026-08-26 ('approximately 9:15 AM')"}],
    "river": {"type": "Feature",
              "properties": {"name": "Lende Khola - Bhote Koshi - Trishuli", "length_km": round(leg_km + cum[-1], 1),
                             "first_segment": "straight-line leg from the upstream signal to the Lende Khola (approximation)",
                             "source": "OpenStreetMap contributors (ODbL), via Overpass API"},
              "geometry": {"type": "LineString",
                           "coordinates": [[EVENT["lon"], EVENT["lat"]]] +
                                          [[round(coord[n][1], 5), round(coord[n][0], 5)] for n in path]}},
    "villages": villages,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(scenario, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(f"wrote {os.path.relpath(OUT, ROOT)}: flood path {leg_km + cum[-1]:.1f} km ({leg_km:.1f} km straight-line leg), "
      f"speed {low}-{high} km/h (no offset {low0}-{high0})")
for v in villages:
    flag = "  <-- far from flood path?" if v["off_path_km"] > MAX_OFF_PATH_KM else ""
    print(f"  {v['id']:14} {v['dist_km']:6.1f} km  window {v['eta_min']}  no-offset {v['eta_min_no_offset']}{flag}")
