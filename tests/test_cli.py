import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from cfd_profile_audit.cli import main

ROOT=Path(__file__).resolve().parents[1]

class CLITests(unittest.TestCase):
    def run_cli(self,*args):
        proc=subprocess.run([sys.executable,'-m','cfd_profile_audit',*args],text=True,capture_output=True,cwd=ROOT)
        return proc

    def test_demo_can_create_svg_and_data_without_network(self):
        with TemporaryDirectory() as d:
            p=self.run_cli('demo','--plot',str(Path(d)/'demo.svg'),'--write-csv',d,'--json')
            self.assertEqual(p.returncode,0,p.stderr)
            obj=json.loads(p.stdout)
            self.assertEqual(obj['naive_clamped_rmse'],0)
            self.assertTrue((Path(d)/'demo.svg').is_file())
            self.assertTrue((Path(d)/'computed.csv').is_file())

    def test_user_csv_strict_error_and_overlap(self):
        with TemporaryDirectory() as d:
            p=self.run_cli('demo','--write-csv',d)
            self.assertEqual(p.returncode,0,p.stderr)
            args=('compare',str(Path(d)/'reference.csv'),str(Path(d)/'computed.csv'),'--coordinate','y','--field','u','--json')
            strict=self.run_cli(*args)
            self.assertEqual(strict.returncode,1,strict.stderr)
            self.assertEqual(json.loads(strict.stdout)['supported_reference_samples'],13)
            overlap=self.run_cli(*args,'--mode','overlap')
            self.assertEqual(overlap.returncode,0,overlap.stderr)
            self.assertEqual(json.loads(overlap.stdout)['verdict'],'OVERLAP_ONLY')

    def test_invalid_input_exit_2(self):
        with TemporaryDirectory() as d:
            a=Path(d)/'ref.csv';b=Path(d)/'computed.csv'
            a.write_text('y,u\n1,0\n2,0\n')
            b.write_text('y,u\n2,0\n2,1\n')
            p=self.run_cli('compare',str(a),str(b))
            self.assertEqual(p.returncode,2)
            self.assertIn('duplicates',p.stderr)

    def test_comparison_preflight(self):
        identity = dict(case='channel', station='x=1 m', coordinate='y from lower wall',
                        field='streamwise velocity', coordinate_unit='m', field_unit='m/s',
                        normalization='dimensional', averaging='steady', conditions='Re=100')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / 'ref.csv'
            computed = root / 'computed.csv'
            metadata = root / 'identity.json'
            reference.write_text('y,u\n0,0\n0.5,1\n1,2\n')
            computed.write_text('y,u\n0,0\n1,2\n')
            inputs = ('compare', str(reference), str(computed), '--preflight', str(metadata),
                      '--max-rmse', '0', '--json')
            cases = (
                (identity, ('--max-gap', '1'), 0, 'PASS', 'station', 'PASS'),
                (dict(identity, station='x=2 m'), (), 1, 'FAIL_COMPARISON_METADATA', 'station', 'FAIL'),
                (dict(identity, averaging=None), (), 2, 'NOT_EVALUABLE', 'averaging', 'UNKNOWN'),
                (identity, (), 2, 'NOT_EVALUABLE', 'interpolation_gap', 'UNKNOWN'),
                (identity, ('--max-gap', '0.9'), 1, 'FAIL_INCOMPLETE_SUPPORT', 'interpolation_gap', 'FAIL'),
                (dict(identity, coordinate_unit='mm'), ('--computed-coordinate-scale', '1'), 1,
                 'FAIL_COMPARISON_METADATA', 'coordinate_unit', 'FAIL'),
            )
            for definition, flags, code, verdict, check, status in cases:
                with self.subTest(verdict=verdict, check=check):
                    metadata.write_text(json.dumps({'reference': identity, 'computed': definition,
                                                    'reference_kind': 'analytic'}))
                    process = self.run_cli(*inputs, *flags)
                    self.assertEqual(process.returncode, code, process.stderr)
                    result = json.loads(process.stdout)
                    self.assertEqual(result['verdict'], verdict)
                    self.assertEqual(result['preflight']['checks'][check]['status'], status)
                    evidence = result['preflight']['validation_evidence']
                    self.assertEqual(evidence['experiment_uncertainty']['status'], 'NOT_APPLICABLE')
                    self.assertEqual(evidence['grid']['status'], 'UNKNOWN')
                    if verdict in ('FAIL_COMPARISON_METADATA', 'NOT_EVALUABLE'):
                        self.assertIsNone(result['overlap_rmse'])

            computed.write_text('y,u\n0,0\n500,1\n1000,2\n')
            metadata.write_text(json.dumps({'reference': identity,
                                            'computed': dict(identity, coordinate_unit='mm')}))
            converted = self.run_cli(*inputs, '--computed-coordinate-scale', '0.001')
            self.assertEqual(converted.returncode, 0, converted.stderr)
            checks = json.loads(converted.stdout)['preflight']['checks']
            self.assertEqual(checks['interpolation_gap']['status'], 'NOT_APPLICABLE')

if __name__=='__main__':unittest.main()
