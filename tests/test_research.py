import unittest
from research import automatic_input
from titan import analyze, parse_dt


class ResearchTests(unittest.TestCase):
    def test_pre_match_evidence_and_denominators(self):
        match = {'team_a':'Mouz','team_b':'Vitality','cutoff':'2026-11-13T03:00:00-05:00'}
        teams, audit = automatic_input(match)
        self.assertLess(parse_dt(audit['retrieved']), parse_dt(match['cutoff']))
        for name, team in audit['teams'].items():
            self.assertEqual(len(team['player_series']), 5)
            self.assertEqual(set(team['player_series'].values()), {2})
            self.assertTrue(all(s['source'] != audit['source'] for s in teams[name]['series']))
            self.assertLessEqual(len(team['series']), 5)
        report = analyze({'match':match,'teams':teams})
        self.assertEqual(report['confidence'], 'MUY BAJA')
        self.assertEqual(report['evidence_state'], 'CERROJO DOCUMENTAL INCOMPLETO')
