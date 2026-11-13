"""Named documentary view. Its contents never enter the scoring functions."""
from titan import parse_dt, window_rows


def key(name):
    return name.strip().casefold()


def unique_five(names):
    return len(names) == 5 and len({key(n) for n in names if key(n)}) == 5


def participation(series, use_secondary):
    primary = {key(n):n for n, maps in series.get('players', {}).items() if maps}
    ver = series.get('verification', {})
    secondary = list(ver.get('players', {})) if use_secondary and ver.get('state') == 'CORROBORADA' else []
    observed = dict(primary)
    observed.update({key(n):n for n in secondary})
    map_ids = {str(n) for n in range(1,len(series.get('maps', []))+1)}
    complete_primary = unique_five(list(primary.values())) and bool(map_ids) and all(
        set(map(str, maps)) == map_ids for maps in series['players'].values())
    complete = (complete_primary or unique_five(secondary)) and unique_five(list(observed.values()))
    status = 'VERIFICADA' if complete else 'PARCIAL' if observed else 'SIN DATOS'
    if len(observed)>5:
        status = 'REVISAR CAMBIO DE ALINEACIÓN'
    return list(observed.values()),status


def build_identity(evidence, cutoff):
    at = evidence['retrieved']
    second_at = evidence.get('second_source_checked')
    before = bool(second_at and parse_dt(second_at)<cutoff)
    primary_before = parse_dt(at)<cutoff
    teams = {}
    for name,team in evidence['teams'].items():
        roster=list(team['player_series'])
        rows=[]
        for s in window_rows(team['series'],cutoff,series=True)[0][:5]:
            prematch, pre_state = participation(s,before) if primary_before else ([], 'SIN DATOS')
            observed,state=participation(s,True)
            rows.append({'opponent':s['opponent'],'date':s['date'],'players':observed,'status':state,
                         'prematch_players':prematch,'prematch_status':pre_state,
                         'outside_roster':[n for n in observed if key(n) not in {key(p) for p in roster}],
                         'source':s['source'],'secondary_source':s.get('verification',{}).get('source')})
        # Current team profiles do not independently attest the starting five for the target.
        confirmation=team.get('fixture_lineup_evidence',{})
        starters=confirmation.get('players',[])
        fixture_ok=(unique_five(starters) and confirmation.get('source')==evidence.get('source')
                    and bool(confirmation.get('checked_at')) and parse_dt(confirmation['checked_at'])<cutoff)
        verified=(fixture_ok and unique_five(roster) and bool(rows)
                  and all(s['prematch_status']=='VERIFICADA' for s in rows))
        teams[name]={'verified':verified,'starters':starters if fixture_ok else [],'roster':roster,'roster_source':team['profile'],'series':rows,
                     'fixture_lineup':'CONFIRMADO' if fixture_ok else 'PENDIENTE DE CONFIRMACIÓN ESPECÍFICA'}
    complete=len(teams)==2 and all(t['verified'] for t in teams.values())
    return {'title':'Identidad y alineación verificadas','status':'COMPLETADA' if complete else 'PARCIAL','primary_checked':at,
            'secondary_checked':second_at,'secondary_post_cutoff':bool(second_at and not before),'teams':teams}
