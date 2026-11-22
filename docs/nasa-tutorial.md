# Two NASA-related teaching paths — distinct evidence levels

This repository does not install or run a CFD solver, and it does not contain NASA's proprietary or license-uncertain raw measurements. Its two SWBLI paths are separate cases and separate levels of reproduction.

## Mach 2.05: duct, exported SU2/PIV profiles

Offline, using a **local A09-derived station metric table** (included under MIT as an original analytical reduction):

```sh
cfd-profile-audit nasa --case duct --source derived --plot nasa.svg
```

Expected pooled absolute streamwise velocity errors divided by `U_inf=532 m/s`:

| Station selection | Matched samples/model | SA | SST |
|---|---:|---:|---:|
| Six documented stations (-30,-10,0,10,30,50 mm) | 202 | 0.107263 | 0.101615 |
| All ten exported stations | 348 | 0.093952 | 0.087436 |

The local per-station input table was reduced from `A09_EXTERNAL_DISCOVERY_20261120/out/A09_M205_profile_metrics.csv` (SHA-256 `b1b9d76bd35a85675da33d89448cf7fd83513c8abfcde28b2fa1fb23b978ee85`); the original A09 file contains other metrics and is not reproduced wholesale. This path recomputes the pooled means from *already-derived* station values; it does not recompute those station values from original CSVs.

For an **upstream-exported-data recomputation** (network required; verifies SHA-256 of each downloaded CSV before parsing):

```sh
cfd-profile-audit nasa --case duct --source upstream --plot nasa-from-upstream.svg
```

Pinned source commit: [`ofirnirr/SU2-SWBLI-Mach-2-RANS-Validation@2b2be8c`](https://github.com/ofirnirr/SU2-SWBLI-Mach-2-RANS-Validation/tree/2b2be8c4e982af6e97542237aeaaf9da615707bd). Source file names and expected SHA-256 values live in `src/cfd_profile_audit/nasa.py`. For each station the algorithm matches experimental and computed `U_m_s` on exactly the same rounded `y_mm` (four decimal places), pools pointwise absolute errors and divides by 532. It additionally compares the full-profile preferences from **absolute integrated signed bias** and **integrated absolute error**; these are different metrics. The historical A10 upstream run reported four preference changes across ten stations. If the upstream bytes, format or count differ, treat the result as a reproduction failure and inspect, not as a new physical observation.

**Boundary:** The archived `results/validation` tables are not the original SU2 solver state and do not verify the missing medium-mesh interior construction. The PIV spatial resolution is not sufficient to infer the actual separation length of a very thin reversed-flow layer. Only this exported-data calculation has a path to the three directly published velocity tables; this project does not rerun mesh generation or SU2.

## Mach 2.5: axisymmetric 16° cone, derived A08 window votes

```sh
cfd-profile-audit nasa --case cone --source derived --json
```

This downloads and checks the SHA-256 of the *existing original A08-derived analysis table* from the user's public [SWBLI validation audit](https://github.com/hengyuhang61-creator/aero-propulsion-system-id/tree/main/research/swbli-validation-audit), then groups its **8,208 votes** into **27 station/solver groups**. For each group its reference is the modal `pref_B` vote; it recomputes per-width agreement and averages across the groups. Historical target values for widths 2,3,4,5,6,8 mm are `0.808,0.813,0.805,0.795,0.787,0.747`, respectively.

This is expressly a **derived-data reproduction**, not raw NASA radial/PIV ingestion or solver rerun. Original upstream NASA TMR archives and source hashes are in the [prior published audit](https://github.com/hengyuhang61-creator/aero-propulsion-system-id/blob/main/research/swbli-validation-audit/cone-input-hashes.json). The Mach 2.5 model is **SST-Vm** and cannot be rebranded Mach 2.05 duct **SST**. The full-profile reference definitions differ across cases; the agreement fractions do not form one universal width-vs-error law. A single 16° cone case and one 3 mm duct case offer no statistical confidence interval for a general turbulence-model ranking.

Both network-dependent commands are implemented but must be verified in an Internet-enabled runtime before the project can claim end-to-end upstream reproducibility. Distinguish data-integrity hashes from scientific correctness.
