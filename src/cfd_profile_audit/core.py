"""One-dimensional CFD profile coverage: standard library, no implicit extrapolation.

This is a small independent implementation of the support-domain audit demonstrated
in A09/A10. It does not reuse or modify a third-party interpolation implementation.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass
import csv
from math import isfinite, sqrt
from pathlib import Path
from typing import Sequence


class ProfileError(ValueError):
    """Invalid or scientifically incomparable input."""


@dataclass(frozen=True)
class Profile:
    x: tuple[float, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.x or len(self.x) != len(self.values):
            raise ProfileError("profile must have matching, nonempty coordinate and value arrays")
        if any(not isfinite(v) for v in (*self.x, *self.values)):
            raise ProfileError("NaN and infinite coordinates/fields are not allowed")
        if any(b <= a for a, b in zip(self.x, self.x[1:])):
            raise ProfileError("coordinates must be strictly increasing (no duplicates)")


def load_csv(path: str | Path, coordinate: str, field: str, *, sort: bool = False) -> Profile:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or coordinate not in reader.fieldnames or field not in reader.fieldnames:
            raise ProfileError(f"CSV requires named columns {coordinate!r} and {field!r}")
        if coordinate == field:
            raise ProfileError("coordinate and field must be different columns")
        rows: list[tuple[float, float]] = []
        for line, row in enumerate(reader, start=2):
            try:
                x, value = float(row[coordinate]), float(row[field])
            except (TypeError, ValueError) as exc:
                raise ProfileError(f"invalid numeric cell in {path} at line {line}") from exc
            if not isfinite(x) or not isfinite(value):
                raise ProfileError(f"non-finite cell in {path} at line {line}")
            rows.append((x, value))
    if sort:
        rows.sort(key=lambda r: r[0])
    try:
        return Profile(tuple(r[0] for r in rows), tuple(r[1] for r in rows))
    except ProfileError as exc:
        raise ProfileError(f"{path}: {exc}; use --sort to reorder unsorted input") from exc


def sample(computed: Profile, x: float, max_gap: float | None = None) -> float | None:
    """Value only when supported by an exact node or an allowed interior segment.

    Max gap is in the reference coordinate units; a gap larger than it excludes
    interior query locations but retains exact computed nodes.
    """
    j = bisect_left(computed.x, x)
    if j < len(computed.x) and computed.x[j] == x:
        return computed.values[j]
    if j == 0 or j == len(computed.x):
        return None
    lo, hi = computed.x[j - 1], computed.x[j]
    if max_gap is not None and hi - lo > max_gap:
        return None
    t = (x - lo) / (hi - lo)
    return computed.values[j - 1] + t * (computed.values[j] - computed.values[j - 1])


def clamped_sample(computed: Profile, x: float) -> float:
    """Intentional baseline reproducing NumPy interp's default endpoint behavior."""
    v = sample(computed, x)
    if v is not None:
        return v
    return computed.values[0] if x < computed.x[0] else computed.values[-1]


def _interval_fraction(ref: Profile, computed: Profile, max_gap: float | None) -> float | None:
    ref_length = ref.x[-1] - ref.x[0]
    if ref_length == 0:
        return None
    length = 0.0
    for left, right in zip(computed.x, computed.x[1:]):
        if max_gap is not None and right - left > max_gap:
            continue
        length += max(0.0, min(right, ref.x[-1]) - max(left, ref.x[0]))
    return min(1.0, length / ref_length)


def audit(ref: Profile, computed: Profile, *, mode: str = "strict",
          max_gap: float | None = None, max_rmse: float | None = None) -> dict:
    if mode not in ("strict", "overlap"):
        raise ProfileError("mode must be 'strict' or 'overlap'")
    if max_gap is not None and (not isfinite(max_gap) or max_gap <= 0):
        raise ProfileError("max_gap must be positive and finite")
    if max_rmse is not None and (not isfinite(max_rmse) or max_rmse < 0):
        raise ProfileError("max_rmse must be nonnegative and finite")
    overlap_min = max(ref.x[0], computed.x[0])
    overlap_max = min(ref.x[-1], computed.x[-1])
    paired = [(x, value, v) for x, value in zip(ref.x, ref.values)
              if (v := sample(computed, x, max_gap)) is not None]
    n = len(paired)
    errors = [computed_value - reference_value for _, reference_value, computed_value in paired]
    full = n == len(ref.x)
    if not n:
        verdict = "NOT_EVALUABLE"
    elif not full and mode == "strict":
        verdict = "FAIL_INCOMPLETE_SUPPORT"
    elif not full:
        verdict = "OVERLAP_ONLY"
    elif max_rmse is None:
        verdict = "FULL_COVERAGE_NO_THRESHOLD"
    else:
        verdict = "PASS" if sqrt(sum(v*v for v in errors) / n) <= max_rmse else "FAIL_RMSE"
    messages = []
    if not full:
        messages.append("Incomplete support: reported errors are conditional on supported reference samples, not full-domain errors.")
    if max_gap is None:
        messages.append("Gap quality not checked: convex-hull interpolation may bridge sparse computed samples; use --max-gap.")
    return {
        "reference_samples": len(ref.x),
        "computed_samples": len(computed.x),
        "supported_reference_samples": n,
        "sample_coverage": n / len(ref.x),
        "reference_domain": [ref.x[0], ref.x[-1]],
        "computed_domain": [computed.x[0], computed.x[-1]],
        "domain_intersection": [overlap_min, overlap_max] if overlap_min <= overlap_max else None,
        "interval_length_coverage": _interval_fraction(ref, computed, max_gap),
        "overlap_mae": sum(abs(v) for v in errors) / n if n else None,
        "overlap_rmse": sqrt(sum(v*v for v in errors) / n) if n else None,
        "full_domain_eligible": full,
        "mode": mode,
        "verdict": verdict,
        "warnings": messages,
    }


def scaled(profile: Profile, factor: float) -> Profile:
    if not isfinite(factor) or factor <= 0:
        raise ProfileError("coordinate scale must be a positive finite number")
    return Profile(tuple(x * factor for x in profile.x), profile.values)


def validate_units(ref_unit: str | None, computed_unit: str | None,
                   scale: float | None, *, kind: str) -> None:
    if (ref_unit is None) != (computed_unit is None):
        raise ProfileError(f"{kind}: supply both reference and computed unit labels, or neither")
    if ref_unit is not None and ref_unit != computed_unit and scale is None:
        raise ProfileError(f"{kind}: units differ; explicit --computed-coordinate-scale required for coordinates; field conversion is not automatic")
    if kind == "field" and scale is not None:
        raise ProfileError("field scaling is not supported")
