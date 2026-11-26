"""Check declared metadata before scoring a pair of one-dimensional profiles."""
import json
from math import isclose
from pathlib import Path

from .core import ProfileError

IDENTITY = ("case", "station", "coordinate", "field", "coordinate_unit", "field_unit",
            "normalization", "averaging", "conditions")
LENGTH_POWER = {"km": 3, "m": 0, "cm": -2, "mm": -3, "um": -6}
LENGTH_IN_METRES = {unit: 10.0 ** power for unit, power in LENGTH_POWER.items()}


def _labels(document, name, allowed):
    labels = document.get(name, {})
    if not isinstance(labels, dict) or labels.keys() - set(allowed):
        raise ProfileError(f"preflight {name}: expected an object with keys {', '.join(allowed)}")
    if any(value is not None and (not isinstance(value, str) or not value.strip())
           for value in labels.values()):
        raise ProfileError(f"preflight {name}: values must be nonempty strings or null")
    return {key: value.strip() for key, value in labels.items() if value is not None}


def read_preflight(path, *, ref_units, computed_units, coordinate_scale):
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or document.keys() - {"reference", "computed", "reference_kind", "evidence"}:
        raise ProfileError("preflight requires a JSON object with reference, computed, reference_kind and evidence")
    reference = _labels(document, "reference", IDENTITY)
    computed = _labels(document, "computed", IDENTITY)
    for side, labels, flags in (("reference", reference, ref_units), ("computed", computed, computed_units)):
        for key, flag in zip(("coordinate_unit", "field_unit"), flags):
            if flag is not None and labels.setdefault(key, flag) != flag:
                raise ProfileError(f"preflight {side} {key}: CLI and metadata labels disagree")

    checks = {}
    for key in IDENTITY:
        ref, comp = reference.get(key), computed.get(key)
        status = "UNKNOWN"
        if ref is not None and comp is not None:
            status = "PASS" if ref == comp else "FAIL"
            if key == "coordinate_unit" and coordinate_scale is not None:
                if ref == comp:
                    expected_scale = 1.0
                elif ref in LENGTH_IN_METRES and comp in LENGTH_IN_METRES:
                    expected_scale = LENGTH_IN_METRES[comp] / LENGTH_IN_METRES[ref]
                else:
                    expected_scale = None
                if expected_scale is None:
                    status = "UNKNOWN"
                else:
                    status = ("PASS" if isclose(coordinate_scale, expected_scale, rel_tol=1e-12)
                              else "FAIL")
        checks[key] = {"status": status, "reference": ref, "computed": comp}
    checks["coordinate_unit"]["computed_scale"] = coordinate_scale

    statuses = {check["status"] for check in checks.values()}
    status = "FAIL" if "FAIL" in statuses else ("UNKNOWN" if "UNKNOWN" in statuses else "PASS")
    science = validation_evidence(document)
    return {"status": status, "checks": checks, "reference_kind": science["reference_kind"],
            "validation_evidence": science["evidence"],
            "scope": "declared identity and configured sampling checks; scientific validation not assessed"}


def validation_evidence(document):
    reference_kind = document.get("reference_kind")
    if reference_kind not in (None, "experiment", "analytic", "simulation"):
        raise ProfileError("preflight reference_kind must be experiment, analytic or simulation")
    evidence_keys = ("iteration", "grid", "experiment_uncertainty")
    sources = _labels(document, "evidence", evidence_keys)
    evidence = {key: {"status": "UNKNOWN", "source": sources.get(key)} for key in evidence_keys}
    if reference_kind in ("analytic", "simulation"):
        evidence["experiment_uncertainty"]["status"] = "NOT_APPLICABLE"

    return {"status": "NOT_ASSESSED", "reference_kind": reference_kind, "evidence": evidence}
