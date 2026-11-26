"""Local, provenance-aware intake for CSV and 1-D Tecplot point tables."""
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re

from .core import Profile, ProfileError, audit
from .preflight import IDENTITY, LENGTH_POWER, validation_evidence

HEADER_UNITS = {*LENGTH_POWER, "1", "%", "m/s", "cm/s", "mm/s", "ft/s", "Pa", "kPa",
                "MPa", "K", "s", "kg/m^3", "N/m^2", "W/m^2"}
UNITS = ("coordinate_unit", "field_unit")
SIDES = ("reference", "computed")
ZONE = re.compile(
    r'ZONE\s*,?\s*T\s*=\s*"([^"]+)"((?:\s*,?\s*(?:I\s*=\s*\d+|(?:F|DATAPACKING)\s*=\s*POINT))*)',
    re.IGNORECASE,
)
POSITION = re.compile(
    r"([xyz])\s*=\s*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)"
    r"(?:\s*\[([^\[\]]+)\])?",
    re.IGNORECASE,
)


def _source(path, raw, location):
    return {"file": str(Path(path).resolve()), "sha256": sha256(raw).hexdigest(), "location": location}


def _unit(label):
    return label.replace("µm", "um").replace("μm", "um")


def _decimal(value):
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ProfileError(f"invalid decimal value {value!r}") from exc
    if not number.is_finite():
        raise ProfileError(f"non-finite decimal value {value!r}")
    return number


def _shift(number, power):
    sign, digits, exponent = number.as_tuple()
    return Decimal((sign, digits, exponent + power))


@dataclass
class Table:
    source: dict
    columns: list
    rows: list
    selection: tuple
    zone: dict | None = None

    def profile(self, power=0, *, sort=False):
        x_index, value_index = (self.columns.index(name) for name in self.selection)
        points = []
        for line, row in self.rows:
            try:
                x = float(_shift(_decimal(row[x_index]), power)) if power else float(row[x_index])
                points.append((x, float(row[value_index])))
            except (OverflowError, ValueError, InvalidOperation) as exc:
                raise ProfileError(f"{self.source['file']}:{line}: invalid numeric cell") from exc
        if sort:
            points.sort()
        try:
            return Profile(tuple(x for x, _ in points), tuple(value for _, value in points))
        except ProfileError as exc:
            raise ProfileError(f"{self.source['file']}: {exc}") from exc


