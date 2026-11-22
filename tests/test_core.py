import math
import tempfile
import unittest
from pathlib import Path
from cfd_profile_audit.core import Profile, ProfileError, audit, load_csv, sample, clamped_sample, scaled, validate_units
from cfd_profile_audit.cli import demo_profiles


class CoreTests(unittest.TestCase):
    def test_full_domain_eligible_and_pass_only_with_threshold(self):
        r=Profile((0,1,2),(0,1,2));c=Profile((0,2),(0,2))
        self.assertEqual(audit(r,c)['verdict'],'FULL_COVERAGE_NO_THRESHOLD')
        self.assertEqual(audit(r,c,max_rmse=0)['verdict'],'PASS')
        self.assertEqual(audit(r,Profile((0,2),(1,3)),max_rmse=0)['verdict'],'FAIL_RMSE')

    def test_plateau_clamped_zero_but_incomplete(self):
        ref,comp=demo_profiles()
        self.assertEqual(sum((clamped_sample(comp,x)-y)**2 for x,y in zip(ref.x,ref.values)),0)
        result=audit(ref,comp,max_rmse=0)
        self.assertEqual(result['supported_reference_samples'],13)
        self.assertAlmostEqual(result['sample_coverage'],13/21)
        self.assertEqual(result['interval_length_coverage'],12/20)
        self.assertEqual(result['verdict'],'FAIL_INCOMPLETE_SUPPORT')
        self.assertEqual(result['overlap_rmse'],0)
        self.assertFalse(result['full_domain_eligible'])

    def test_explicit_overlap_mode_never_full_domain_pass(self):
        ref,comp=demo_profiles()
        result=audit(ref,comp,mode='overlap',max_rmse=0)
        self.assertEqual(result['verdict'],'OVERLAP_ONLY')
        self.assertEqual(result['overlap_mae'],0)

    def test_no_intersection_is_not_evaluable(self):
        r=Profile((0,1),(0,1));c=Profile((3,4),(0,1))
        result=audit(r,c)
        self.assertEqual(result['verdict'],'NOT_EVALUABLE')
        self.assertIsNone(result['domain_intersection'])
        self.assertIsNone(result['overlap_rmse'])

    def test_max_gap_excludes_intermediate_points_but_not_nodes(self):
        r=Profile((0,1,2,3,4),(0,1,2,3,4))
        c=Profile((0,4),(0,4))
        result=audit(r,c,max_gap=2)
        self.assertEqual(result['supported_reference_samples'],2)
        self.assertEqual(result['interval_length_coverage'],0)
        self.assertIsNone(sample(c,1,max_gap=2))
        self.assertEqual(sample(c,4,max_gap=2),4)

    def test_nonfinite_duplicate_unsorted(self):
        for xs in ((0,0),(1,0),(0,float('nan')),(0,float('inf'))):
            with self.assertRaises(ProfileError):Profile(xs,(1,1))
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'file.csv'
            p.write_text('x,u\n2,2\n0,0\n1,1\n')
            with self.assertRaises(ProfileError):load_csv(p,'x','u')
            self.assertEqual(load_csv(p,'x','u',sort=True).x,(0,1,2))
            p.write_text('x,u\n1,1\n1,2\n')
            with self.assertRaises(ProfileError):load_csv(p,'x','u',sort=True)
            p.write_text('x,u\n1,nan\n')
            with self.assertRaises(ProfileError):load_csv(p,'x','u')

    def test_units_and_scaling(self):
        with self.assertRaises(ProfileError):validate_units('mm','m',None,kind='coordinate')
        with self.assertRaises(ProfileError):validate_units('m',None,None,kind='coordinate')
        with self.assertRaises(ProfileError):scaled(Profile((1,2),(1,2)),-1)
        self.assertEqual(scaled(Profile((1,2),(1,2)),.001).x,(0.001,0.002))

    def test_equal_reference_singleton(self):
        r=Profile((2,),(10,));c=Profile((1,2,3),(7,10,13))
        out=audit(r,c,max_rmse=0)
        self.assertEqual(out['verdict'],'PASS')
        self.assertIsNone(out['interval_length_coverage'])

if __name__=='__main__':unittest.main()
