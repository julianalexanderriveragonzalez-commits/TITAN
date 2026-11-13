"""T3: compare recorded claims at their observation time, independently of scoring."""
from urllib.parse import urlsplit

from titan import parse_dt, window_rows


def before(timestamp, cutoff):
    try:
        return parse_dt(timestamp) < cutoff
    except (AttributeError, TypeError, ValueError):
        return False


def player_lines(series, verification):
    primary = series.get('players', {})
    secondary = verification.get('players', {})
    map_ids = {str(i) for i in range(1, len(series['maps']) + 1)}
    rows = []
    for nick in sorted(set(n.casefold() for n in [*primary, *secondary])):
        left = [(n, maps) for n, maps in primary.items() if n.casefold() == nick]
        right = [(n, line) for n, line in secondary.items() if n.casefold() == nick]
        label = (left or right)[0][0]
        result = 'UNA FUENTE'
        if len(left) > 1 or len(right) > 1:
            result = 'IDENTIDAD AMBIGUA'
        elif left and right:
            maps = left[0][1]
            total = right[0][1]
            if not map_ids or set(map(str, maps)) != map_ids:
                result = 'MAPAS INCOMPLETOS'
            elif all(type(m.get(k)) in (int, float) for m in maps.values() for k in ('kills','deaths')) and all(type(total.get(k)) in (int,float) for k in ('kills','deaths')):
                agrees = all(sum(m[k] for m in maps.values()) == total[k] for k in ('kills','deaths'))
                result = 'K-D CORROBORADO' if agrees else 'K-D EN CONFLICTO'
            else:
                result = 'DATOS INCOMPLETOS'
        rows.append({'player':label,'state':result})
    return rows


def dossier(evidence, cutoff):
    primary_time = evidence.get('retrieved')
    rows = []
    used = set()
    for team, info in evidence['teams'].items():
        for s in window_rows(info['series'],cutoff,series=True)[0][:5]:
            ver = s.get('verification', {})
            second_time = ver.get('checked_at') or evidence.get('second_source_checked')
            url = ver.get('source')
            state = ver.get('state','SIN CONFIRMAR')
            if state == 'CORROBORADA':
                hosts = [urlsplit(link or '').hostname for link in (s.get('source'),url)]
                if hosts[0] == hosts[1] or (team,url) in used:
                    state = 'EVIDENCIA DUPLICADA'
                elif hosts != ['blast.tv','bo3.gg']:
                    state = 'POR VALIDAR'
                else:
                    used.add((team,url))
            timely = before(primary_time,cutoff) and before(second_time,cutoff)
            confirmed = state == 'CORROBORADA'
            players = player_lines(s,ver) if confirmed else []
            rows.append({'team':team,'opponent':s['opponent'],'date':s['date'],
                         'primary':s['source'],'primary_checked':primary_time,
                         'secondary':url,'secondary_checked':second_time,
                         'prematch':state if timely else 'SIN CONSTANCIA AL CORTE',
                         'review':state,'after_cutoff':bool(second_time and not before(second_time,cutoff)),
                         'players':players,'prematch_players':players if timely else []})
    confirmed = sum(r['prematch']=='CORROBORADA' for r in rows)
    kd_before = sum(p['state']=='K-D CORROBORADO' for r in rows for p in r['prematch_players'])
    kd_review = sum(p['state']=='K-D CORROBORADO' for r in rows for p in r['players'])
    full = len(evidence['teams'])==2 and len(rows)==10 and confirmed==10
    for team,info in evidence['teams'].items():
        roster={n.casefold() for n in info['player_series']}
        group=[r for r in rows if r['team']==team]
        full = full and len(roster)==5 and len(group)==5 and all(
            roster <= {p['player'].casefold() for p in r['prematch_players'] if p['state']=='K-D CORROBORADO'}
            for r in group)
    return {'status':'COMPLETADA' if full else 'PARCIAL' if rows else 'PENDIENTE',
            'series':rows,'confirmed_before':confirmed,
            'confirmed_review':sum(r['review']=='CORROBORADA' for r in rows),
            'kd_before':kd_before,'kd_review':kd_review}
