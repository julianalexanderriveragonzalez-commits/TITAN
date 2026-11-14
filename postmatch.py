"""T11 compares final observations with a separately preserved pre-match report."""
from datetime import datetime, timezone
import re
from time import time
from research import HOST, MATCH, detail, normalize
from titan import TASKS, parse_dt


def official_result(match, source):
    path = source.removeprefix(HOST)
    if not re.fullmatch(MATCH, path):
        raise ValueError('Ficha BLAST inválida.')
    fixture, _ = detail(path, int(time() // 60))
    names = [fixture[k]['name'] for k in ('teamA', 'teamB')]
    expected = {normalize(match[k]): match[k] for k in ('team_a', 'team_b')}
    if (fixture['type'] != 'BO3' or set(map(normalize, names)) != set(expected)
            or parse_dt(fixture['scheduledAt']) != parse_dt(match['cutoff'])):
        raise ValueError('La ficha no corresponde al BO3 y corte registrados.')
    teams = [expected[normalize(n)] for n in names]
    maps = []
    wins = [0, 0]
    now = datetime.now(timezone.utc)
    for game in fixture['maps']:
        if not game.get('endedAt'):
            continue
        scores = [game['teamAScore'], game['teamBScore']]
        end = parse_dt(game['endedAt'])
        if (any(type(s) != int or s < 0 for s in scores) or scores[0] == scores[1]
                or not parse_dt(match['cutoff']) <= end <= now or max(wins) == 2):
            raise ValueError('Secuencia de mapas incompatible.')
        side = int(scores[1] > scores[0])
        wins[side] += 1
        maps.append({'map': game['name'], 'scores': dict(zip(teams, scores)), 'winner': teams[side]})
    if max(wins) != 2 or wins != [fixture['teamAScore'], fixture['teamBScore']]:
        raise ValueError('BLAST aún no confirma el resultado final del BO3.')
    return {'winner': teams[wins.index(2)], 'maps': maps, 'source': source, 'origin': 'BLAST'}


def review(report, result, frozen_at, evaluated_at):
    cutoff = parse_dt(report['match']['cutoff'])
    prospective = bool(frozen_at and parse_dt(frozen_at) < cutoff
                       and report.get('verdict', {}).get('timing', 'PREPARTIDO') == 'PREPARTIDO')
    winner = result.get('winner')
    selected = report['selection']
    mechanism = 'SIN HIPÓTESIS TÁCTICA CONGELADA'
    hypothesis = report.get('postmatch_hypothesis')
    if prospective and hypothesis == 'REMONTAR_TRAS_PERDER_MAPA_1':
        maps = result.get('maps', [])
        if not maps:
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
    return {'status': state, 'frozen_at': frozen_at, 'evaluated_at': evaluated_at,
            'selected': selected, 'actual': result, 'prospective': prospective,
            'correct': selected == winner if prospective and winner else None,
            'mechanism': mechanism, 'hypothesis': hypothesis,
            'steps': [{'step': k.split('_')[0], 'status': state if k == TASKS[10] else
                       report['tasks'].get(k,'PENDIENTE')} for k in TASKS]}
