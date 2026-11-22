"""Bounded NASA/SU2 teaching reproductions with explicit evidence levels.

Duct upstream path recomputes from archived velocity CSVs. Cone path recomputes
statistics from a *derived* A08 vote archive, not the NASA native solutions.
"""
from __future__ import annotations
import collections
import csv
import hashlib
import json
from pathlib import Path
from importlib.resources import files
from statistics import mean
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from .core import ProfileError
from .plotting import nasa_svg

SIX_STATIONS = frozenset({-30, -10, 0, 10, 30, 50})
U_INF = 532.0
SOURCE_REV = '2b2be8c4e982af6e97542237aeaaf9da615707bd'
UPSTREAM = f'https://raw.githubusercontent.com/ofirnirr/SU2-SWBLI-Mach-2-RANS-Validation/{SOURCE_REV}/results/validation/M205_3mm_z21/'
SOURCES = {
    'piv': ('m205_3mm_z21_piv_profiles.csv','3c4f862b2c036a2cb4c02cc01a389b6827f1a49134234288a50b6e29732a81f8'),
    'SA': ('SA_M205_3mm_medium_su2_profiles_z21.csv','98d7f514f944c9f5f2d511460533d0b593f3e14a88461d570209abc134deb380'),
    'SST': ('SST_M205_3mm_medium_su2_profiles_z21.csv','5b3a4fb6a683bd5a4ee09c2e6ef0a5360a8c2f919f5f888e85ccee35fac69916'),
}
# Original analysis, not the full NASA data; published with the existing SWBLI audit.
CONE_URL = ('https://raw.githubusercontent.com/hengyuhang61-creator/'
            'aero-propulsion-system-id/b436ba1581cc39ffc7611118cf90cafc20d2011e/'
            'research/swbli-validation-audit/cone-window-votes.csv')
CONE_SHA256 = '07cf55352caa68642f82b732e477d92cd37a3ae40c369241fb41623a63e6caea'
WIDTHS = (2,3,4,5,6,8)


def retrieve(url: str, sha256: str) -> bytes:
    with urlopen(url, timeout=40) as response:
        raw = response.read()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != sha256:
        raise ProfileError(f'upstream SHA-256 mismatch: expected {sha256}, got {observed}')
    return raw


