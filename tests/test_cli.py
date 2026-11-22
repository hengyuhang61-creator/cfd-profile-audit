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

if __name__=='__main__':unittest.main()
