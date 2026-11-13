"""Corroborate each series against a public BO3.gg sheet; never execute page scripts."""
import concurrent.futures
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from time import time
from urllib.request import Request, urlopen

from lxml import html
from titan import parse_dt

HOST = 'https://bo3.gg'
ALIASES = {'mouz':'mouz-cs2','falcons':'falcons-esports','fut':'fut-cs2','betboom':'betboom-team'}
NAMES = {'teamvitality':'vitality','teamfalcons':'falcons','futesports':'fut','betboomteam':'betboom','navi':'natusvincere','g2esports':'g2','teambetboom':'betboom','teammouz':'mouz'}
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|Array\(\d+\)|\{\}|\[\]|[^,]+')
PAIR = re.compile(r'(\w+):("(?:\\.|[^"\\])*"|[\w.-]+)')


def norm(name):
    name = re.sub('[^a-z0-9]', '', name.lower())
    return NAMES.get(name,name)


@lru_cache(maxsize=48)
def fetch(path, bucket):
    if not re.fullmatch(r'/teams/[\w-]+/matches|/matches/[\w-]+', path):
        raise ValueError('Ruta inválida')
    with urlopen(Request(HOST+path,headers={'User-Agent':'TITAN-CS2/1.0'}),timeout=8) as response:
        data=response.read(3_000_001)
    if len(data)>3_000_000:
        raise ValueError('Ficha demasiado grande')
    return data.decode()


def scalar(raw):
    if raw.startswith('"'): return json.loads(raw)
    if re.fullmatch(r'-?\d+',raw): return int(raw)
    if re.fullmatch(r'-?(?:\d*\.\d+)',raw): return float(raw)
    return None


def round_data(text, maps, names):
    match=re.search(r'window\.__NUXT__=\(function\(([^)]*)\).*?\}\((.*?)\)\)</script>',text,re.S)
    if not match: return {}
    args=TOKEN.findall(match[2])
    params=match[1].split(',')
    if len(params)!=len(args): return {}
    table=dict(zip(params,map(scalar,args)))
    def fields(block):
        return {k:table[v] if v in table else scalar(v) for k,v in PAIR.findall(block)}
    game_maps={}
    for m in re.finditer(r'\{(id:[\w]+,match_id:[^{}]{0,320}?map_name:[\w"]+[^{}]{0,100}),demo_header:\{',text):
        f=fields(m[1])
        if isinstance(f.get('map_name'),str):game_maps[f['id']]=f['map_name'].removeprefix('de_')
    by_map={}
    for m in re.finditer(r'game_round_team_clans:\[\{([^{}]*)\},\{([^{}]*)\}\]',text):
        rows=[fields(block) for block in m.groups()]
        if any(not isinstance(r.get('clan_name'),str) for r in rows):continue
        rows.sort(key=lambda r:norm(r['clan_name'])!=names[0])
        if [norm(r['clan_name']) for r in rows]!=names:continue
        a,b=rows
        if type(a.get('round_number'))!=int or a.get('game_id')!=b.get('game_id') or a.get('round_number')!=b.get('round_number'):continue
        if sorted([a.get('win',-1),b.get('win',-1)],key=str)!=[0,1]:continue
        key=game_maps.get(a.get('game_id'))
        if key not in maps:continue
        stats=('win','team_side','first_kills','first_death','trade_kills','equipment_value','money_spent','grenades_damage')
        by_map.setdefault(key,{})[a['round_number']]=[{k:r.get(k) for k in stats} for r in rows]
    valid={}
    for key,rounds in by_map.items():
        score=maps[key]
        if set(rounds)==set(range(1,sum(score)+1)) and sum(v[0]['win'] for v in rounds.values())==score[0]:
            valid[key]=[rounds[i] for i in sorted(rounds)]
    return valid


def parse_sheet(text, team, series, path):
    doc=html.fromstring(text)
    event=next(e for e in json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0]) if e.get('@type')=='SportsEvent')
    names=[norm(n) for n in event['name'].split(' vs ')]
    if set(names)!={norm(team),norm(series['opponent'])} or event['url']!=HOST+path or parse_dt(event['startDate']).date()!=parse_dt(series['date']).date():
        return None
    score={}
    for e in doc.find_class('c-match-score-map'):
        tag=e.getparent().find('a')
        if tag is None:continue
        score[tag.text_content().strip().lower().replace('dust ii','dust2')]=[int(v) for v in re.findall(r'\d+',e.text_content())]
    side=names.index(norm(team))
    expected={m['map'].removeprefix('de_'):m['score'][::1 if side==0 else -1] for m in series['maps']}
    if score!=expected:return {'state':'CONTRADICCIÓN','source':HOST+path}
    players={}
    for board in doc.find_class('c-widget-match-scoreboard'):
        header=board.find_class('o-widget__header')
        if not header or norm(header[0].text_content().replace('Scoreboard',''))!=norm(team):continue
        for row in board.find_class('table-row'):
            nick=row.find_class('nickname')
            if not nick:continue
            values={}
            for key in ('kills','deaths','adr'):
                cell=row.find_class(key)
                if cell and re.fullmatch(r'\d+(?:\.\d+)?',cell[0].text_content().strip()):values[key]=float(cell[0].text_content().strip())
            if len(values)==3:players[nick[0].text_content().strip()]=values
    return {'state':'CORROBORADA','source':HOST+path,'players':players,'side':side,'rounds':round_data(text,score,names)}


def corroborate(name, team, bucket):
    slug=team['profile'].split('/')[-1]
    index=html.fromstring(fetch('/teams/'+ALIASES.get(slug,slug)+'/matches',bucket))
    paths=list(dict.fromkeys(index.xpath('//a[starts-with(@href,"/matches/")]/@href')))
    def inspect(s):
        date=parse_dt(s['date']).strftime('%d-%m-%Y')
        for path in [p for p in paths if re.fullmatch(r'/matches/[\w-]+-'+date,p)][:6]:
            try:
                result=parse_sheet(fetch(path,bucket),name,s,path)
                if result:return result
            except (OSError,ValueError,KeyError,IndexError,StopIteration,TypeError):continue
        return {'state':'SIN CONFIRMAR'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
        return dict(zip((s['id'] for s in team['series']),workers.map(inspect,team['series'])))


def enrich(evidence):
    for name,team in evidence['teams'].items():
        try: results=corroborate(name,team,int(time()//1800))
        except (OSError,ValueError,KeyError):results={}
        for s in team['series']:
            s['verification']=results.get(s['id'],{'state':'ACCESO LIMITADO'})
    evidence['second_source_checked']=datetime.now(timezone.utc).isoformat()
