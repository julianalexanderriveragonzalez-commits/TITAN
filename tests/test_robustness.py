import unittest
from titan import analyze


def series(i,result='W'):
    return {'id':str(i),'date':f'2026-11-{i:02}T12:00:00Z','format':'BO3','result':result,'source':f'https://example.org/{i}'}

def check(a,b):
    return analyze({'match':{'team_a':'X','team_b':'Y','cutoff':'2026-11-13T08:00:00Z'},'teams':{'X':a,'Y':b}})['robustness']

class RobustnessTests(unittest.TestCase):
    def test_one_win_removal_ties_and_adverse_reverses(self):
        x=check({'series':[series(1)]},{})
        self.assertEqual((x['stable'],x['most_supportive'][0]['margin'],x['adverse']['adverse_margin']),(0,0,-.1))
    def test_shared_result_is_one_symmetric_scenario(self):
        a={'series':[series(1)]};b={'series':[series(1,'L')]}
        for x in (check(a,b),check(b,a)):
            self.assertEqual(len(x['withdrawals']),1)
            self.assertTrue(x['adverse']['shared'])
            self.assertEqual(x['adverse']['adverse_margin'],-.2)
    def test_no_replacement_with_sixth_series(self):
        x=check({'series':[series(i) for i in range(1,7)]},{})
        self.assertEqual(len(x['withdrawals']),5)
        self.assertTrue(all(r['margin']==.4 for r in x['withdrawals']))
    def test_tie_has_no_sporting_direction(self):
        self.assertIsNone(check({},{})['side'])
    def test_rival_negative_mechanism_supports_selection(self):
        x=check({},{'mechanisms':[{'date':'2026-11-10T00:00:00Z','score':-1,'source':'report'}]})
        self.assertEqual((x['side'],x['adverse']['group'],x['adverse']['adverse_margin']),('A','mechanisms',-.05))
