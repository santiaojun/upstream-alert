# pipeline/

Owner: data teammate.

GIS export, speed calibration, trigger script and trigger evaluation.
Output: `data/scenario.json`, which must pass `python data/validate_scenario.py` before every push.

Build the scenario from the OpenStreetMap extracts in `osm/` (how to refresh them is in the script's docstring):

```
python pipeline/build_scenario.py
python data/validate_scenario.py
```
