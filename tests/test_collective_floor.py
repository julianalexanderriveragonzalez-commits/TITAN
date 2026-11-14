import unittest
from collective_floor import extract,inspect_series
from titan import parse_dt


def table(scope,kind,rating,version='3.0'):
    return f'<div id="{scope}"><table class="{kind}"><tr class="header-row"><td class="teamName">Vitality</td><td class="ratingDesc">{version}</td></tr><tr><td class="player-nick">P</td><td class="rating">{rating}</td></tr></table></div>'

class FloorTests(unittest.TestCase):
    url='https://www.hltv.org/matches/123/a'
    def test_only_series_both_sides_and_known_scale(self):
        raw=table('map1','totalstats','0.23')+table('all-content','ctstats','0.19')+table('all-content','totalstats','0.81')
        self.assertEqual(extract(raw,'Vitality'),{'P':{'rating':0.81}})
        self.assertFalse(extract(table('all-content','totalstats','0.21','2.1'),'Vitality'))
    def test_strict_threshold_and_observation_time(self):
        row=dict(team='Vitality',opponent='A',date='2026-11-10',url=self.url,state='MARCADOR CORROBORADO',score=[2,0],before=True)
        cut=parse_dt('2026-11-13T08:00:00Z')
        snapshot={self.url:{'vitality':{'checked':cut.isoformat(),'players':{'P':{'rating':0.79},'Q':{'rating':0.80}}}}}
        v=inspect_series(row,snapshot,cut,None)
        self.assertEqual(v['alerts'],['P'])
        self.assertEqual(v['scope'],'RETROSPECTIVA')
        self.assertEqual(v['compensation'],'POR VERIFICAR EN RONDAS')
    def test_conflicting_result_excluded(self):
        self.assertIsNone(inspect_series({'state':'CONTRADICCIÓN'},None,None,None))
