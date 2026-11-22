# Third-party data and source notices

- Python implementation, original diagrams, derived A09 station-MAE subset and accompanying documentation in this repository: MIT (see `LICENSE`). The derived table was transcribed from the A09 local original analysis; it is not native NASA experimental data.
- Mach 2.05 SU2/PIV exported velocity tables are **downloaded on demand, not vendored**. Upstream: [ofirnirr/SU2-SWBLI-Mach-2-RANS-Validation](https://github.com/ofirnirr/SU2-SWBLI-Mach-2-RANS-Validation), pinned at `2b2be8c4e982af6e97542237aeaaf9da615707bd`. Refer to that repository, its underlying NASA source, and its data license/conditions before any redistribution. A pinned source hash verifies bytes, not experimental credibility or redistribution permission.
- Mach 2.5 NASA TMR 16° cone uses a separately published *derived analysis vote table*, on demand from [aero-propulsion-system-id SWBLI validation audit](https://github.com/hengyuhang61-creator/aero-propulsion-system-id/tree/main/research/swbli-validation-audit). Original upstream archive citations and input hashes remain there. Native NASA radial fields are not bundled here. Mach 2.5 SST-Vm is not the Mach 2.05 SST dataset.
- NumPy, SciPy, Oberkampf–Barone (2006), Wünsch et al. (2025) and Geifman–El-Yaniv (2019) are referenced, **not copied or modified**. No NumPy/SciPy source is included.

The repository MIT license applies only to original project assets and does **not** relicense upstream measurements, simulations, papers, or images.
