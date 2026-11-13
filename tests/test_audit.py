import unittest
from audit import run
from research import automatic_input
from titan import analyze,CONTROL_NAMES


class HistoricalAudit(unittest.TestCase):
    def test_postmatch_enrichment_never_changes_the_pre_match_selection(self):
        match={'team_a':'Vitality','team_b':'MOUZ','cutoff':'2026-11-13T03:00:00-05:00'}
        teams,evidence=automatic_input(match)
        data={'teams':teams,'match':match}
        report=analyze(data)
        selection=report['selection']
        audit=run(report,data,evidence)
        self.assertTrue(audit['retrospective'])
        self.assertEqual((audit['confirmed'],audit['series']), (9,9))
        self.assertEqual(set(audit['controls']),set(CONTROL_NAMES))
        self.assertEqual(audit['sample'],43)
        self.assertEqual(audit['rounds'],210)
        self.assertEqual(len(audit['cipi_diagnostic']['Equipo A']),6)
        self.assertEqual(report['selection'],selection)
