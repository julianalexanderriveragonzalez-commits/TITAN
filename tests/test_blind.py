import json
import unittest
from titan import analyze, blind_evidence


def report(a, b, first, second):
    return analyze({'match':{'team_a':a,'team_b':b,'cutoff':'2026-11-13T08:00:00Z'},
                    'teams':{a:first,b:second}})


class BlindScoringTests(unittest.TestCase):
    result = {'series':[{'date':'2026-11-12T18:00:00Z','source':'https://example.org/secret',
                         'opponent':'Secret','players':{'Secret':{}},'format':'BO3','result':'W'}]}

    def test_no_identifiers_reach_scoring(self):
        self.assertNotIn('secret',json.dumps(blind_evidence(self.result)).lower())
        self.assertTrue(blind_evidence(self.result)['series'][0]['source'])

    def test_renaming_preserves_decision(self):
        a=report('Alpha','Zeta',self.result,{})
        b=report('Zeta','Alpha',self.result,{})
        self.assertEqual(a['blind_scoring'],b['blind_scoring'])
        self.assertEqual(b['selection'],'Zeta')

    def test_swapping_evidence_reverses_sign(self):
        a=report('Uno','Dos',self.result,{})
        b=report('Dos','Uno',{},self.result)
        self.assertEqual(a['selection'],b['selection'])
        self.assertEqual(a['difference'],-b['difference'])

    def test_tie_has_no_sporting_side(self):
        a=report('Alpha','Zeta',{},{});b=report('Zeta','Alpha',{},{})
        self.assertIsNone(a['blind_scoring']['sporting_side'])
        self.assertNotEqual(a['selection'],b['selection'])
        self.assertTrue(a['blind_scoring']['administrative'])
