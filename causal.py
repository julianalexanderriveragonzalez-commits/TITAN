"""T5 round sequences. Round aggregates establish order and outcome, not intent."""
from collections import defaultdict
from titan import parse_dt, window_rows

LABELS = {'lost_opening_advantage':'Pierde la ronda tras conseguir la primera baja',
          'recovery':'Gana la ronda tras sufrir la primera baja'}
INVERSE = {'recovery':'lost_opening_advantage','lost_opening_advantage':'recovery'}


def rounds_for(team, rows, cutoff):
    result=[]
    for s in window_rows(team['series'],cutoff,series=True)[0][:5]:
        proof=rows.get(s['source'],{})
        if proof.get('review')!='CORROBORADA':
            continue
        v=s.get('verification',{})
        index=v.get('side')
        if index not in (0,1):continue
        for mapname, rounds in v.get('rounds',{}).items():
            for number,pair in enumerate(rounds,1):
                own,other=pair[index],pair[1-index]
                flags=(own.get('first_kills'),own.get('first_death'),other.get('first_kills'),other.get('first_death'))
                if flags not in ((1,0,0,1),(0,1,1,0)) or (own.get('win'),other.get('win')) not in ((1,0),(0,1)):continue
                side=own.get('team_side')
                if {side,other.get('team_side')}!={'CT','T'}:continue
                a,b=own.get('equipment_value'),other.get('equipment_value')
                economy=None
                if all(type(value) in (int,float) and value>0 for value in (a,b)):
                    economy='mayor' if a>b else 'menor' if a<b else 'igual'
                opened=flags[0]==1
                result.append({'series_id':s['id'],'date':s['date'],'opponent':s['opponent'],
                    'map':mapname,'round':number,'side':side,'equipment':economy,
                    'kind':'lost_opening_advantage' if opened else 'recovery',
                    'observed':own['win']==int(not opened),'trade_kills':own.get('trade_kills'),
                    'source':proof['secondary'],'primary':s['source'],'pre':proof['prematch']=='CORROBORADA'})
    return result


def contrast(home,away,target):
    groups=defaultdict(list)
    for r in home:
        groups[(r['kind'],r['map'],r['side'],r['equipment'])].append(r)
    findings=[]
    for (kind,mapname,side,equip),opportunities in groups.items():
        hits=[r for r in opportunities if r['observed']]
        if not hits:continue
        independent=[r for r in hits if r['opponent'].casefold()!=target.casefold()]
        repeated=len({r['opponent'].casefold() for r in independent})>=2
        original={r['series_id'] for r in opportunities}
        inverse={'mayor':'menor','menor':'mayor','igual':'igual'}.get(equip)
        rivals=[r for r in away if inverse and r['series_id'] not in original and
                r['kind']==INVERSE[kind] and r['map']==mapname and r['side']!=side and r['equipment']==inverse]
        matches=[r for r in rivals if r['observed']]
        findings.append({'mechanism':LABELS[kind],'map':mapname,'side':side,'equipment':equip,
                         'hits':len(hits),'opportunities':len(opportunities),'rivals':sorted({r['opponent'] for r in independent}),
                         'repeat':repeated,'target_hits':len(matches),'target_opportunities':len(rivals),
                         'compatible':bool(repeated and matches),'examples':opportunities,'target_examples':rivals})
    return sorted(findings,key=lambda v:(v['compatible'],v['repeat'],v['hits']),reverse=True)


def build_causal(report,evidence):
    cutoff=parse_dt(report['match']['cutoff'])
    names=[report['match']['team_a'],report['match']['team_b']]
    data=[]
    for name in names:
        refs={r['primary']:r for r in report['multisource']['series'] if r['team']==name}
        data.append(rounds_for(evidence['teams'][name],refs,cutoff))
    result={}
    for label,pre in [('prematch',True),('latest',False)]:
        sides=[[r for r in rows if not pre or r['pre']] for rows in data]
        findings={n:contrast(sides[i],sides[1-i],names[1-i]) for i,n in enumerate(names)}
        result[label]={'rounds':sum(map(len,sides)),'series':sum(len({r['series_id'] for r in s}) for s in sides),
                       'compatible':sum(v['compatible'] for vs in findings.values() for v in vs),'teams':findings}
    return result