def load_velocity_csv(path: Path) -> dict[float, dict[float, float]]:
    tables: dict[float, dict[float, float]] = collections.defaultdict(dict)
    with path.open(newline='',encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if not {'target_x_mm','y_mm','U_m_s'}.issubset(reader.fieldnames or []):
            raise ProfileError('NASA table missing required coordinates/velocity columns')
        for row in reader:
            x,y,u=float(row['target_x_mm']),round(float(row['y_mm']),4),float(row['U_m_s'])
            if y in tables[x]:
                raise ProfileError(f'duplicate NASA (station,y) sample at {x},{y}')
            tables[x][y]=u
    return tables


def _trap(values: list[float], ys: list[float]) -> float:
    return sum((a+b)*(v-u)/2 for a,b,u,v in zip(values,values[1:],ys,ys[1:]))


def compare_duct_raw(piv: dict, sa: dict, sst: dict) -> dict:
    station_rows=[]
    for station in sorted(piv):
        ys=sorted(set(piv[station]) & set(sa.get(station,{})) & set(sst.get(station,{})))
        if len(ys)<2:
            raise ProfileError(f'NASA station {station} has fewer than two common y samples')
        errors={name:[model[station][y]-piv[station][y] for y in ys] for name,model in [('SA',sa),('SST',sst)]}
        win=ys[-1]-ys[0]
        if win<=0:
            raise ProfileError('NASA y span is zero')
        metrics={name:{'mae_u_n':mean(abs(e) for e in error)/U_INF,
                        'bias_preference_score':abs(_trap(error,ys)/win),
                        'integrated_absolute_error':_trap([abs(e) for e in error],ys)/win}
                 for name,error in errors.items()}
        station_rows.append({'station':station,'n':len(ys),'metrics':metrics,
                             'definition_flip':(min(metrics,key=lambda n:metrics[n]['bias_preference_score']) !=
                                                min(metrics,key=lambda n:metrics[n]['integrated_absolute_error']))})
    return summarize_duct(station_rows,'upstream_exported_CSV',include_flips=True)


def summarize_duct(rows: list[dict], evidence: str, *, include_flips: bool) -> dict:
    six=[row for row in rows if row['station'] in SIX_STATIONS]
    def summary(selected):
        return {name:{'matched_samples':sum(row['n'] for row in selected),
                      'pooled_mae_over_uinf':sum(row['n']*row['metrics'][name]['mae_u_n'] for row in selected)/sum(row['n'] for row in selected),
                      'equal_station_mae_over_uinf':mean(row['metrics'][name]['mae_u_n'] for row in selected)} for name in ('SA','SST')}
    if not rows or not six:
        raise ProfileError('NASA table has no required stations')
    result={'case':'Mach 2.05 duct, SU2/PIV','provenance':evidence,
            'station_count':len(rows),'six_station':summary(six),'all_stations':summary(rows),
            'source_commit':SOURCE_REV, 'u_inf_m_s':U_INF,
            'limits':['Exported velocity tables are not a native SU2 solver rerun.',
                      'PIV wall-normal resolution does not establish a measured separation length.']}
    if include_flips:
        result['definition_flips']=sum(r['definition_flip'] for r in rows)
        result['definition_flip_denominator']=len(rows)
    else:
        result['definition_flips']=None
    result['per_station_mae']={name:{r['station']:r['metrics'][name]['mae_u_n'] for r in rows} for name in ('SA','SST')}
    return result


def duct_derived(path: Path) -> dict:
    with path.open(newline='',encoding='utf-8-sig') as handle:
        records=list(csv.DictReader(handle))
    grouped: dict[float,dict]={}
    for row in records:
        x=float(row['station']); name=row['model']; n=int(row['n']); e=float(row['mae_u_n'])
        g=grouped.setdefault(x,{'station':x,'n':n,'metrics':{}})
        if g['n']!=n or name in g['metrics']:
            raise ProfileError('derived table has mismatched counts or duplicate models')
        g['metrics'][name]={'mae_u_n':e}
    if any(set(r['metrics'])!={'SA','SST'} for r in grouped.values()):
        raise ProfileError('derived table requires SA and SST at every station')
    return summarize_duct(list(grouped.values()),'A09_derived_station_metrics',include_flips=False)


def duct_upstream() -> dict:
    with TemporaryDirectory() as d:
        datasets={}
        for name,(filename,digest) in SOURCES.items():
            path=Path(d)/filename
            path.write_bytes(retrieve(UPSTREAM+filename,digest))
            datasets[name]=load_velocity_csv(path)
        return compare_duct_raw(datasets['piv'],datasets['SA'],datasets['SST'])


def cone_votes(path: Path) -> dict:
    grouped: dict[tuple[float,str],list[tuple[float,str]]]=collections.defaultdict(list)
    with path.open(newline='',encoding='utf-8-sig') as handle:
        reader=csv.DictReader(handle)
        if not {'station','solver','width','pref_B'}.issubset(reader.fieldnames or []):
            raise ProfileError('cone vote table missing required columns')
        for row in reader:
            grouped[(float(row['station']),row['solver'])].append((float(row['width']),row['pref_B']))
    if not grouped:
        raise ProfileError('empty cone vote table')
    per_width={w:[] for w in WIDTHS}
    for key,rows in sorted(grouped.items()):
        ref=collections.Counter(pref for _,pref in rows).most_common(1)[0][0]
        for width in WIDTHS:
            subs=[v for w,v in rows if abs(w-width)<0.05]
            if subs:per_width[width].append(sum(v==ref for v in subs)/len(subs))
    return {'case':'Mach 2.5 axisymmetric 16-degree cone','provenance':'A08_derived_window_votes',
            'vote_count':sum(map(len,grouped.values())),'station_solver_groups':len(grouped),
            'mean_modal_agreement_by_width':{str(w):mean(per_width[w]) if per_width[w] else None for w in WIDTHS},
            'source_sha256':CONE_SHA256,
            'limits':['Derived window votes are not a rerun from native NASA PIV/solver fields.',
                      'Modal-vote reference differs from Mach 2.05 full-profile bias preference.',
                      'SST-Vm is not interchangeable with duct SST.']}


def run_nasa(case: str, source: str, *, plot: str | None = None, data: str | None = None) -> dict:
    if case=='duct':
        if source=='derived':
            path=Path(data) if data else files('cfd_profile_audit').joinpath('data/m205_station_metrics_derived.csv')
            result=duct_derived(path)
        elif source=='upstream':
            result=duct_upstream()
        else:
            raise ProfileError('duct --source must be derived or upstream')
        if plot:nasa_svg(result['per_station_mae'],plot)
        return result
    if case=='cone':
        if source!='derived':
            raise ProfileError('cone supports only derived window-vote reproduction')
        if data:
            return cone_votes(Path(data))
        with TemporaryDirectory() as folder:
            path=Path(folder)/'cone-window-votes.csv'
            path.write_bytes(retrieve(CONE_URL,CONE_SHA256))
            return cone_votes(path)
    raise ProfileError('case must be duct or cone')
