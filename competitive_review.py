"""Blind comparison of two documented pre-match series portfolios."""
from collections import Counter
from statistics import mean



def series_record(series, roster, rating, confirmed):
    """Require matching players, scores and complete round coverage from the collectors."""
    if not confirmed or not rating or not roster or len(roster) != 5:
        return None
    board = {n.casefold(): v for n,v in rating['players'].items()}
    if set(board) != {n.casefold() for n in roster}:
        return None
    ver = series['verification']
    side = ver.get('side')
    if side not in (0,1):
        return None
    counts = Counter()
    contexts = Counter()
    situations={k:[0,0] for k in ("lost_advantage","comeback","close")}
    map_responses=[]
    recovery_sequences={}
    for game in series['maps']:
        name = game['map'].removeprefix('de_')
        rounds = ver.get('rounds', {}).get(name, [])
        if not rounds or len(rounds) != sum(game['score']):
            return None
        map_recoveries=map_deficits=0
        losses = 0
        previous = None
        lead = peak = own_score = enemy_score = 0
        lost_advantage = comeback = False
        for pair in rounds:
            own, other = pair[side], pair[1-side]
            opening = own.get('first_kills'), own.get('first_death')
            if (opening not in ((1,0),(0,1)) or opening[::-1] != (other.get('first_kills'),other.get('first_death'))
                    or {own.get('team_side'),other.get('team_side')} != {'T','CT'}
                    or {own.get('win'),other.get('win')} != {0,1}
                    or any(type(r.get(k)) != int or r[k]<0 for r in pair
                           for k in ('equipment_value','trade_kills','grenades_damage'))):
                return None
            win = own['win']
            opened = bool(opening[0])
            map_deficits+=int(not opened)
            map_recoveries+=int(not opened and win)
            for key,active in [('lost_advantage',lost_advantage),('comeback',comeback),
                               ('close',own_score==enemy_score and own_score>=11)]:
                if active:
                    situations[key][0]+=1
                    situations[key][1]+=win
            lost_advantage=opened and not win
            own_score+=win
            enemy_score+=1-win
            lead=own_score-enemy_score
            comeback=peak>=3 and lead==0
            peak=0 if comeback else max(peak,lead)
            counts['opens' if opened else 'deficits'] += 1
            counts['converted' if opened else 'recovered'] += win
            counts['traded_recovery'] += int(not opened and win and own['trade_kills']>0)
            counts['utility'] += own['grenades_damage']
            lane = own['team_side']
            if previous != lane:
                losses = 0
            if losses == 3:
                counts['stress'] += 1
                counts['response'] += win
            losses = 0 if win else losses+1
            previous = lane
            economy = (own['equipment_value']>other['equipment_value'])-(own['equipment_value']<other['equipment_value'])
            if not opened:
                recovery_sequences.setdefault((name,lane,economy),[]).append((win,own['trade_kills']>0))
            contexts[name,lane,economy,opened,'opportunities'] += 1
            contexts[name,lane,economy,opened,'wins'] += win
        map_responses.append((name,map_recoveries,map_deficits))
    if not all(type(p.get('rating')) in (int,float) and p.get('kast') for p in board.values()):
        return None
    return {'recovery_sequences':recovery_sequences,'maps':map_responses,'date':series['date'],'situations':situations,'player_ratings':[board[n.casefold()]['rating'] for n in roster],
            'id':series['id'],'opponent':series['opponent'],'ratings':[p['rating'] for p in board.values()],
            'counts':dict(counts),'contexts':contexts,'sources':[series['source'],ver['source'],rating['source']]}


def compare(groups, rest):
    metrics=[]
    for group in groups:
        if not group:
            return None,[]
        c=sum((Counter(r['counts']) for r in group),Counter())
        if not all(c[k] for k in ('opens','deficits','stress')):
            return None,[]
        metrics.append({'IND':mean(mean(r['ratings']) for r in group),
                        'CCE':c['traded_recovery']/c['deficits'],'STR':c['converted']/c['opens'],
                        'ADP':c['response']/c['stress'],'LOG':rest[len(metrics)]})
    candidates=set()
    for side, group in enumerate(groups):
        contexts=set(k[:3] for r in group for k in r['contexts'] if k[3] is False)
        for name,lane,economy in contexts:
            opposing = (name,'CT' if lane=='T' else 'T',-economy,True)
            home = (name,lane,economy,False)
            def repeated(records,key,recovery):
                rivals=set()
                for r in records:
                    n=r['contexts'][key+('opportunities',)]
                    w=r['contexts'][key+('wins',)]
                    if n and 2*(w if recovery else n-w)>n:
                        rivals.add(r['opponent'])
                return len(rivals)>=2
            if repeated(group,home,True) and repeated(groups[1-side],opposing,False):
                candidates.add(side)
    for i,m in enumerate(metrics):
        m['OPP'] = i in candidates
    if len(candidates)!=1:
        return None,metrics
    side=candidates.pop()
    a,b=metrics[side],metrics[1-side]
    # A matched opening-recovery mechanism is required. Stronger contrary
    # compensation or adaptation prevents authorizing the candidate.
    supported=(a['CCE']>b['CCE'] and a['ADP']>=b['ADP'] and
               not (a['IND']<b['IND'] and a['STR']<b['STR']) and a['LOG']>=b['LOG'])
    return ('AB'[side] if supported else None),metrics


def evaluate(groups, rest):
    side,metrics=compare(groups,rest)
    trials=[]
    if side:
        for ident in sorted({r['id'] for group in groups for r in group}):
            removed=[[r for r in group if r['id']!=ident] for group in groups]
            retained,_=compare(removed,rest)
            adverse=[]
            for i,group in enumerate(groups):
                stressed=[]
                for row in group:
                    if row['id']==ident:
                        # Turn all recoveries in this series against the candidate.
                        change=dict(row['counts'])
                        events=row['contexts'].copy()
                        for k in list(events):
                            if k[-1]=='wins':
                                events[k]=0 if 'AB'[i]==side else events[k[:-1]+('opportunities',)]
                        for count,denom in [('traded_recovery','deficits'),('converted','opens'),('response','stress')]:
                            change[count]=0 if 'AB'[i]==side else change.get(denom,0)
                        row=dict(row,counts=change,contexts=events)
                    stressed.append(row)
                adverse.append(stressed)
            stressed_side,_=compare(adverse,rest)
            trials.append({'series':ident,'withdrawal':retained,'adverse':stressed_side})
    survives=bool(trials) and all(t['withdrawal']==side and t['adverse']==side for t in trials)
    return {'side':side,'families':metrics,'trials':trials,'survives':survives,
            'reason':('Recuperación tras la primera baja compatible con el rival, respaldada por intercambios y respuesta a pérdidas.'
                      if side else 'Sin una dirección única con apoyo colectivo, adaptación y contexto comparables.')}
