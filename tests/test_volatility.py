from unittest import TestCase
from volatility import tipping_point, objections
from titan import analyze

def series(i):
    return {'id':str(i),'date':f'2026-11-{i:02}T12:00:00Z','format':'BO3','result':'W','source':str(i)}

class VolatilityTests(TestCase):
    def test_minimum_joint_flip_passes_through_tie(self):
        p={'match':{'team_a':'X','team_b':'Y','cutoff':'2026-11-13T08:00:00Z'},
           'teams':{'X':{'series':[series(1),series(2)]},'Y':{}}}
        t=tipping_point(analyze(p)['robustness'])
        self.assertEqual((t['state'],len(t['changes']),t['margin']),('INVERSIÓN',2,-.2))
    def test_admin_tie(self):
        self.assertEqual(tipping_point({'side':None})['state'],'EMPATE INICIAL')
    def test_late_conflict_cannot_be_prematch_objection(self):
        row={'team':'A','opponent':'B','primary':'primary','secondary':'second','prematch':'SIN CONSTANCIA AL CORTE',
             'review':'CORROBORADA','prematch_players':[],'after_cutoff':True,'players':[{'state':'K-D EN CONFLICTO','player':'P'}]}
        r={'multisource':{'series':[row]},'casefile':{'observations_at_cutoff':20},'robustness':{'side':'A','base_margin':.3,'withdrawals':[]},'tasks':{'T7_robustez':'BLOQUEADA'}}
        v=objections(r)
        self.assertEqual((len(v['late']),len(v['conflicts']),v['formal_status']),(1,0,'BLOQUEADA'))
        self.assertIn('carecían',v['strongest'])
