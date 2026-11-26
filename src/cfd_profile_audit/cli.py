"""Small public CLI for 1D CFD profile coverage; no solver/CFD dependencies."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import sys
from . import __version__
from .core import Profile, ProfileError, audit, clamped_sample, load_csv, scaled, validate_units
from .intake import audit_inputs, read_table
from .nasa import run_nasa
from .plotting import coverage_svg
from .preflight import read_preflight


def demo_profiles() -> tuple[Profile,Profile]:
    x=tuple(float(i) for i in range(21))
    ref=Profile(x,tuple(min(i,12)/12 for i in range(21)))
    comp=Profile(x[:13],ref.values[:13])
    return ref,comp


def write_demo_csvs(directory: str | Path) -> None:
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for name,profile in zip(('reference.csv','computed.csv'),demo_profiles()):
        with (directory/name).open('w',newline='',encoding='utf-8') as handle:
            writer=csv.writer(handle);writer.writerow(['y','u']);writer.writerows(zip(profile.x,profile.values))


def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(prog='cfd-profile-audit',description='Audit the support and identity of 1D CFD profiles.')
    p.add_argument('--version',action='version',version=f'cfd-profile-audit {__version__}')
    sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('demo',help='offline 21-reference/13-supported counterexample')
    d.add_argument('--plot',metavar='SVG',help='write reproducible coverage SVG')
    d.add_argument('--write-csv',metavar='DIRECTORY',help='write both demo CSVs')
    d.add_argument('--json',action='store_true')
    c=sub.add_parser('compare',help='audit your reference and computed CSV files')
    c.add_argument('reference');c.add_argument('computed')
    c.add_argument('--coordinate',default='y');c.add_argument('--field',default='u')
    c.add_argument('--computed-coordinate',help='computed CSV coordinate column (defaults to --coordinate)')
    c.add_argument('--computed-field',help='computed CSV field column (defaults to --field)')
    c.add_argument('--mode',choices=('strict','overlap'),default='strict')
    c.add_argument('--max-gap',type=float,metavar='LENGTH',help='reject interior interpolation across wider computed gaps')
    c.add_argument('--max-rmse',type=float,help='threshold for full-domain PASS; cannot override incomplete support')
    c.add_argument('--ref-coordinate-unit');c.add_argument('--computed-coordinate-unit')
    c.add_argument('--ref-field-unit');c.add_argument('--computed-field-unit')
    c.add_argument('--computed-coordinate-scale',type=float,help='multiply computed coordinates to express in reference coordinate units')
    c.add_argument('--preflight',metavar='JSON',help='check declared case, station, units and field definitions before scoring')
    c.add_argument('--sort',action='store_true',help='explicitly sort unordered coordinate rows; duplicates remain invalid')
    c.add_argument('--json',action='store_true',help='machine-readable result only')
    c.add_argument('--output',help='write JSON to file in addition to stdout')
    a = sub.add_parser('audit', help='inspect two CSV or 1-D Tecplot point tables with source evidence')
    a.add_argument('reference')
    a.add_argument('computed')
    a.add_argument('--coordinate', default='y')
    a.add_argument('--field', default='u')
    a.add_argument('--computed-coordinate', help='computed column if different from --coordinate')
    a.add_argument('--computed-field', help='computed column if different from --field')
    a.add_argument('--reference-zone', help='exact Tecplot zone title for the reference')
    a.add_argument('--computed-zone', help='exact Tecplot zone title for the computed profile')
    a.add_argument('--declarations', metavar='JSON', help='confirmed identity definitions for each side')
    a.add_argument('--max-gap', type=float, metavar='LENGTH', help='largest allowed interpolation gap in reference units')
    a.add_argument('--sort', action='store_true', help='explicitly sort rows; duplicate coordinates remain invalid')
    a.add_argument('--template', metavar='NEW_JSON', help='save unresolved identity fields to fill in')
    a.add_argument('--json', action='store_true', help='machine-readable report only')
    a.add_argument('--output', metavar='NEW_JSON', help='save the audit report without overwriting an existing file')
    n=sub.add_parser('nasa',help='bounded NASA Mach 2.05 / Mach 2.5 teaching reproductions')
    n.add_argument('--case',choices=('duct','cone'),required=True)
    n.add_argument('--source',choices=('derived','upstream'),default='derived')
    n.add_argument('--data',help='local source CSV (derived duct metrics or derived cone vote table)')
    n.add_argument('--plot',metavar='SVG',help='for duct: plot per-station MAE from underlying data')
    n.add_argument('--json',action='store_true')
    return p


def pretty(result: dict) -> None:
    if preflight := result.get('preflight'):
        print(f"declared comparison preflight={preflight['status']} | scientific validation not assessed")
        for name, check in preflight['checks'].items():
            if check['status'] in ('FAIL', 'UNKNOWN'):
                print(f"  {name}: {check['status']}")
    if 'supported_reference_samples' not in result:
        return
    print(f"verdict={result['verdict']} | reference={result['reference_samples']} supported={result['supported_reference_samples']} ({100*result['sample_coverage']:.1f}%)")
    if result['overlap_rmse'] is None:
        print('overlap MAE/RMSE: N/A (no matched reference samples)')
    else:
        print(f"overlap-only MAE={result['overlap_mae']:.6g}, RMSE={result['overlap_rmse']:.6g}; full_domain_eligible={result['full_domain_eligible']}")
    for warning in result['warnings']:
        print('WARNING:',warning,file=sys.stderr)


def run_intake(args):
    reference = read_table(args.reference, args.coordinate, args.field, args.reference_zone)
    computed = read_table(args.computed, args.computed_coordinate or args.coordinate,
                          args.computed_field or args.field, args.computed_zone)
    report = audit_inputs(reference, computed, declarations=args.declarations,
                          max_gap=args.max_gap, sort=args.sort)
    data = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        with Path(args.output).open('x', encoding='utf-8') as handle:
            handle.write(data + '\n')
    if args.template:
        template = {
            side: {name: item['raw_value'] if item['status'] == 'USER_DECLARED' else None
                   for name, item in details['identity'].items() if item['status'] != 'EXPLICIT_SOURCE'}
            for side, details in report['inputs'].items()
        }
        with Path(args.template).open('x', encoding='utf-8') as handle:
            json.dump(template, handle, indent=2)
            handle.write('\n')
    eligibility = report['comparison_eligibility']
    if args.json:
        print(data)
    else:
        print(f"{eligibility} | scientific validation not assessed")
        for side, details in report['inputs'].items():
            fields = details['identity']
            explicit = [f"{k}={v['value']}" for k, v in fields.items() if v['status'] == 'EXPLICIT_SOURCE']
            missing = [k for k, v in fields.items() if v['status'] in ('MISSING', 'CANDIDATE', 'UNRESOLVED', 'CONFLICT')]
            print(f"  {side} source units: {', '.join(explicit) or 'none'}")
            if missing:
                print(f"  {side} fields to resolve: {', '.join(missing)}")
        checks = report['declaration_consistency']['checks']
        mismatches = [name for name, status in checks.items() if status in ('MISMATCH', 'CONFLICT')]
        if mismatches:
            print(f"  conflicting definitions: {', '.join(mismatches)}")
        support = report['numeric_support']
        print(f"  numeric support: {support['supported_reference_samples']}/{support['reference_samples']}"
              f" | interpolation gap={support['interpolation_gap']}")
        if metrics := report['error_metrics']:
            print(f"  descriptive MAE={metrics['overlap_mae']:.6g} | RMSE={metrics['overlap_rmse']:.6g}")
    return 0 if eligibility.startswith('ELIGIBLE') else 1 if eligibility.startswith('INELIGIBLE') else 2


def main(argv: list[str] | None = None) -> int:
    args=parser().parse_args(argv)
    try:
        if args.command == 'audit':
            return run_intake(args)
        if args.command=='demo':
            ref,comp=demo_profiles()
            result=audit(ref,comp)
            naive=math.sqrt(sum((clamped_sample(comp,x)-y)**2 for x,y in zip(ref.x,ref.values))/len(ref.x))
            out={'naive_clamped_rmse':naive,**result}
            if args.plot:coverage_svg(ref,comp,args.plot)
            if args.write_csv:write_demo_csvs(args.write_csv)
            if args.json: print(json.dumps(out,indent=2,allow_nan=False))
            else:
                print(f'naive clamped RMSE={naive:g} (not valid across missing support)')
                pretty(out)
            return 0  # demonstration intentionally shows a rejected comparison
        if args.command=='compare':
            preflight = None
            if args.preflight:
                preflight = read_preflight(
                    args.preflight,
                    ref_units=(args.ref_coordinate_unit, args.ref_field_unit),
                    computed_units=(args.computed_coordinate_unit, args.computed_field_unit),
                    coordinate_scale=args.computed_coordinate_scale,
                )
            else:
                validate_units(args.ref_coordinate_unit,args.computed_coordinate_unit,args.computed_coordinate_scale,kind='coordinate')
                validate_units(args.ref_field_unit,args.computed_field_unit,None,kind='field')
            ref=load_csv(args.reference,args.coordinate,args.field,sort=args.sort)
            comp=load_csv(args.computed,args.computed_coordinate or args.coordinate,args.computed_field or args.field,sort=args.sort)
            if args.computed_coordinate_scale is not None:
                comp=scaled(comp,args.computed_coordinate_scale)
            if preflight and preflight['status'] != 'PASS':
                result = {
                    'verdict': 'FAIL_COMPARISON_METADATA' if preflight['status'] == 'FAIL' else 'NOT_EVALUABLE',
                    'overlap_mae': None, 'overlap_rmse': None, 'full_domain_eligible': False,
                    'reference_samples': len(ref.x), 'computed_samples': len(comp.x),
                    'preflight': preflight,
                }
            else:
                result=audit(ref,comp,mode=args.mode,max_gap=args.max_gap,max_rmse=args.max_rmse)
                if preflight:
                    result['preflight'] = preflight
                    checks = preflight['checks']
                    checks['sample_support'] = {
                        'status': 'PASS' if result['full_domain_eligible'] else 'FAIL',
                        'supported': result['supported_reference_samples'], 'total': len(ref.x),
                    }
                    nodes = set(comp.x)
                    interior = sum(comp.x[0] < x < comp.x[-1] and x not in nodes for x in ref.x)
                    covered = sum(comp.x[0] <= x <= comp.x[-1] for x in ref.x)
                    gap_status = 'NOT_APPLICABLE'
                    if interior:
                        if args.max_gap is None:
                            gap_status = 'UNKNOWN'
                        else:
                            gap_status = 'PASS' if covered == result['supported_reference_samples'] else 'FAIL'
                    checks['interpolation_gap'] = {
                        'status': gap_status, 'max_gap': args.max_gap, 'interior_reference_samples': interior,
                    }
                    if not result['full_domain_eligible']:
                        preflight['status'] = 'FAIL'
                    if gap_status == 'UNKNOWN':
                        if preflight['status'] == 'PASS':
                            preflight['status'] = 'UNKNOWN'
                        if result['verdict'] not in ('FAIL_INCOMPLETE_SUPPORT', 'NOT_EVALUABLE'):
                            result['verdict'] = 'NOT_EVALUABLE'
                        result['overlap_mae'] = result['overlap_rmse'] = None
                        result['full_domain_eligible'] = False
                else:
                    result['coordinate_unit']=args.ref_coordinate_unit
                    result['field_unit']=args.ref_field_unit
                    result['coordinate_units_verified']=args.ref_coordinate_unit is not None
                    result['field_units_verified']=args.ref_field_unit is not None
                    if not result['coordinate_units_verified'] or not result['field_units_verified']:
                        result['warnings'].append('CSV units are not fully verified; provide explicit unit labels.')
            if preflight:
                preflight['checks']['csv_input'] = {'status': 'PASS'}
            data=json.dumps(result,indent=2,allow_nan=False)
            if args.output:Path(args.output).write_text(data+'\n',encoding='utf-8')
            if args.json:print(data)
            else:pretty(result)
            return 2 if result['verdict']=='NOT_EVALUABLE' else (1 if result['verdict'].startswith('FAIL') else 0)
        if args.command=='nasa':
            if args.case=='cone' and args.plot:raise ProfileError('cone --plot is not available in this release')
            result=run_nasa(args.case,args.source,plot=args.plot,data=args.data)
            if args.json: print(json.dumps(result,indent=2,allow_nan=False))
            elif args.case=='duct':
                for label,counts in [('6 stations',result['six_station']),('10 stations',result['all_stations'])]:
                    for name in ('SA','SST'):
                        print(f"{label:11} {name:3} n={counts[name]['matched_samples']:3} pooled MAE/Uinf={counts[name]['pooled_mae_over_uinf']:.6f}")
                if result['definition_flips'] is not None:
                    print('Station preference flips (bias vs integrated absolute error):',result['definition_flips'],'/',result['definition_flip_denominator'])
                print('PROVENANCE:',result['provenance'])
            else:
                print('PROVENANCE:',result['provenance'],'vote_count:',result['vote_count'],'groups:',result['station_solver_groups'])
                print('by width:',{k:round(v,3) if v is not None else None for k,v in result['mean_modal_agreement_by_width'].items()})
            return 0
    except (OSError, ProfileError, ValueError, csv.Error, ArithmeticError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 2
    except Exception as exc:
        # Transport errors should be actionable but must not be mistaken for scientific failure.
        print(f'ERROR: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 2
    return 2
