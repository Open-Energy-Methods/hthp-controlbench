# Audit A01 — WP3 relay-amplitude correction (2026-11-03)

**Research status:** simulation-only; neither a hardware PID calibration nor a
formal robust-stability certificate.

The previous `identify_relay` measured the process temperature at the sampled
hysteresis switch. Such samples are not the limit-cycle temperature extrema.
When thermal inertia and compressor lag are present, the trajectory continues
past the switching threshold before reversing. This biased amplitude low and
the describing-function gain high. The corrected method records every integration
step and measures the half peak-to-peak amplitude in the last five complete
high-to-high relay cycles. It independently checks period and amplitude
stationarity and rejects underresolved cycles.

The describing-function estimate `Ku = 4 d / (pi a)` is still **approximate**:
hysteresis, actuator lags, sample-and-hold and nonlinear plant dynamics mean it
must not be interpreted as a formally identified ultimate gain.

**Evidence/version lineage:** historic WP3–WP5 CSV/PNG/MD outputs were produced
with the old algorithm and must be treated as **legacy L1 benchmark v1**. Their
controller rankings cannot be relabelled as corrected by changing the source.
A follow-up comparison regeneration must use a new `L1_RelayPeak_v2` identifier
and preserve the old data as read-only historical results. WP7/WP8 fixed IMC
controller results are not directly retuned by this change.

**Verification:** `python -m unittest tests.test_wp3` plus existing full suite.
A sampling resolution check compares 10-s and 5-s integration of an otherwise
identical 30-s sampled relay. No independent experimental validation exists.
