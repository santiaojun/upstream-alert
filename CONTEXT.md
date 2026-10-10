# Upstream Alert

An upstream-triggered flood warning prototype: it turns a seismic record of an upstream collapse into
per-village alerts downstream, demonstrated by replaying the 26 August 2026 Lende Khola – Trishuli flood.

## Language

**Upstream signal**:
The seismic record of a collapse upstream of the flood path, identified by its USGS event id (for the
replay, `us7000tbwb`).
_Avoid_: Event (alone), earthquake, warning

**Trigger**:
The rule that decides whether an upstream signal looks like a collapse that can send a flood down the
flood path.
_Avoid_: Detector, alarm

**Flood path**:
The single line the flood is assumed to follow, from the upstream signal location down the Lende
Khola, Bhote Koshi and Trishuli to Bidur.
_Avoid_: River (alone), route, corridor

**Arrival window**:
The earliest and latest time the flood can reach a village, in minutes after the upstream signal.
_Avoid_: ETA (alone), countdown, arrival time

**Village**:
A place on the flood path that receives an alert, including towns such as Bidur.
_Avoid_: Settlement, town, community

**Alert**:
The short message one village receives, in English and Nepali, stating its arrival window and what to do.
_Avoid_: Warning, notification, message

**Scenario**:
One replayable upstream signal together with its flood path, villages and arrival windows.
_Avoid_: Case, simulation, run
