import unittest
from multisource import dossier
from titan import parse_dt

CUT=parse_dt('2026-11-13T08:00:00Z')
PRE='2026-11-13T07:59:59Z'
def sample(checked=PRE):
    stats={'kills':10,'deaths':9}
    series={'id':'m','date':'2026-11-12T13:00:00Z','format':'BO3','result':'W','opponent':'Otro',
            'source':'https://blast.tv/cs/m','maps':[{},{}],'players':{'P':{1:stats,2:stats}},
            'verification':{'source':'https://bo3.gg/matches/m','checked_at':checked,'state':'CORROBORADA',
                            'players':{'P':{'kills':20,'deaths':18},'Suplente':stats}}}
    return {'retrieved':PRE,'teams':{'A':{'series':[series],'player_series':{'P':1}}}}

class T3Tests(unittest.TestCase):
    def test_aggregate_kd_and_single_source(self):
        v=dossier(sample(),CUT)
        self.assertEqual((v['confirmed_before'],v['kd_before']),(1,1))
        self.assertEqual(v['series'][0]['players'][1]['state'],'UNA FUENTE')
    def test_exact_cutoff_and_missing_time(self):
        for t in [CUT.isoformat(),None]:
            v=dossier(sample(t),CUT)
            self.assertEqual((v['kd_before'],v['kd_review']),(0,1))
    def test_duplicate_source(self):
        e=sample();s=e['teams']['A']['series'][0];s['verification']['source']=s['source']
        self.assertEqual(dossier(e,CUT)['series'][0]['review'],'EVIDENCIA DUPLICADA')
    def test_score_agreement_does_not_override_individual_conflict(self):
        e=sample();e['teams']['A']['series'][0]['verification']['players']['P']['kills']=19
        v=dossier(e,CUT)
        self.assertEqual((v['confirmed_before'],v['kd_before']),(1,0))
        self.assertEqual(v['series'][0]['players'][0]['state'],'K-D EN CONFLICTO')
