from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import unittest
from cfd_profile_audit.nasa import duct_derived, compare_duct_raw, cone_votes, run_nasa

ROOT=Path(__file__).resolve().parents[1]

class NASATests(unittest.TestCase):
    def test_a09_derived_six_and_ten_station_pooled(self):
        result=duct_derived(ROOT/'examples/nasa/m205_station_metrics_derived.csv')
        self.assertEqual(result['six_station']['SA']['matched_samples'],202)
        self.assertEqual(result['all_stations']['SA']['matched_samples'],348)
        self.assertAlmostEqual(result['six_station']['SA']['pooled_mae_over_uinf'],0.107263,places=6)
        self.assertAlmostEqual(result['six_station']['SST']['pooled_mae_over_uinf'],0.101615,places=6)
        self.assertAlmostEqual(result['all_stations']['SA']['pooled_mae_over_uinf'],0.093952,places=6)
        self.assertAlmostEqual(result['all_stations']['SST']['pooled_mae_over_uinf'],0.087436,places=6)
        self.assertIsNone(result['definition_flips'])

    def test_raw_comparison_changes_preference_by_definition(self):
        piv={-30.:{0.:0.,1.:0.}}
        sa={-30.:{0.:-1.,1.:1.}}  # signed bias cancels, absolute error does not
        sst={-30.:{0.:0.5,1.:0.5}}
        result=compare_duct_raw(piv,sa,sst)
        self.assertEqual(result['definition_flips'],1)
        self.assertEqual(result['six_station']['SA']['matched_samples'],2)

    def test_cone_vote_reaggregation_is_modal_per_group(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'votes.csv'
            p.write_text('station,solver,width,pref_B\n482.6,VULCAN,2,SST-Vm\n482.6,VULCAN,2,SA\n482.6,VULCAN,3,SST-Vm\n')
            result=cone_votes(p)
        self.assertEqual(result['vote_count'],3)
        self.assertEqual(result['station_solver_groups'],1)
        self.assertEqual(result['mean_modal_agreement_by_width']['2'],0.5)
        self.assertEqual(result['mean_modal_agreement_by_width']['3'],1)

    def test_packaged_derived_path(self):
        result=run_nasa('duct','derived')
        self.assertEqual(result['all_stations']['SST']['matched_samples'],348)

if __name__=='__main__':unittest.main()
