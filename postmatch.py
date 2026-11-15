"""T11 compares final observations with a separately preserved pre-match report."""
from datetime import datetime, timezone
import re
from time import time
from research import HOST, MATCH, detail, normalize
from titan import TASKS, ordered_review, parse_dt


def official_result(match, source):
    path = source.removeprefix(HOST)
    if not re.fullmatch(MATCH, path):
        raise ValueError('Ficha BLAST inválida.')
    fixture, _ = detail(path, int(time() // 60))
    names = [fixture[k]['name'] for k in ('teamA', 'teamB')]
    expected = {normalize(match[k]): match[k] for k in ('team_a', 'team_b')}
    fmt = fixture['type']
    if (fmt not in ('BO1','BO2','BO3','BO5','BO7') or fmt != match.get('format','BO3') or set(map(normalize, names)) != set(expected)
            or parse_dt(fixture['scheduledAt']) != parse_dt(match['cutoff'])):
        raise ValueError('La ficha no corresponde al formato y corte registrados.')
    teams = [expected[normalize(n)] for n in names]
    maps = []
    wins = [0, 0]
    limit = int(fmt[2:])
    target = limit // 2 + 1
    now = datetime.now(timezone.utc)
    for game in fixture['maps']:
        if not game.get('endedAt'):
            continue
        scores = [game['teamAScore'], game['teamBScore']]
        end = parse_dt(game['endedAt'])
        if (any(type(s) != int or s < 0 for s in scores) or scores[0] == scores[1]
                or not parse_dt(match['cutoff']) <= end <= now or sum(wins) >= limit or (fmt != 'BO2' and max(wins) >= target)):
            raise ValueError('Secuencia de mapas incompatible.')
        side = int(scores[1] > scores[0])
        wins[side] += 1
        maps.append({'map': game['name'], 'scores': dict(zip(teams, scores)), 'winner': teams[side]})
    complete = sum(wins) == 2 if fmt == 'BO2' else max(wins) == target
    if not complete or wins != [fixture['teamAScore'], fixture['teamBScore']]:
        raise ValueError('BLAST aún no confirma el resultado final del encuentro.')
    return {'winner': 'EMPATE' if wins[0] == wins[1] else teams[int(wins[1] > wins[0])], 'maps': maps, 'source': source, 'origin': 'BLAST'}


def review(report, result, frozen_at, evaluated_at):
    cutoff = parse_dt(report['match']['cutoff'])
    prospective = bool(frozen_at and parse_dt(frozen_at) < cutoff
                       and report.get('verdict', {}).get('timing', 'PREPARTIDO') == 'PREPARTIDO')
    if parse_dt(evaluated_at) <= cutoff:
        raise ValueError('T11 requiere una evaluación posterior al corte.')
    winner = result.get('winner')
    selected = report['selection']
    mechanism = 'SIN HIPÓTESIS TÁCTICA CONGELADA'
    hypothesis = report.get('postmatch_hypothesis')
    if prospective and hypothesis == 'REMONTAR_TRAS_PERDER_MAPA_1':
        maps = result.get('maps', [])
        if report['match'].get('format') in ('BO1','BO2') or selected == 'EMPATE':
            mechanism = 'NO APLICA AL FORMATO O RESULTADO'
        elif not maps:
            mechanism = 'FALTAN MAPAS VERIFICADOS'
        elif maps[0]['winner'] == selected:
            mechanism = 'NO SE DIO LA CONDICIÓN'
        else:
            mechanism = 'OBSERVADA' if winner == selected else 'REFUTADA'
    if not prospective:
        state = 'BLOQUEADA'
    elif result.get('origin') == 'BLAST' and mechanism in ('OBSERVADA','REFUTADA','NO SE DIO LA CONDICIÓN'):
        state = 'COMPLETADA'
    else:
        state = 'PARCIAL'
    findings = dict(report.get('stage_findings', report['tasks']))
    findings[TASKS[10]] = state
    steps = ordered_review(findings)
    return {'status': steps[-1]['status'], 'finding': state, 'frozen_at': frozen_at, 'evaluated_at': evaluated_at,
            'selected': selected, 'actual': result, 'prospective': prospective,
            'correct': selected == winner if prospective and winner else None,
            'mechanism': mechanism, 'hypothesis': hypothesis,
            'steps': steps}
