# WP8 — 24-hour integration-step sensitivity (unvalidated reference plant)

Three actual CoolProp/IF97 runs of the same nominal synthetic tariff:

| dt (s) | Baseline €/day | Scheduled €/day | Eligible saving €/day | Eligible? | Reasons |
|---:|---:|---:|---:|---|---|
| 60 | 456.845435 | 456.738690 | 0.106745 | yes |  |
| 30 | 456.845436 | 456.738661 | 0.106775 | yes |  |
| 15 | 456.845436 | 456.738660 | 0.106776 | yes |  |

**Numerical screen:** NUMERICAL_SIGNAL_SCREEN_PASSED__NOT_ECONOMIC_VALIDATION.

This is sensitivity to the integration time step only, not a
reliable uncertainty bound for assumed compressor displacement,
efficiency, source/sink flow, pressure envelope, tariff, auxiliaries,
compressor cycling, CAPEX or maintenance costs.
Even a numerically stable positive daily difference does not justify
an investment or real industrial savings claim.
