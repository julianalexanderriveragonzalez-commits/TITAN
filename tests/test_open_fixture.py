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

    def test_archived_history_replays_without_target_score(self):
        teams=fixtures.histories(self.saved,self.match)
        self.assertEqual(set(teams),{'33','Genone'})
        for team in teams.values():
            self.assertEqual(len(team['series']),5)
            for row in team['series']:
                self.assertLess(fixtures.parse_dt(row['date']), fixtures.parse_dt(self.match['cutoff']))
                self.assertGreater(fixtures.parse_dt(row['checked_at']),fixtures.parse_dt(self.match['cutoff']))
                self.assertNotEqual(row['source'], self.saved['source'])
        self.assertEqual(sum(r['result']=='W' for r in teams['33']['series']),3)
        self.assertFalse(any(r['result']=='W' for r in teams['Genone']['series']))

    def test_canonical_aliases(self):
        self.assertEqual(fixtures.key('FaZe Clan'), fixtures.key('FaZe'))
        self.assertEqual(fixtures.key('Natus Vincere'), fixtures.key('NAVI'))
        self.assertNotEqual(fixtures.key('Perturbar'), fixtures.key('FaZe'))
        self.assertEqual(fixtures.key('Fantasma'), fixtures.key('Phantom'))

    def test_direct_hltv_link_accepts_browser_translated_team_name(self):
        path='/matches/2400368/33-vs-phantom-nodwin-clutch-series-14'
        page=html.fromstring('<main><div class="team1-gradient"><div class="teamName">33</div></div>'
            '<div class="team2-gradient"><div class="teamName">Phantom</div></div><div class="timeAndEvent">'
            '<div class="time" data-unix="1795338000000"></div><a href="/events/123/nodwin">NODWIN Clutch Series 14</a>'
            '</div><div class="preformatted-text">Best of 3</div></main>')
        match=dict(team_a='33',team_b='Fantasma',cutoff='2026-11-22T04:00:00-05:00',
                   source_url=fixtures.HOST+path)
        with patch('open_fixture.read',return_value=page) as read:
            result=fixtures.lookup(match)
        self.assertEqual((result['names'],result['format']),(['33','Phantom'],'BO3'))
        read.assert_called_once_with(path,read.call_args.args[1])

    def test_direct_hltv_failure_still_tries_fallback_sources(self):
        path='/matches/2400368/33-vs-phantom-nodwin-clutch-series-14'
        match=dict(team_a='33',team_b='Fantasma',cutoff='2026-11-22T04:00:00-05:00',
                   source_url=fixtures.HOST+path)
        fallback={'names':['33','Phantom'],'source':'https://api.pandascore.co/csgo/matches/1',
                  'tournament':'NODWIN Clutch Series 14','format':'BO3',
                  'kickoff':'2026-11-22T09:00:00+00:00'}
        with patch('open_fixture.read',side_effect=OSError('blocked')), \
             patch('second_source.fetch',side_effect=OSError('blocked')), \
             patch('open_fixture.api_fixture',return_value=fallback) as api:
            diagnostics=[]
            result=fixtures.lookup(match,diagnostics)
        self.assertEqual(result,fallback)
        api.assert_called_once()
        self.assertTrue(any('ficha directa' in d for d in diagnostics))

    def test_ambiguous_matches_are_not_selected(self):
        paths=['/matches/9876543/alpha-vs-beta-regional','/matches/9876544/alpha-vs-beta-regional']
        calendar=html.fromstring('<main>'+''.join('<a href="'+p+'">fixture</a>' for p in paths)+'</main>')
        page=html.fromstring('<main><div class="team1-gradient"><div class="teamName">Alpha</div></div>'
            '<div class="team2-gradient"><div class="teamName">Beta</div></div><div class="timeAndEvent">'
            '<div class="time" data-unix="1794681000000"></div><a href="/events/123/regional">Regional</a>'
            '</div><div class="preformatted-text">Best of 3</div></main>')
        with patch('open_fixture.read',side_effect=[calendar,page,page]):
            self.assertIsNone(fixtures.lookup(dict(self.match,team_a='Alpha',team_b='Beta')))