def _tecplot(lines, requested):
    columns, header, zones = [], None, {}
    current = None
    for line, raw in enumerate(lines, 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        label, _, rhs = value.partition("=")
        if label.strip().upper() == "TITLE" and current is None:
            continue
        if label.strip().upper() == "VARIABLES":
            if not re.fullmatch(r'\s*"[^"]+"(?:\s*,?\s*"[^"]+")*\s*', rhs):
                raise ProfileError(f"line {line}: expected quoted Tecplot VARIABLES on one line")
            names = re.findall(r'"([^"]+)"', rhs)
            if columns and names != columns:
                raise ProfileError(f"line {line}: inconsistent Tecplot VARIABLES across zones")
            columns, header, current = names, line, None
            continue
        if match := ZONE.fullmatch(value):
            name = match[1]
            if header is None or name in zones:
                raise ProfileError(f"line {line}: missing VARIABLES or duplicate zone {name!r}")
            count = re.search(r"\bI\s*=\s*(\d+)", match[2], re.IGNORECASE)
            current = (line, header, int(count[1]) if count else None, [])
            zones[name] = current
            continue
        row = value.replace(",", " ").split()
        if current is None or len(row) != len(columns):
            raise ProfileError(f"line {line}: expected 1-D Tecplot POINT rows or a named ZONE")
        current[3].append((line, row))
    if requested is None and len(zones) == 1:
        requested = next(iter(zones))
    if requested not in zones:
        raise ProfileError(f"select a Tecplot zone from {list(zones)!r}")
    line, header, count, rows = zones[requested]
    if count is not None and count != len(rows):
        raise ProfileError(f"line {line}: declared I={count} but found {len(rows)} rows")
    return columns, header, rows, {"title": requested, "line": line}


def read_table(path, coordinate, field, zone=None):
    raw = Path(path).read_bytes()
    data = raw.decode("utf-8-sig")
    if Path(path).suffix.lower() == ".csv":
        if zone is not None:
            raise ProfileError(f"{path}: zones are only available for Tecplot inputs")
        reader = csv.reader(StringIO(data, newline=""), strict=True)
        columns = next(reader, [])
        header = 1
        rows = [(reader.line_num, row) for row in reader if row]
        if any(len(row) != len(columns) for _, row in rows):
            raise ProfileError(f"{path}: CSV rows must have the same width as the header")
    else:
        try:
            columns, header, rows, zone = _tecplot(data.splitlines(), zone)
        except ProfileError as exc:
            raise ProfileError(f"{path}: {exc}") from exc
    if len(set(columns)) != len(columns):
        raise ProfileError(f"{path}: duplicate column names")
    if coordinate == field or coordinate not in columns or field not in columns:
        raise ProfileError(f"{path}: select two distinct columns from {columns!r}")
    return Table(_source(path, raw, f"line {header}"), columns, rows, (coordinate, field), zone)


def _entry(status, value=None, source=None, raw_value=None, rule=None, confirmation="UNCONFIRMED"):
    return {"status": status, "value": value, "source": source, "raw_value": raw_value, "rule": rule,
            "confirmation": confirmation}


def _position(value):
    keys = {"axis", "origin", "direction", "value", "unit"}
    if value.keys() != keys or not all(isinstance(item, str) and item.strip() for item in value.values()):
        raise ProfileError("structured station requires nonempty strings for axis, origin, direction, value, unit")
    value = {k: item.strip() for k, item in value.items()}
    value["unit"] = _unit(value["unit"])
    if value["unit"] not in LENGTH_POWER:
        raise ProfileError("structured station requires a supported length unit")
    _decimal(value["value"])
    return value


def _metres(value):
    return _shift(_decimal(value["value"]), LENGTH_POWER[value["unit"]])


def _fields(table, side, document, declaration_source):
    labels = document.get(side, {})
    links = document.get("sources", {}).get(side, {})
    if not isinstance(labels, dict) or labels.keys() - set(IDENTITY):
        raise ProfileError(f"{side}: expected identity fields {', '.join(IDENTITY)}")
    if not isinstance(links, dict) or links.keys() - set(IDENTITY) or any(
            not isinstance(link, str) or not link.strip() for link in links.values()):
        raise ProfileError(f"{side}: supporting citations must be nonempty strings keyed by identity field")
    result = {}
    for key in IDENTITY:
        raw = labels.get(key)
        if key == "station" and isinstance(raw, dict):
            value = _position(raw)
        elif isinstance(raw, str) and raw.strip():
            value = _unit(raw.strip()) if key in UNITS else raw.strip()
        elif raw is None:
            result[key] = _entry("MISSING")
            continue
        else:
            raise ProfileError(f"{side}.{key}: expected a nonempty string or null")
        source = {**declaration_source, "location": f"$.{side}.{key}", "citation": links.get(key)}
        result[key] = _entry("USER_DECLARED", value, source, raw, "explicit declaration",
                             confirmation="USER_DECLARED")

    for key, column in zip(UNITS, table.selection):
        match = re.search(r"\[([^\[\]]+)\]\s*$", column)
        if match and _unit(match[1].strip()) in HEADER_UNITS:
            unit = _unit(match[1].strip())
            source = {**table.source, "column": column}
            observed = _entry("EXPLICIT_SOURCE", unit, source, column, "recognized bracketed unit")
            declared = result[key]
            if declared["status"] == "USER_DECLARED":
                observed["declaration"] = declared
                if declared["value"] != unit:
                    observed["status"] = "CONFLICT"
                else:
                    observed["confirmation"] = "USER_DECLARED"
            result[key] = observed
        elif result[key]["status"] == "MISSING":
            source = {**table.source, "column": column}
            if suffix := re.search(r"_(mm|cm|km|m|um|m_s)$", column):
                result[key] = _entry("CANDIDATE", source=source, raw_value=column,
                                     rule="unit-like column suffix, verify with source")
                result[key]["candidate_value"] = suffix[1].replace("_", "/")
            else:
                result[key] = _entry("MISSING", source=source, raw_value=column)

    if table.zone and (match := POSITION.fullmatch(table.zone["title"])):
        station = result["station"]
        source = {**table.source, "location": f"line {table.zone['line']}, ZONE T"}
        literal = {"axis": match[1].lower(), "value": match[2], "unit": _unit(match[3].strip()) if match[3] else None}
        station["observed"] = _entry("EXPLICIT_SOURCE", literal, source, table.zone["title"],
                                     "literal axis and position in zone title")
        stated = station["value"]
        if not isinstance(stated, dict):
            station["status"] = "UNRESOLVED"
        elif literal["unit"] and literal["unit"] not in LENGTH_POWER:
            station["status"] = "UNRESOLVED"
        elif (stated["axis"] != literal["axis"]
              or _metres(stated) != _metres({**literal, "unit": literal["unit"] or stated["unit"]})):
            station["status"] = "CONFLICT"
        else:
            station["observed"]["confirmation"] = "USER_DECLARED"
    return result


def _check_identity(left, right):
    statuses = {}
    power = 0
    for name in IDENTITY:
        a, b = left[name], right[name]
        x, y = a["value"], b["value"]
        if "CONFLICT" in (a["status"], b["status"]):
            status = "CONFLICT"
        elif None in (x, y) or "UNRESOLVED" in (a["status"], b["status"]):
            status = "MISSING"
        elif name == "station" and isinstance(x, dict) and isinstance(y, dict):
            same_frame = all(x[k] == y[k] for k in ("axis", "origin", "direction"))
            status = "MATCH" if same_frame and _metres(x) == _metres(y) else "MISMATCH"
        elif name == "coordinate_unit" and x in LENGTH_POWER and y in LENGTH_POWER:
            power = LENGTH_POWER[y] - LENGTH_POWER[x]
            status = "MATCH"
        else:
            status = "MATCH" if x == y else "MISMATCH"
        statuses[name] = status
    return statuses, power


def audit_inputs(reference, computed, *, declarations=None, max_gap=None, sort=False):
    document, declaration_source = {}, {}
    if declarations:
        raw = Path(declarations).read_bytes()
        document = json.loads(raw.decode("utf-8-sig"))
        declaration_source = _source(declarations, raw, "$")
        if not isinstance(document, dict) or document.keys() - {
                *SIDES, "reference_kind", "evidence", "sources"}:
            raise ProfileError("invalid declarations document")
    sources = document.get("sources", {})
    if not isinstance(sources, dict) or sources.keys() - set(SIDES):
        raise ProfileError("sources must be an object keyed by reference or computed")
    fields = {side: _fields(table, side, document, declaration_source)
              for side, table in zip(SIDES, (reference, computed))}
    checks, power = _check_identity(*fields.values())
    ref, comp = reference.profile(sort=sort), computed.profile(power, sort=sort)
    numeric = audit(ref, comp, max_gap=max_gap)
    knots = set(comp.x)
    interior = sum(comp.x[0] < x < comp.x[-1] and x not in knots for x in ref.x)
    covered = sum(comp.x[0] <= x <= comp.x[-1] for x in ref.x)
    gap = "NOT_APPLICABLE"
    if interior:
        gap = ("UNKNOWN" if max_gap is None else
               "PASS" if covered == numeric["supported_reference_samples"] else "FAIL")
    complete = numeric.pop("full_domain_eligible")
    scores = {name: numeric.pop(name) for name in ("overlap_mae", "overlap_rmse")}
    for name in ("mode", "verdict", "warnings"):
        numeric.pop(name)
    if {"MISMATCH", "CONFLICT"}.intersection(checks.values()):
        consistency = "MISMATCH"
    else:
        consistency = "INCOMPLETE" if "MISSING" in checks.values() else "CONSISTENT"
    if consistency == "MISMATCH":
        eligibility = "INELIGIBLE_IDENTITY"
    elif consistency == "INCOMPLETE":
        eligibility = "UNKNOWN_IDENTITY"
    elif not complete:
        eligibility = "INELIGIBLE_SUPPORT"
    elif gap == "UNKNOWN":
        eligibility = "UNKNOWN_INTERPOLATION"
    else:
        eligibility = "ELIGIBLE_DESCRIPTIVE"
    inputs = {side: {**table.source, "columns": table.columns, "selected_columns": table.selection,
                     "zone": table.zone, "identity": fields[side]}
              for side, table in zip(SIDES, (reference, computed))}
    return {
        "report_version": 1, "inputs": inputs,
        "declaration_consistency": {"status": consistency, "checks": checks},
        "comparison_eligibility": eligibility,
        "numeric_support": {
            **numeric, "coordinate_units_match": checks["coordinate_unit"] == "MATCH",
            "computed_coordinate_scale": {"power_of_ten": power, "status": "DERIVED" if power else "NOT_APPLIED",
                                          "rule": "computed unit to reference unit"},
            "max_gap_in_reference_coordinates": max_gap, "interpolation_gap": gap,
            "interior_interpolated_reference_samples": interior,
            "scope": "numeric coordinates; physical interpretation requires eligible identity",
        },
        "error_metrics": scores if eligibility == "ELIGIBLE_DESCRIPTIVE" else None,
        "scientific_validation": validation_evidence(document),
    }
