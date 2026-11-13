import unittest
from identity import build_identity, participation
from titan import parse_dt


class IdentityTests(unittest.TestCase):
    def test_substitute_is_reported_only_when_observed(self):
        base={n:{} for n in 'ABCDE'}
        s={'date':'2026-11-01T12:00:00Z','opponent':'Rival','source':'BLAST','format':'BO3','result':'W',
           'maps':[{},{}],'verification':{'state':'CORROBORADA','source':'BO3','players':dict.fromkeys('ABCDF',{})}}
        e={'retrieved':'2026-11-11T12:00:00Z','second_source_checked':'2026-11-13T12:00:00Z',
           'teams':{'Equipo':{'series':[s],'profile':'perfil','player_series':base}}}
        r=build_identity(e,parse_dt('2026-11-13T08:00:00Z'))
        row=r['teams']['Equipo']['series'][0]
        self.assertEqual(row['outside_roster'],['F'])
        self.assertEqual(row['prematch_players'],[])
        self.assertEqual(row['status'],'VERIFICADA')
        self.assertEqual(r['status'],'PARCIAL')

    def test_five_listed_names_require_map_evidence(self):
        s={'players':{n:{1:{}} for n in 'ABCDE'},'maps':[{},{}]}
        self.assertEqual(participation(s,False)[1],'PARCIAL')
        for m in s['players'].values():m[2]={}
        self.assertEqual(participation(s,False)[1],'VERIFICADA')
