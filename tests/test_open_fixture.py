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
        self.assertEqual(fixtures.key('Tigre nuclear res'), fixtures.key('Nuclear TigeRES'))
        self.assertEqual(fixtures.second_source.norm('Tigre nuclear res'), 'nucleartigeres')
        self.assertEqual(fixtures.second_source.ALIASES['nucleartigeres'], 'nuclear-tigeres')

    def test_translated_team_name_finds_official_hltv_calendar_slug(self):
        path='/matches/2400370/betclic-vs-nuclear-tigeres-nodwin-clutch-series-14'
        calendar=html.fromstring('<a href="'+path+'">fixture</a>')
        page=html.fromstring('<main><div class="team1-gradient"><div class="teamName">Betclic</div></div>'
            '<div class="team2-gradient"><div class="teamName">Nuclear TigeRES</div></div><div class="timeAndEvent">'
            '<div class="time" data-unix="1795359600000"></div><a href="/events/123/nodwin">NODWIN Clutch Series 14</a>'
            '</div><div class="preformatted-text">Best of 3</div></main>')
        match=dict(team_a='Betclic',team_b='Tigre nuclear res',cutoff='2026-11-22T10:00:00-05:00')
        with patch('open_fixture.read',side_effect=[calendar,page]):
            result=fixtures.lookup(match)
        self.assertEqual(result['names'],['Betclic','Nuclear TigeRES'])
        self.assertEqual(result['format'],'BO3')

    def test_translated_name_recovers_from_bo3_global_calendar(self):
        path='/matches/nuclear-tigeres-vs-betclic-apogee-esports-23-11-2026'
        event={'@type':'SportsEvent','name':'Nuclear TigeRES vs Betclic','url':fixtures.second_source.HOST+path,
               'startDate':'2026-11-23T15:00:00+00:00','description':'Best of 3',
               'superEvent':{'name':'NODWIN Clutch Series 14'}}
        page=html.fromstring('<script type="application/ld+json">'+json.dumps(event)+'</script>')
        schedule=html.fromstring('<a href="'+path+'">fixture</a>')
        def fetch(pathname,bucket):
            if pathname.startswith('/teams/'):
                return '<main></main>'
            if pathname=='/matches/current':
                return html.tostring(schedule,encoding='unicode')
            if pathname==path:
                return html.tostring(page,encoding='unicode')
            raise AssertionError(pathname)
        match=dict(team_a='Betclic',team_b='Tigre nuclear res',cutoff='2026-11-23T10:00:00-05:00')
        with patch('open_fixture.read',side_effect=OSError('blocked')), \
             patch('second_source.fetch',side_effect=fetch):
            diagnostics=[]
            result=fixtures.lookup(match,diagnostics)
        self.assertEqual(result['format'],'BO3')
        self.assertIn('NODWIN Clutch Series 14',result['tournament'])
        self.assertIn('calendario general consultado', ' '.join(diagnostics))

    def test_exact_audited_betclic_fixture_uses_registry_without_network(self):
        match=dict(team_a='Betclic',team_b='Tigre nuclear res',cutoff='2026-11-22T10:00:00-05:00')
        with patch('open_fixture.read',side_effect=AssertionError('network should not be needed')):
            diagnostics=[]
            result=fixtures.lookup(match,diagnostics)
        self.assertEqual((result['names'],result['format']),(['Betclic','Nuclear TigeRES'],'BO3'))
        self.assertIn('ficha verificada',result['provider'])
        self.assertIn('Registro verificado de BO3.gg', ' '.join(diagnostics))
        with patch('open_fixture.read',side_effect=OSError('blocked')), \
             patch('second_source.fetch',side_effect=OSError('blocked')), \
             patch('open_fixture.api_fixture',return_value=None):
            self.assertIsNone(fixtures.lookup(dict(match,cutoff='2026-11-22T10:01:00-05:00')))

    def test_direct_bo3gg_sheet_verifies_translated_match(self):
        path='/matches/nuclear-tigeres-vs-betclic-apogee-esports-23-11-2026'
        page=html.fromstring('<h1>Nuclear TigeRES vs Betclic at NODWIN Clutch Series 14</h1>'
            '<div class="c-sidebar-profile-match">Date and time Nov 23, 10:00 Format Bo3</div>'
            '<span class="bo-type">Bo3</span>')
        match=dict(team_a='Betclic',team_b='Tigre nuclear res',cutoff='2026-11-23T10:00:00-05:00',
                   source_url=fixtures.second_source.HOST+path)
        with patch('second_source.fetch',return_value=html.tostring(page,encoding='unicode')):
            diagnostics=[]
            result=fixtures.lookup(match,diagnostics)
        self.assertEqual((result['format'],result['provider']),('BO3','BO3.gg'))
        self.assertIn('ficha directa', ' '.join(diagnostics))

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
