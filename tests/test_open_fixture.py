import json
import unittest
from unittest.mock import patch

import open_fixture as fixtures
from lxml import html


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.saved = json.loads(fixtures.SNAPSHOT.read_text())
        self.match = dict(team_a='Genone', team_b='33',cutoff='2026-11-14T13:30:00-05:00')

    @patch('open_fixture.read',side_effect=OSError)
    def test_original_fixture_offline(self,read):
        self.assertEqual(fixtures.lookup(self.match)['tournament'],'NODWIN Clutch Series 14')

    @patch('open_fixture.read',side_effect=OSError)
    def test_other_fixture_or_cutoff_never_uses_snapshot(self,read):
        self.assertIsNone(fixtures.lookup(dict(self.match,team_b='333')))
        self.assertIsNone(fixtures.lookup(dict(self.match,cutoff='2026-11-14T13:00:00-05:00')))

    def test_untrusted_url(self):
        with self.assertRaises(ValueError):
            fixtures.lookup(dict(self.match,source_url='https://example.com/matches/12345/a-vs-b'))

    def test_calendar_discovers_other_tournament(self):
        path='/matches/9876543/alpha-vs-beta-regional'
        calendar=html.fromstring('<a href="'+path+'">fixture</a>')
        page=html.fromstring('<main><div class="team1-gradient"><div class="teamName">Alpha</div></div>'
            '<div class="team2-gradient"><div class="teamName">Beta</div></div><div class="timeAndEvent">'
            '<div class="time" data-unix="1794681000000"></div><a href="/events/123/regional">Regional</a>'
            '</div><div class="preformatted-text">Best of 5</div></main>')
        with patch('open_fixture.read',side_effect=[calendar,page]):
            result=fixtures.lookup(dict(self.match,team_a='Beta',team_b='Alpha'))
        self.assertEqual((result['tournament'],result['format']),('Regional','BO5'))
