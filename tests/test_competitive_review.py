from collections import Counter
from unittest import TestCase
from competitive_review import compare, evaluate, series_record


def sample(team,i):
    strong = team == 'A'
    context = ('mirage','CT' if strong else 'T',0,not strong)
    return {'id':team+str(i),'opponent':str(i),'ratings':[1.2 if strong else .8]*5,
            'counts':dict(opens=10,deficits=10,converted=9 if strong else 2,
                          traded_recovery=9 if strong else 1,stress=3,response=3 if strong else 0),
            'contexts':Counter({context+('wins',):9 if strong else 2,context+('opportunities',):10})}


class CompetitiveTests(TestCase):
    def test_blind_comparison_and_adverse_trials(self):
        groups=[[sample(n,i) for i in range(5)] for n in 'AB']
        r=evaluate(groups,[24,24])
        self.assertEqual(r['side'],'A')
        self.assertTrue(r['survives'])
        self.assertEqual(len(r['trials']),10)
        self.assertEqual(set(r['families'][0]),set('IND CCE STR ADP LOG OPP'.split()))
        self.assertEqual(evaluate(groups[::-1],[24,24])['side'],'B')

    def test_direction_disappears_on_withdrawal(self):
        groups=[[sample(n,i) for i in range(2)] for n in 'AB']
        r=evaluate(groups,[24,24])
        self.assertEqual(r['side'],'A')
        self.assertFalse(r['survives'])

    def test_missing_pre_match_proof_and_contradiction(self):
        self.assertIsNone(series_record({},[],{},False))
        self.assertIsNone(compare([[sample('A',i) for i in range(5)],
                                   [sample('B',i) for i in range(5)]],[10,20])[0])

    def test_cloud_path_computes_direction_from_source_records(self):
        import io
        import json
        import os
        import tempfile
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch
        from cloud import app
        now=datetime.now(timezone.utc)
        checked=now.isoformat()
        cutoff=(now+timedelta(days=1)).isoformat()
        source='https://blast.tv/synthetic'
        match=dict(id='fixture',team_a='Alpha',team_b='Beta',cutoff=cutoff)
        teams={}
        evidence=dict(teams={},stage='Semi Final',tournament='Fixture',source=source,
                      retrieved=checked,second_source_checked=checked,cutoff=cutoff)
        floor=[]
        for side,name in enumerate(('Alpha','Beta')):
            roster={name+str(i):5 for i in range(5)}
            series=[]
            for i in range(5):
                ident=name+str(i)
                date=(now-timedelta(days=i+2)).isoformat()
                ownwins=([0]*3+[1]*13) if side==0 else ([0]*13+[1]*3)
                rounds=[]
                for n,win in enumerate(ownwins):
                    opened=int((n<2) if side==0 else (n>=2))
                    pair=[]
                    for index in range(2):
                        first=opened if index==0 else 1-opened
                        pair.append(dict(win=win if index==0 else 1-win,first_kills=first,first_death=1-first,
                                         team_side='CT' if index==side else 'T',equipment_value=4500,
                                         grenades_damage=20,trade_kills=int(index==0 and side==0)))
                    rounds.append(pair)
                maps=[dict(map='de_'+m,score=[sum(ownwins),16-sum(ownwins)]) for m in ('mirage','ancient')]
                score=dict(kills=15,deaths=10,adr=75)
                row=dict(id=ident,date=date,finished_at=date,source='https://blast.tv/'+ident,opponent='R'+str(i),
                         format='BO3',result='L' if side else 'W',maps=maps,
                         players={p:{1:score,2:score} for p in roster},verification=dict(
                             checked_at=checked,side=0,state='CORROBORADA',source='https://bo3.gg/'+ident,
                             players={p:dict(kills=30,deaths=20,adr=75) for p in roster},
                             rounds={'mirage':rounds,'ancient':rounds}))
                series.append(row)
                floor.append(dict(team=name,date=date,opponent=row['opponent'],scope='PREPARTIDO',
                                  source='https://www.hltv.org/'+ident,
                                  players={p:dict(kast='75%',rating=1.1) for p in roster}))
            teams[name]=dict(series=series,mechanisms=[])
            evidence['teams'][name]=dict(series=series,profile=source,player_series=roster,
                fixture_lineup_evidence=dict(players=list(roster),checked_at=checked,source=source))
        network=dict(hltv=[],floor=dict(series=floor,review_ratings=0))
        payload=json.dumps(dict(match=match,teams=teams,research_mode='automatic')).encode()
        env=dict(PATH_INFO='/api/analyze',REQUEST_METHOD='POST',CONTENT_TYPE='application/json',
                 CONTENT_LENGTH=str(len(payload)),HTTP_HOST='localhost')
        env['wsgi.input']=io.BytesIO(payload)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'TITAN_DB':tmp+'/test.db'}), \
             patch('cloud.automatic_input',return_value=(teams,evidence)),patch('audit.enrich'), \
             patch('cloud.collect_sources',return_value=network), \
             patch('osint_context.headlines',return_value=('CONSULTADA',checked,[])):
            r=json.loads(b''.join(app(env,lambda status,headers:None)))
        self.assertEqual(r['selection_basis'],'CIPI',r.get('cipi_review'))
        self.assertEqual(r['selection'],'Alpha')
        self.assertTrue(all(s['status']=='COMPLETADA' for s in r['sequence'][:10]))
