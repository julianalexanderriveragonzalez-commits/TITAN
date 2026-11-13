import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from osint_context import context
from titan import parse_dt

CUT=parse_dt('2026-11-13T08:00:00Z')
E={'teams':{'Vitality':{},'MOUZ':{}},'retrieved':'2026-11-13T06:00:00Z','tournament':'BLAST','stage':'Quarter Final','source':'https://blast.tv/cs'}
class ContextTests(unittest.TestCase):
    def test_historical_never_backfills_current_news(self):
        with patch('osint_context.datetime') as clock, patch('osint_context.headlines') as feed:
            clock.now.return_value=CUT
            r=context(E,CUT)
            feed.assert_not_called()
            self.assertEqual(r['items'][0]['scope'],'PREPARTIDO')
            self.assertEqual(r['status'],'PARCIAL')
    def test_news_dedup_identity_scope_and_cutoff(self):
        item={'title':'MOUZ announce roster','url':'https://www.hltv.org/news/123/roster','published':'Fri, 13 Nov 2026 06:00:00 GMT'}
        entries=[item,item,dict(item,url=item['url'].replace('123','124'),title='MOUZacademy plays'),
                 dict(item,url=item['url'].replace('123','125'),published='Fri, 13 Nov 2026 08:00:00 GMT')]
        with patch('osint_context.datetime') as clock,patch('osint_context.headlines',return_value=('CONSULTADA','2026-11-13T08:00:01Z',entries)):
            clock.now.return_value=parse_dt(E['retrieved'])
            r=context(E,CUT)
            self.assertEqual(len(r['items']),2)
            self.assertEqual(r['items'][1]['scope'],'RETROSPECTIVA')
    def test_feed_failure_exposes_gap(self):
        with patch('osint_context.datetime') as clock,patch('osint_context.headlines',return_value=('ACCESO LIMITADO',E['retrieved'],[])):
            clock.now.return_value=parse_dt(E['retrieved'])
            self.assertEqual(context(E,CUT)['sources'][1]['state'],'ACCESO LIMITADO')
