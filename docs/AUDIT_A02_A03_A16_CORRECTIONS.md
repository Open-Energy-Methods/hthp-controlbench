# Audit A02 / A03 / A16 — terminal-energy, off-mode and tariff-accounting fixes

**A02 WP8:** The 24-hour savings eligibility gate now checks the final buffer
IF97 enthalpy, header sensible-energy inventory, their *sum* and compressor
actual modulation / final applied command. Each store has an independent
0.5 kWh equality gate; actual and command modulation must match within 0.02.
Offsetting buffer and header energy differences cannot falsely pass. Raw cost
and electricity differences remain diagnostic even when credit is withheld.
These are predefined **simulation comparability** limits, not calibrated
energy-measurement tolerances. The original WP8 reference comparison finished
at approximately equal header and buffer temperatures; this correction is not
a claim that the legacy €0.11 result was biased.

**A03 WP2:** A disconnected header-buffer (`khb=0`) and heat pump switched off
(`q_hp_rated=0`) remain *valid dynamic off-mode tests*; no energy is magically
added. The **steady equilibrium** algebra explicitly raises ValueError for
these singular cases instead of ZeroDivisionError. `Parameters` rejects NaN,
infinity, negative physical capacities and invalid model bounds.

**A16 WP8:** Tariff electricity buckets are classified from the selected
high/low/regular time intervals, never equality comparisons of floating-point
prices. All three intervals retain their accounting labels under a flat tariff.

Regression checks: deliberately unmatched final header energy (including the
adversarial 7 K/9.72 kWh difference), mismatched compressor modulation,
three identical tariff prices, explicit zero-capacity dynamic operation and
finite-domain validation. No compressor manufacturer or hardware claims.
