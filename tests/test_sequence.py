import unittest
from titan import TASKS, ordered_review, prepare_review, finalize_review
from postmatch import review
from research import fixture_fives


class SequenceTests(unittest.TestCase):
    def test_each_missing_link_blocks_all_successors(self):
        for i, key in enumerate(TASKS):
            with self.subTest(step=key):
                findings = dict.fromkeys(reversed(TASKS), 'COMPLETADA')
                del findings[key]
                trace = ordered_review(findings)
                self.assertEqual([r['status'] for r in trace],
                                 ['COMPLETADA']*i + ['PENDIENTE'] + ['BLOQUEADA']*(10-i))
                for row in trace[i+1:]:
                    self.assertEqual(row['blocked_by'], key.split('_')[0])

    def test_complete_simulated_handoff_to_postmatch(self):
        match = dict(team_a='Uno', team_b='Dos', cutoff='2099-01-01T08:00:00Z')
        r = prepare_review(dict(match=match,teams={'Uno':{},'Dos':{}}))
        # Simulate accepted outputs of T1–T8 to exercise the downstream contract.
        r['tasks'].update(dict.fromkeys(TASKS[:8], 'COMPLETADA'))
        r['cipi_decision'] = dict(side='A', robust_side='A', aliases={'A':'Uno','B':'Dos'},
                                  input_sha256=r['input_sha256'])
        r['volatility'] = dict(formal_status='COMPLETADA',conclusion='CONTRADICCIÓN Y VOLATILIDAD REVISADAS')
        r['postmatch_hypothesis'] = 'REMONTAR_TRAS_PERDER_MAPA_1'
        finalize_review(r)
        self.assertEqual(r['sequence'][-1]['status'], 'PENDIENTE TEMPORAL')
        outcome = dict(origin='BLAST',winner='Uno',maps=[{'winner':n} for n in ('Dos','Uno','Uno')])
        a = review(r,outcome,'2099-01-01T07:00:00Z','2099-01-01T11:00:00Z')
        self.assertEqual([s['status'] for s in a['steps']], ['COMPLETADA']*11)
        self.assertEqual(a['mechanism'],'OBSERVADA')

    def test_target_roster_requires_both_distinct_fives(self):
        text = '>Spirit - a, b, c, d and e faced off against MOUZ - f, g, h, i and j at the BLAST'
        self.assertEqual(fixture_fives(text,['Spirit','MOUZ'])['mouz'],list('fghij'))
        self.assertFalse(fixture_fives(text.replace('and j','and f'),['Spirit','MOUZ']))
