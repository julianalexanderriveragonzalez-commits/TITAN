import unittest
from source_network import reconcile,parse_dt
class HLTVTests(unittest.TestCase):
    def test_orientation_conflict_ambiguity_and_cutoff(self):
        series={'date':'2026-11-11T12:00:00Z','opponent':'Team Falcons','maps':[{'score':[13,8]},{'score':[13,6]}]}
        match={'teams':['falcons','vitality'],'date':'2026-11-11','scores':[0,2],'url':'https://www.hltv.org/matches/123/a'}
        checked='2026-11-12T08:00:00Z'; cutoff=parse_dt(checked)
        def check(index):return reconcile('Vitality',series,index,checked,cutoff)
        self.assertFalse(check([match])['before'])
        self.assertEqual(check([match])['state'],'MARCADOR CORROBORADO')
        self.assertEqual(check([dict(match,scores=[2,0])])['state'],'CONTRADICCIÓN')
        self.assertEqual(check([match,match])['state'],'COINCIDENCIA AMBIGUA')
        self.assertEqual(check([])['state'],'SIN COINCIDENCIA')
