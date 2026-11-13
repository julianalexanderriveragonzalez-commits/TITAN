import unittest
from causal import contrast

def event(rival,ident,**changes):
    r=dict(kind='recovery',map='mirage',side='CT',equipment='menor',opponent=rival,series_id=ident,observed=True)
    r.update(changes)
    return r

class TransferTests(unittest.TestCase):
    def test_repetition_and_complementary_rival_with_counterexample(self):
        a=[event('X','1'),event('Y','2'),event('X','1',observed=False)]
        b=[event('Z','3',kind='lost_opening_advantage',side='T',equipment='mayor')]
        f=contrast(a,b,'Next')[0]
        self.assertEqual((f['hits'],f['opportunities'],f['target_hits']),(2,3,1))
        self.assertTrue(f['compatible'])
        for field,value in [('series_id','1'),('side','CT'),('equipment','menor'),('map','nuke'),('observed',False)]:
            self.assertFalse(contrast(a,[dict(b[0],**{field:value})],'Next')[0]['compatible'])
    def test_same_rival_or_target_cannot_supply_repetition(self):
        for rival in ('X','Next'):
            self.assertFalse(contrast([event('X','1'),event(rival,'2')],[],'Next')[0]['repeat'])
