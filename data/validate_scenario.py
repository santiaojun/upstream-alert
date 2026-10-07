"""Validate data/scenario.json against the agreed contract (schema_version 1.0).

Usage:  python data/validate_scenario.py [path]      (default: data/scenario.json)
Exit code 0 = valid, 1 = invalid. No third-party packages needed.
"""
import json
import math
import re
import sys

SCHEMA_VERSION = "1.0"
ISO_NPT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:45$")  # Nepal time only
ID_RE = re.compile(r"^[a-z0-9-]+$")
# Rough bounding box for the study area (lon, lat). Catches swapped lat/lon and wrong CRS.
LON_RANGE, LAT_RANGE = (84.0, 87.0), (27.0, 29.5)
ETA_TOLERANCE_MIN = 2  # eta_min must match dist_km / speed within this many minutes

errors = []


def err(path, msg):
    errors.append(f"{path}: {msg}")


def check_type(obj, key, types, path, required=True):
    if key not in obj:
        if required:
            err(path, f"missing required field '{key}'")
        return None
    val = obj[key]
    if isinstance(val, bool) and bool not in (types if isinstance(types, tuple) else (types,)):
        err(f"{path}.{key}", f"expected {types}, got bool")
        return None
    if not isinstance(val, types):
        err(f"{path}.{key}", f"expected {types}, got {type(val).__name__}")
        return None
    return val


def check_point(obj, path):
    lon = check_type(obj, "lon", (int, float), path)
    lat = check_type(obj, "lat", (int, float), path)
    if lon is not None and not LON_RANGE[0] <= lon <= LON_RANGE[1]:
        err(f"{path}.lon", f"{lon} outside study area {LON_RANGE} (swapped lat/lon? not WGS84?)")
    if lat is not None and not LAT_RANGE[0] <= lat <= LAT_RANGE[1]:
        err(f"{path}.lat", f"{lat} outside study area {LAT_RANGE} (swapped lat/lon? not WGS84?)")


def haversine_km(a, b):
    r = 6371.0
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dla, dlo = la2 - la1, math.radians(b[0] - a[0])
    x = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def validate(d):
    if d.get("schema_version") != SCHEMA_VERSION:
        err("schema_version", f"expected '{SCHEMA_VERSION}', got {d.get('schema_version')!r}")
    check_type(d, "placeholder", bool, "root")

    # event
    ev = check_type(d, "event", dict, "root")
    if ev:
        for k in ("id", "label_en", "source"):
            check_type(ev, k, str, "event")
        t = check_type(ev, "time", str, "event")
        if t and not ISO_NPT.match(t):
            err("event.time", f"{t!r} must be ISO 8601 with +05:45 offset")
        check_type(ev, "mag", (int, float), "event")
        check_point(ev, "event")

    # speed
    sp = check_type(d, "speed_kmh", dict, "root")
    low = high = None
    if sp:
        low = check_type(sp, "low", (int, float), "speed_kmh")
        high = check_type(sp, "high", (int, float), "speed_kmh")
        check_type(sp, "method", str, "speed_kmh")
        if low is not None and high is not None and not 0 < low <= high:
            err("speed_kmh", f"need 0 < low <= high, got low={low}, high={high}")
            low = high = None

    delay = check_type(d, "alert_delay_min", (int, float), "root")
    if delay is not None and delay < 0:
        err("alert_delay_min", "must be >= 0")

    # calibration points
    cps = check_type(d, "calibration_points", list, "root")
    for i, cp in enumerate(cps or []):
        p = f"calibration_points[{i}]"
        if not isinstance(cp, dict):
            err(p, "must be an object")
            continue
        for k in ("name", "source"):
            check_type(cp, k, str, p)
        t = check_type(cp, "observed_time", str, p)
        if t and not ISO_NPT.match(t):
            err(f"{p}.observed_time", f"{t!r} must be ISO 8601 with +05:45 offset")
        check_type(cp, "dist_km", (int, float), p)

    # river
    river_km = None
    rv = check_type(d, "river", dict, "root")
    if rv:
        if rv.get("type") != "Feature":
            err("river.type", "must be 'Feature'")
        geom = rv.get("geometry") or {}
        coords = geom.get("coordinates")
        if geom.get("type") != "LineString":
            err("river.geometry.type", "must be 'LineString'")
        elif not isinstance(coords, list) or len(coords) < 2:
            err("river.geometry.coordinates", "need at least 2 [lon, lat] points")
        else:
            for i, c in enumerate(coords):
                if not (isinstance(c, list) and len(c) >= 2):
                    err(f"river.coordinates[{i}]", "must be [lon, lat]")
                    break
                check_point({"lon": c[0], "lat": c[1]}, f"river.coordinates[{i}]")
            else:
                river_km = sum(haversine_km(coords[i - 1], coords[i]) for i in range(1, len(coords)))
                if ev and "lon" in ev and "lat" in ev:
                    if haversine_km(coords[0], [ev["lon"], ev["lat"]]) > haversine_km(coords[-1], [ev["lon"], ev["lat"]]):
                        err("river.coordinates", "line looks reversed: first point must be the upstream source")

    # villages
    vs = check_type(d, "villages", list, "root")
    seen, prev = set(), -1.0
    for i, v in enumerate(vs or []):
        p = f"villages[{i}]"
        if not isinstance(v, dict):
            err(p, "must be an object")
            continue
        vid = check_type(v, "id", str, p)
        if vid:
            if not ID_RE.match(vid):
                err(f"{p}.id", f"{vid!r} must be lowercase letters, digits, hyphens")
            if vid in seen:
                err(f"{p}.id", f"duplicate id {vid!r}")
            seen.add(vid)
        check_type(v, "name_en", str, p)
        check_point(v, p)
        dist = check_type(v, "dist_km", (int, float), p)
        if dist is not None:
            if dist < 0:
                err(f"{p}.dist_km", "must be >= 0")
            if river_km is not None and dist > river_km * 1.05:
                err(f"{p}.dist_km", f"{dist} exceeds river length {river_km:.1f} km")
            if dist < prev:
                err(f"{p}.dist_km", "villages must be sorted upstream to downstream")
            prev = dist
        eta = check_type(v, "eta_min", list, p)
        if eta is not None:
            if len(eta) != 2 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in eta):
                err(f"{p}.eta_min", "must be [earliest, latest] numbers")
            elif eta[0] > eta[1]:
                err(f"{p}.eta_min", "earliest must be <= latest")
            elif dist is not None and low and high:
                exp = (dist / high * 60, dist / low * 60)
                if abs(eta[0] - exp[0]) > ETA_TOLERANCE_MIN or abs(eta[1] - exp[1]) > ETA_TOLERANCE_MIN:
                    err(f"{p}.eta_min", f"{eta} inconsistent with dist_km/speed, expected about "
                                       f"[{exp[0]:.0f}, {exp[1]:.0f}]")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/scenario.json"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read {path}: {e}")
        return 1
    if not isinstance(data, dict):
        print("FAIL: root must be a JSON object")
        return 1
    validate(data)
    if errors:
        print(f"FAIL: {len(errors)} problem(s) in {path}")
        for e in errors:
            print("  -", e)
        return 1
    note = " (placeholder data)" if data.get("placeholder") else ""
    print(f"OK: {path} matches schema {SCHEMA_VERSION}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
