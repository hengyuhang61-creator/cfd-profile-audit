# Research foundations and evidence boundaries

This is a support-domain **audit**, not a new validation metric or physical theory. The core decision is to separate (i) a numeric discrepancy computed on supported reference samples from (ii) the extent to which the intended reference profile is actually evaluated. Sources checked on **2026-11-22**; links should be revisited when APIs or evidence change.

## Interpolation is not the bug

**NumPy, [`numpy.interp`](https://numpy.org/doc/stable/reference/generated/numpy.interp.html).** Its documented, intentional default is endpoint fill: when `x < xp[0]`, it returns `fp[0]` unless `left` is supplied; for `x > xp[-1]`, it returns `fp[-1]` unless `right` is supplied. It expects increasing `xp`, warns that this order is not explicitly enforced, and `xp` cannot contain NaNs. Interpolating *within* valid adjacent computed samples is mathematically legitimate. The audit problem arises when a user silently treats endpoint-filled values as **computed CFD support** and reports a misleading all-reference RMSE. The 21/13 plateau illustration deliberately reproduces this baseline; it does **not** claim a NumPy defect.

**SciPy, [`scipy.interpolate.interp1d`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.interp1d.html) and [extrapolation guide](https://docs.scipy.org/doc/scipy/tutorial/interpolate/extrapolation_examples.html).** `interp1d` is documented as *legacy*; by default it raises for out-of-bounds queries unless extrapolation is configured. `bounds_error=False` plus `fill_value` can define missing value behavior; `fill_value='extrapolate'` explicitly permits extrapolation. Non-unique inputs and NaNs have undefined behavior in `interp1d`. SciPy's extrapolation policies differ across interpolator classes. This utility deliberately implements no extrapolation or automatic clamping in the audited comparison. The `demo` baseline alone uses clamping, explicitly labeled misleading.

**Engineering rule applied here:** reject nonfinite values and duplicate coordinates; require ascending order unless `--sort` is explicit. By default, linearly interpolate only within computed coordinate bounds; `--max-gap` rejects interior queries across oversized computed intervals. Even a fully supported convex-hull comparison does *not* prove adequate mesh resolution, physical fidelity, or experimental representativeness.

## Validation metrics and uncertainty

**Oberkampf, W. L., & Barone, M. F. (2006).** “Measures of agreement between computation and experiment: Validation metrics.” *Journal of Computational Physics*, **217**(1), 5–36. DOI: [10.1016/j.jcp.2006.03.037](https://doi.org/10.1016/j.jcp.2006.03.037). The [original article text](https://www.inscc.utah.edu/~spinti/Public/Oberkamp%26Barone_2006.pdf) was inspected on 2026-11-22, including its introduction and §§3, 5–6. It develops validation metrics tied to experimental uncertainty; §5 addresses experimental-data interpolation when observations are sufficiently dense, and §6 addresses regression when data are sparse. §3 explicitly separates a measure of agreement from the *application-dependent adequacy/accuracy requirement*. Accordingly, the CLI's `--max-rmse` is a **user-chosen policy threshold**, not a threshold prescribed by that paper; a `PASS` is not proof of physical-model validity. The [Sandia record](https://www.sandia.gov/research/publications/details/measures-of-agreement-between-computation-and-experiment-validation-metrics-2006-09-01/) and article were checked rather than extrapolating from the title. **This paper does not establish this project's 13/21 coverage ratio, its support definition or its full-domain gating rule.** Those are explicit conservative software protocol choices. Full uncertainty modeling is outside v0.1.

## Undefined outputs and domain coverage are distinct questions

**Wünsch, M., Herrmann, M., Noltenius, E., Mohr, M., Morris, T. P., & Boulesteix, A.-L. (2025).** “Rethinking the Handling of Method Failure in Comparison Studies.” *Statistics in Medicine*, **44**(23–24), e70257. DOI: [10.1002/sim.70257](https://doi.org/10.1002/sim.70257). The [full text](https://onlinelibrary.wiley.com/doi/10.1002/sim.70257) differentiates a method failing to produce output from ordinary missing values; it warns that deleting failed cases or imputing results often biases comparative studies and advocates clear reporting and context-dependent fallback strategies. Transferable principle: avoid silently dropping unevaluable cases, report what was excluded, and define the comparison population. **Difference:** a spatially unsupported CFD sample is not necessarily a statistical method failure, and no fallback value can be interpreted as a CFD solution merely because a statistical benchmark might use fallbacks.

**Geifman, Y., & El-Yaniv, R. (2019).** “SelectiveNet: A Deep Neural Network with an Integrated Reject Option.” *Proceedings of ICML*, PMLR 97:2151–2159. [Primary proceedings page](https://proceedings.mlr.press/v97/geifman19a.html). The paper trains a deep network with prediction and reject behavior and studies a risk–coverage trade-off over accepted predictions. Transferable principle: report loss jointly with how much is admitted. **Difference:** its coverage is a fraction of predictions accepted by a learned selective system, not the spatial fraction of CFD points within a numerical support domain. There is no common theorem or calibrated probability connecting these definitions here.

## Formal definitions used by this program

For ordered, unique, finite reference samples \(R=\{(y_i,u_i)\}_{i=1}^{N}\) and computed samples \(C=\{(z_j,v_j)\}_{j=1}^{M}\), define \(S\) as the union of permitted segments \([z_j,z_{j+1}]\), plus the exact computed nodes. A segment is permitted by default; with `--max-gap G`, only lengths at most \(G\) are permitted. This definition is a *numerical support proxy*, not proof of good CFD resolution.

Let \(I=\{i : y_i \in S\}\). Then

\[
C_{\mathrm{sample}} = |I| / N,\qquad
\mathrm{MAE}_{I} = \frac{1}{|I|}\sum_{i\in I}|\hat u(y_i)-u_i|,\qquad
\mathrm{RMSE}_{I}=\sqrt{\frac{1}{|I|}\sum_{i\in I}(\hat u(y_i)-u_i)^2}.
\]

No overlap means the errors are `null`, not zero. For \(N=1\), the interval-length coverage is undefined (`null`). For a nonzero reference span, separately report \(C_{\mathrm{length}}=\operatorname{length}(S\cap[y_1,y_N])/(y_N-y_1)\); its denominator is length rather than sample count. `full_domain_eligible` means every reference **sample** is supported, not that the entire continuous physical domain or uncertainty has been validated.

`--mode strict` refuses full-domain PASS on partial coverage. `--mode overlap` reports a conditional error while visibly marking the comparison as overlap-only. A full-domain `PASS` needs an explicit `--max-rmse` threshold; coverage alone is not physical validation. A low overlap error is never automatically a success on omitted points. Units must be explicitly supplied for machine-checkable compatibility; an explicit coordinate scale, not implicit guessing, is required for any conversion. Different observation windows, reference grids, or populations are not automatically commensurate.

## Existing software considered

The following were checked as *design precedents*, not dependencies: [Ruff](https://github.com/astral-sh/ruff) (README-first proof of value and installation), [Pandera](https://github.com/unionai-oss/pandera) (schema failures and copyable input examples), [Pydantic](https://github.com/pydantic/pydantic) (small minimal example), [Hypothesis](https://github.com/HypothesisWorks/hypothesis) (shrinking counterexample motivation), [CFDverify](https://github.com/ORNL/cfd-verify) (separate V&V theory, tests and limitations), and [cfd-vv-suite](https://github.com/vvp-cfd/cfd-vv-suite) (CFD comparison interface and the 1D `np.interp` use in `tools/cfdvv/compare.py`). Representative README files and the latter comparison implementation were read; **there has been no exhaustive source or issue audit**. This project adds only a small CSV parser, support calculation, SVG and NASA teaching adapter, not a new CFD validation platform.
