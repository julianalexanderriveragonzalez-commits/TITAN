import unittest
from unittest.mock import patch
from postmatch import official_result, review
from titan import TASKS

SOURCE='https://blast.tv/cs/tournaments/rivals-2026-season-2/match/0d409c57/vitality-mouz'
MATCH={'team_a':'MOUZ','team_b':'Vitality','cutoff':'2026-11-13T08:00:00Z'}
DATE='2026-11-13T10:10:00Z'
FROZEN='2026-11-12T10:10:00Z'

class PostmatchTests(unittest.TestCase):
    def report(self):
        return {'match':MATCH,'selection':'MOUZ','tasks':dict.fromkeys(TASKS,'COMPLETADA'),
                'postmatch_hypothesis':'REMONTAR_TRAS_PERDER_MAPA_1'}

    def test_causal_outcomes(self):
        for first,winner,expected in [('Vitality','MOUZ','OBSERVADA'),('Vitality','Vitality','REFUTADA'),
                                      ('MOUZ','MOUZ','NO SE DIO LA CONDICIÓN')]:
            audit=review(self.report(),{'origin':'BLAST','maps':[{'winner':first}],'winner':winner},FROZEN,DATE)
            self.assertEqual((audit['status'],audit['mechanism']),('COMPLETADA',expected))
            self.assertEqual(len(audit['steps']),11)

    def test_retrospective_excluded_manual_partial(self):
        actual={'origin':'MANUAL','winner':'MOUZ'}
        self.assertIsNone(review(self.report(),actual,None,DATE)['correct'])
        self.assertEqual(review(self.report(),actual,FROZEN,DATE)['status'],'PARCIAL')

    def test_reject_unfinished_and_wrong_match(self):
        fixture={'maps':[],'type':'BO3','scheduledAt':MATCH['cutoff'],'teamA':{'name':'Vitality'},
                 'teamB':{'name':'MOUZ'},'teamAScore':0,'teamBScore':0}
        with patch('postmatch.detail',return_value=(fixture,[])):
            with self.assertRaises(ValueError):official_result(MATCH,SOURCE)
            with self.assertRaises(ValueError):official_result(dict(MATCH,team_a='Spirit'),SOURCE)
