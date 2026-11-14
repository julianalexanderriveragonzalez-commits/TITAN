from unittest import TestCase
from engines import ORDER,chain,verified,review


class EngineTests(TestCase):
    def test_each_missing_engine_blocks_successors(self):
        for i,name in enumerate(ORDER):
            findings={n:dict(finding='COMPLETADA') for n in ORDER}
            findings[name]['finding']='PARCIAL'
            rows=chain(findings)
            self.assertFalse(verified(rows))
            self.assertEqual([r['status'] for r in rows],['COMPLETADA']*i+['PARCIAL']+['BLOQUEADA']*(5-i))
            self.assertTrue(all(r['blocked_by']==name for r in rows[i+1:]))
        self.assertFalse(verified([]))

    def test_ratings_and_replicated_response(self):
        groups=[[dict(id=f'{side}{i}',date=str(i),sources=['fixture'],opponent=str(i),maps=[],
                      recovery_sequences={('mirage','CT',0):[(0,False),(1,True),(1,True)]},
                      counts={},situations={k:[1,1] for k in ('lost_advantage','comeback','close')},
                      player_ratings=[1+i*.1,1,1,1,1]) for i in range(5)] for side in 'AB']
        rows,_=review({},groups)
        self.assertEqual(rows['PVE']['data']['A1']['changes'],4)
        self.assertEqual(rows['BMA']['finding'],'COMPLETADA')
        groups[0][0]['player_ratings'][0]=.79
        changed,_=review({},groups)
        self.assertEqual(changed['CCE']['finding'],'PARCIAL')
        self.assertEqual(chain(changed)[2]['blocked_by'],'CCE')
