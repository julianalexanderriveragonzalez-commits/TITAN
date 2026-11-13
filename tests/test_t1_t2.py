from copy import deepcopy
from datetime import timedelta
import json
import unittest

from audit import blind_sheets, indicators, run
from research import automatic_input
from titan import analyze, parse_dt, window_rows

CUT=parse_dt('2026-11-13T08:00:00Z')


def row(date, ident='x'):
    return {'date':date,'id':ident,'result':'W','format':'BO3','source':'https://example.org/'+ident}


class WindowTests(unittest.TestCase):
    def test_both_edges_and_equivalent_offsets(self):
        dates=['2026-10-29T02:59:59.999999-05:00','2026-10-29T03:00:00-05:00',
               '2026-11-13T07:59:59.999999Z','2026-11-13T03:00:00-05:00']
        rows=[row(d,str(i)) for i,d in enumerate(dates)]
        kept,why=window_rows(rows,CUT,True)
        self.assertEqual([x['id'] for x in kept],['2','1'])
        self.assertEqual(why,{'fuera de ventana':2})

    def test_duplicate_and_late_completion(self):
        a=row('2026-11-01T12:00:00Z')
        b=dict(a,id='b',finished_at=CUT.isoformat())
        rows,why=window_rows([a,dict(a),b],CUT,True)
        self.assertEqual(rows,[a])
        self.assertEqual(why,{'duplicada':1,'fin de serie incompatible':1})

    def test_latest_five_distinct(self):
        rows=[row((CUT-timedelta(days=i+1)).isoformat(),str(i)) for i in range(6)]
        p={'match':{'team_a':'X','team_b':'Y','cutoff':CUT.isoformat()},'teams':{'X':{'series':rows+[rows[0]]},'Y':{}}}
        a=analyze(p)['window']['teams']['Equipo A']
        self.assertEqual(a,{'eligible':6,'used':5,'excluded':{'duplicada':1}})

class BlindFilesTests(unittest.TestCase):
    def test_ten_renames_leave_files_cipi_and_floor_unchanged(self):
        match={'team_a':'Vitality','team_b':'MOUZ','cutoff':CUT.isoformat()}
        teams,e=automatic_input(match)
        run(analyze({'match':match,'teams':teams}),{'match':match,'teams':teams},e)
        # Inject comparable series ratings solely for this boundary regression.
        for team in e['teams'].values():
            for s in team['series']:
                for v in s.get('verification',{}).get('players',{}).values():v['series_rating']=0.79
        names=list(e['teams'])
        baseline=blind_sheets(e,names,CUT)
        def diagnostic(ev,teams,names):
            from unittest.mock import patch
            p={'match':dict(match,team_a=names[0],team_b=names[1]),'teams':teams}
            with patch('audit.Path.exists',return_value=False):
                return run(analyze(p),p,ev)['cipi_diagnostic']
        original=diagnostic(e,teams,names)
        changed=deepcopy(e)
        for index,name in enumerate(names):
            t=changed['teams'].pop(name)
            aliases={nick:f'Persona-{index}-{i}' for i,nick in enumerate(t['player_series'])}
            t['player_series']={aliases[n]:c for n,c in t['player_series'].items()}
            for s in t['series']:
                v=s.get('verification',{})
                v['players']={next((a for n,a in aliases.items() if n.casefold()==p.casefold()),p):x for p,x in v.get('players',{}).items()}
            changed['teams'][str(index)]=t
        renamed=blind_sheets(changed,['0','1'],CUT)
        self.assertEqual(original,diagnostic(changed,dict(zip(['0','1'],teams.values())),['0','1']))
        self.assertEqual(baseline,renamed)
        for t in renamed.values():
            metrics=indicators(t)
            self.assertTrue(metrics['floor_alerts'])
            self.assertEqual(set(metrics['players']),{f'Jugador {i}' for i in range(1,6)})
            self.assertNotIn('https:',json.dumps(t))
