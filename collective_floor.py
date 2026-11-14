"""Series ratings on one scale; keep later measurements out of pre-match claims."""
import re
from concurrent.futures import ThreadPoolExecutor
from lxml import html
from second_source import norm
from titan import parse_dt


def extract(data, team):
    doc=html.fromstring(data)
    teams=[]
    for table in doc.xpath('//*[@id="all-content"]//table'):
        if 'totalstats' not in table.classes:continue
        header=table.find_class('header-row')
        if len(header)!=1:continue
        label=header[0].find_class('teamName')
        version=header[0].find_class('ratingDesc')
        if len(label)!=1 or norm(label[0].text_content())!=norm(team):continue
        if len(version)!=1 or version[0].text_content().strip()!='3.0':continue
        players={}
        for row in table.xpath('.//tr[not(contains(@class,"header-row"))]'):
            nick=row.find_class('player-nick'); value=row.find_class('rating')
            if len(nick)!=1 or len(value)!=1:continue
            raw=value[0].text_content().strip()
            name=nick[0].text_content().strip()
            if not name or name.casefold() in {n.casefold() for n in players} or not re.fullmatch(r'\d+\.\d{2}',raw):
                return {}
            line={'rating':float(raw)}
            for field in ('adr','kast','kd'):
                cells=[c.text_content().strip() for c in row.find_class(field) if 'traditional-data' in c.classes]
                if len(cells)==1:line[field]=cells[0]
            players[name]=line
        teams.append(players)
    return teams[0] if len(teams)==1 else {}


def inspect_series(row, snapshot, cutoff, loader):
    if row.get('state')!='MARCADOR CORROBORADO':return None
    url=row['url']
    if not re.fullmatch(r'https://www\.hltv\.org/matches/\d+/[a-z0-9-]+',url):return None
    if snapshot is not None:
        record=snapshot.get(url,{}).get(norm(row['team']),{})
        players=record.get('players',{})
        checked=record.get('checked')
    else:
        try:
            data,checked=loader(url)
            players=extract(data,row['team'])
        except (OSError,ValueError):
            players,checked={},None
    before=bool(checked and parse_dt(checked)<cutoff and row['before'])
    alerts=[name for name,line in players.items() if line['rating']<0.80]
    return {'team':row['team'],'opponent':row['opponent'],'date':row['date'],'source':url,'checked':checked,
            'scope':'PREPARTIDO' if before else 'RETROSPECTIVA' if checked else 'SIN DATOS',
            'method':'HLTV Rating 3.0 · serie completa','players':players,'alerts':alerts,
            'series_won':row['score'][0]>row['score'][1],
            'compensation':'POR VERIFICAR EN RONDAS' if alerts else 'SIN ALERTA OBSERVADA' if players else 'SIN DATOS'}


def collect(network, cutoff, snapshot, loader):
    rows=[r for group in network['hltv'] for r in group['series']]
    with ThreadPoolExecutor(max_workers=3) as pool:
        records=[v for v in pool.map(lambda r:inspect_series(r,snapshot,cutoff,loader),rows) if v]
    pre=[v for v in records if v['scope']=='PREPARTIDO']
    return {'series':records,'prematch_ratings':sum(len(v['players']) for v in pre),
            'prematch_alerts':sum(len(v['alerts']) for v in pre),'review_ratings':sum(len(v['players']) for v in records),
            'review_alerts':sum(len(v['alerts']) for v in records)}


def compensation_cases(floor, evidence):
    """Describe team responses in flagged series, without assigning causal credit."""
    for item in floor['series']:
        item['round_evidence']=[]
        if not item['alerts']:continue
        candidates=[s for s in evidence['teams'][item['team']]['series']
                    if s['date']==item['date'] and s['opponent']==item['opponent']]
        if len(candidates)!=1:continue
        verification=candidates[0].get('verification',{})
        if verification.get('state')!='CORROBORADA' or verification.get('side') not in (0,1):continue
        for name,rounds in verification.get('rounds',{}).items():
            count=recovered=0
            for pair in rounds:
                own=pair[verification['side']]
                if own.get('first_death')==1 and own.get('first_kills')==0:
                    count+=1
                    recovered+=int(own['win']==1)
            item['round_evidence'].append({'map':name,'lost_openings':count,'recovered':recovered,
                'source':verification['source'],'checked':verification.get('checked_at') or evidence.get('second_source_checked')})
