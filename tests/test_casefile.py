import unittest
from research import automatic_input
from titan import parse_dt
from multisource import dossier
from casefile import build_casefile


class CasefileTests(unittest.TestCase):
    def test_joins_only_pre_cutoff_map_lines(self):
        m={'team_a':'Vitality','team_b':'MOUZ','cutoff':'2026-11-13T03:00:00-05:00'}
        _,ev=automatic_input(m)
        r={'match':m,'multisource':dossier(ev,parse_dt(m['cutoff']))}
        f=build_casefile(r,ev)
        self.assertEqual(f['observations_at_cutoff'],20)
        self.assertEqual(f['series_count'],9)
        self.assertEqual(sum(len(t['players']) for t in f['teams'].values()),10)
        ev['retrieved']=m['cutoff']
        self.assertEqual(build_casefile(r,ev)['observations_at_cutoff'],0)
