"""Resolve public HLTV fixtures without an organizer or team directory."""
import json
import logging
import unicodedata
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from time import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from lxml import html
from titan import parse_dt, FORMATS
import second_source
from source_network import result_index, fetch as fetch_index

HOST = 'https://www.hltv.org'
PATH = r'/matches/\d{5,10}/[a-z0-9-]+'
ERRORS = (OSError, ValueError, IndexError, OverflowError)
SNAPSHOT = Path(__file__).with_name('nodwin_fixture.json')


def key(name):
    raw = ''.join(c for c in unicodedata.normalize('NFKD', name.casefold()) if c.isalnum())
    return {'fazeclan':'faze', 'fnaticesports':'fnatic', 'natusvincere':'navi',
            'teamvitality':'vitality', 'g2esports':'g2', 'teamfalcons':'falcons',
            'betboomteam':'betboom', 'futesports':'fut', 'fantasma':'phantom',
            # Browser translation can reorder and translate the official team name.
            'tigrenuclearres':'nucleartigeres'}.get(raw, raw)


@lru_cache(maxsize=96)
def read(path, bucket):
    if path not in ('/matches', '/results') and not re.fullmatch(PATH, path):
        raise ValueError('Ruta HLTV inválida')
    # Fixture pages can be heavier than the calendar; allow enough time for a direct-link fetch.
    with urlopen(Request(HOST + path, headers={'User-Agent':'TITAN-CS2/1.0'}), timeout=12) as response:
        data = response.read(3_000_001)
    if len(data) > 3_000_000 or not data:
        raise ValueError('Ficha inaccesible')
    return html.fromstring(data.decode('utf-8', errors='replace'))


def sheet(doc, path, checked):
    names = doc.xpath('//*[@class="team1-gradient" or contains(@class,"team1-gradient ") or @class="team2-gradient" or contains(@class,"team2-gradient ")]//*[@class="teamName"]/text()')
    names = list(dict.fromkeys(names))
    timestamp = doc.xpath('//*[@class="timeAndEvent"]//*[@class="time"]/@data-unix')
    event = doc.xpath('//*[@class="timeAndEvent"]//a[contains(@href,"/events/")]/text()')
    info = ' '.join(doc.xpath('//*[contains(@class,"preformatted-text")]//text()'))
    fmt = re.search(r'Best of (\d+)', info, re.I)
    if len(names) != 2 or not timestamp or not fmt or not event:
        raise ValueError('Ficha incompleta')
    history, rosters = {}, {}
    for box in doc.xpath('//*[@data-past-matches-team]/*'):
        team = box.xpath('.//*[contains(@class,"past-matches-headline")]//a/text()')
        if team:
            history[team[0]] = list(dict.fromkeys(box.xpath('.//td[@class="past-matches-map"]/div/a/@href')))[:5]
    for box in doc.xpath('//*[@class="lineup standard-box"]'):
        team = box.xpath('.//a[starts-with(@href,"/team/")]/text()')
        if team:
            rosters[team[0]] = box.xpath('.//td//div[@class="text-ellipsis"]/text()')
    return dict(names=names, source=HOST+path, tournament=event[0], format='BO'+fmt[1],
                kickoff=datetime.fromtimestamp(int(timestamp[0])/1000,timezone.utc).isoformat(),
                checked=checked, rosters=rosters, history=history, team_ids={
                    a.text_content().strip():a.get('href').split('/')[2]
                    for a in doc.xpath('//*[@class="lineup standard-box"]//a[starts-with(@href,"/team/")]')
                    if re.fullmatch(r'/team/\d+/[a-z0-9-]+',a.get('href',''))})



def api_fixture(match, required, cutoff, bucket, diagnostics=None):
    """Authorized calendar API; token stays server-side and never enters evidence."""
    diagnostics = diagnostics if diagnostics is not None else []
    import os
    from urllib.parse import urlencode
    token = os.environ.get('PANDASCORE_TOKEN','').strip()
    if not token:
        logging.warning('T1 PandaScore: token not configured')
        diagnostics.append('PandaScore: token no configurado')
        return None
    endpoint = 'https://api.pandascore.co/csgo/matches'
    params = {'range[scheduled_at]':(cutoff-timedelta(days=1)).isoformat()+','+(cutoff+timedelta(days=1)).isoformat(), 'per_page':100}
    found = {}
    try:
        for page in range(1,6):
            query = urlencode(dict(params,page=page))
            req = Request(endpoint+'?'+query,headers={'Authorization':'Bearer '+token,'Accept':'application/json'})
            with urlopen(req,timeout=8) as response:
                raw = response.read(3_000_001)
            if len(raw)>3_000_000:
                raise ValueError('Response too large')
            rows = json.loads(raw)
            if not isinstance(rows,list):
                raise ValueError('Unexpected response')
            for row in rows:
                names = [v.get('opponent',{}).get('name','') for v in row.get('opponents',[])]
                if len(names)!=2 or {key(n) for n in names}!=required:
                    continue
                kickoff = parse_dt(row['scheduled_at'])
                fmt = 'BO'+str(row.get('number_of_games'))
                if kickoff!=cutoff or fmt not in FORMATS or row.get('status') in ('canceled','cancelled','postponed'):
                    continue
                event = ' / '.join(v.get('name','') for v in (row.get('league') or {},row.get('serie') or {},row.get('tournament') or {}) if v.get('name'))
                ident = row.get('id')
                if not event or not isinstance(ident,int):
                    continue
                found[ident] = dict(names=names,source=endpoint+'/'+str(ident),tournament=event,format=fmt,
                                    kickoff=kickoff.isoformat(),checked=datetime.now(timezone.utc).isoformat(),
                                    rosters={},history={},team_ids={},provider='PandaScore',provider_id=ident)
            if len(rows)<100:
                break
        else:
            logging.warning('T1 PandaScore: pagination limit reached; uniqueness not established')
            diagnostics.append('PandaScore: límite de páginas; no se pudo confirmar unicidad')
            return None
    except HTTPError as exc:
        logging.warning('T1 PandaScore: HTTP %s',exc.code)
        detail = 'token rechazado o vencido' if exc.code == 401 else 'acceso denegado' if exc.code == 403 else 'error HTTP'
        diagnostics.append(f'PandaScore: HTTP {exc.code} ({detail})')
        return None
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        logging.warning('T1 PandaScore: %s',type(exc).__name__)
        diagnostics.append('PandaScore: error de conexión o respuesta inválida ('+type(exc).__name__+')')
        return None
    logging.warning('T1 PandaScore candidates=%s',len(found))
    diagnostics.append('PandaScore: consulta completada; coincidencias exactas='+str(len(found)))
    return next(iter(found.values())) if len(found)==1 else None


def lookup(match, diagnostics=None):
    diagnostics = diagnostics if diagnostics is not None else []
    cutoff = parse_dt(match['cutoff'])
    names = [match['team_a'],match['team_b']]
    required = {key(n) for n in names}
    url = match.get('source_url','')
    if not isinstance(url,str) or url and not re.fullmatch(re.escape(HOST)+PATH,url):
        raise ValueError('Usa la URL completa de una ficha de partido de www.hltv.org.')
    bucket = int(time()//300)
    def matches(f):
        return ({key(n) for n in f['names']} == required and parse_dt(f['kickoff']) == cutoff
                and (not url or f['source']==url))
    saved = json.loads(SNAPSHOT.read_text())
    candidates = [url[len(HOST):]] if url else []
    if not url and matches(saved):
        candidates.append(saved['source'][len(HOST):])
    if not candidates:
        try:
            listing = read('/results' if cutoff < datetime.now(timezone.utc) else '/matches',bucket)
            for path in listing.xpath('//a/@href'):
                if re.fullmatch(PATH,path) and all(key(n) in key(path.split('/')[-1]) for n in names):
                    candidates.append(path)
            diagnostics.append('HLTV: calendario consultado; fichas candidatas='+str(len(set(candidates))))
        except ERRORS as exc:
            logging.warning('T1 HLTV listing: %s', exc)
            diagnostics.append('HLTV: calendario inaccesible ('+str(exc)[:100]+')')
    verified = []
    for path in list(dict.fromkeys(candidates))[:24]:
        try:
            record = sheet(read(path,bucket),path,datetime.now(timezone.utc).isoformat())
        except ERRORS as exc:
            logging.warning('T1 HLTV sheet %s: %s', path, exc)
            diagnostics.append('HLTV: ficha inaccesible ('+str(exc)[:100]+')')
            continue
        if matches(record):
            verified.append(record)
    if len(verified) == 1:
        diagnostics.append('HLTV: encuentro verificado por nombre, fecha y ficha')
        return verified[0]
    if len(verified) > 1:
        diagnostics.append('HLTV: varias fichas coinciden; se bloqueó la selección')
        return None
    if matches(saved):
        diagnostics.append('HLTV: coincidencia exacta con registro archivado')
        return saved
    if url:
        diagnostics.append('HLTV: la ficha directa no confirmó nombre, fecha y formato; se prueban otras fuentes')
    def alternate(name):
        slug = key(name)
        try:
            index = html.fromstring(second_source.fetch('/teams/'+second_source.ALIASES.get(slug,slug)+'/matches',bucket))
            dates = {(cutoff+timedelta(days=i)).strftime('%d-%m-%Y') for i in (-1,0,1)}
            paths = [p for p in dict.fromkeys(index.xpath('//a[starts-with(@href,"/matches/")]/@href'))
                     if re.fullmatch(r'/matches/[\w-]+',p) and any(p.endswith('-'+d) for d in dates)]
            return paths, None
        except ERRORS as exc:
            logging.warning('T1 BO3.gg index %s: %s',slug,exc)
            return [], str(exc)
    def alternate_sheet(path):
        try:
            doc = html.fromstring(second_source.fetch(path,bucket))
            for raw in doc.xpath('//script[@type="application/ld+json"]/text()'):
                data = json.loads(raw)
                events = data if isinstance(data,list) else data.get('@graph',[data])
                for event in events:
                    if not isinstance(event,dict) or event.get('@type')!='SportsEvent':
                        continue
                    sides = event.get('name','').split(' vs ')
                    if len(sides)!=2 or {key(n) for n in sides}!=required or event.get('url')!=second_source.HOST+path:
                        continue
                    kickoff = parse_dt(event['startDate'])
                    context = str(event.get('description',''))+' '+' '.join(e.text_content() for e in doc.xpath('//*[contains(@class,"match-format") or contains(@class,"best-of")]'))
                    formats = set(re.findall(r'\b(?:bo\s*|best.of.)([12357])\b',context,re.I))
                    if len(formats)!=1 or kickoff!=cutoff:
                        logging.warning('T1 BO3.gg mismatch %s kickoff=%s formats=%s',path,kickoff,sorted(formats))
                        continue
                    tournament = event.get('superEvent') or event.get('eventSeries')
                    if isinstance(tournament,dict):
                        tournament = tournament.get('name')
                    if not isinstance(tournament,str) or not tournament.strip():
                        labels = list(dict.fromkeys(v.strip() for v in doc.xpath('//a[contains(@href,"/tournaments/")]/text()') if v.strip()))
                        tournament = labels[0] if len(labels)==1 else None
                    if tournament:
                        return dict(names=sides,source=event['url'],tournament=tournament,format='BO'+formats.pop(),
                                    kickoff=kickoff.isoformat(),checked=datetime.now(timezone.utc).isoformat(),
                                    rosters={},history={},team_ids={})
        except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError) as exc:
            logging.warning('T1 BO3.gg sheet %s: %s',path,exc)
        return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        indexes = list(pool.map(alternate,names))
    paths = list(dict.fromkeys(p for group,_ in indexes for p in group))
    index_errors = [error for _,error in indexes if error]
    if index_errors:
        diagnostics.append('BO3.gg: error de acceso en índice de equipo ('+', '.join(index_errors)[:120]+')')
    else:
        diagnostics.append('BO3.gg: índices consultados; fichas candidatas='+str(len(paths)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        alternatives = [f for f in pool.map(alternate_sheet,paths[:12]) if f]
    logging.warning('T1 BO3.gg candidates=%s verified=%s',len(paths),len(alternatives))
    diagnostics.append('BO3.gg: fichas verificadas='+str(len(alternatives)))
    if len(alternatives)>1:
        diagnostics.append('BO3.gg: varias coincidencias; se bloqueó la selección')
        return None
    if alternatives:
        return alternatives[0]
    return api_fixture(match,required,cutoff,bucket,diagnostics)


def completed_score(fmt, scores):
    if fmt not in FORMATS or len(scores)!=2 or any(v<0 for v in scores):
        return False
    if fmt=='BO2':
        return sum(scores)==2
    target=int(fmt[2:])//2+1
    return max(scores)==target and min(scores)<target


def outcome(scores, side):
    return 'D' if scores[0]==scores[1] else 'W' if scores[side]>scores[1-side] else 'L'


def histories(fixture, match):
    names = [match['team_a'],match['team_b']]
    teams = {n:{'series':[],'mechanisms':[]} for n in names}
    cutoff = parse_dt(match['cutoff'])
    archive = json.loads(Path(__file__).with_name('nodwin_review.json').read_text())
    archived = (fixture['source']==archive['fixture'] and cutoff==parse_dt(archive['cutoff'])
                and {key(n) for n in names}=={key(n) for n in archive['teams']}
                and datetime.now(timezone.utc)>=parse_dt(archive['checked']))
    if archived:
        for name in names:
            teams[name]['series'] = archive['teams'][next(k for k in archive['teams'] if key(k)==key(name))]
        return teams
    bucket = int(time()//300)
    def previous(item):
        name,path = item
        try:
            doc=read(path,bucket)
            record=sheet(doc,path,datetime.now(timezone.utc).isoformat())
            sides=record['names']
            idx=[key(n) for n in sides].index(key(name))
            start=parse_dt(record['kickoff'])
            scores=[doc.xpath('//*[contains(@class,"team%d-gradient")]//*[@class="won" or @class="lost"]/text()'%(i+1)) for i in range(2)]
            if (not all(scores) or not completed_score(record['format'],[int(s[0]) for s in scores]) or not cutoff-timedelta(days=15)<=start<min(cutoff,parse_dt(record['checked']))
                    or (parse_dt(record['checked'])>=cutoff and start.date()>=cutoff.date())):
                return
            maps=[]
            for box in doc.find_class('mapholder'):
                labels=box.find_class('mapname')
                results=box.find_class('results-team-score')
                if labels and len(results)==2 and all(v.text_content().strip().isdigit() for v in results):
                    pair=[int(v.text_content().strip()) for v in results]
                    maps.append({'map':labels[0].text_content().strip().lower(),'score':pair if idx==0 else pair[::-1]})
            return name,dict(checked_at=record['checked'],maps=maps,id=path.split('/')[2],date=start.isoformat(),format=record['format'],
                             result=outcome([int(s[0]) for s in scores],idx),source=record['source'],opponent=sides[1-idx])
        except ERRORS:
            return
    items=[(name,path) for name in names for side,paths in fixture['history'].items() if key(name)==key(side) for path in paths]
    with ThreadPoolExecutor(max_workers=8) as workers:
        for row in workers.map(previous,items):
            if row:
                teams[row[0]]['series'].append(row[1])
    def check_secondary(name):
        rows = teams[name]['series']
        slug = re.sub(r'[^a-z0-9]+','-',name.casefold()).strip('-')
        ident=next((v for k,v in fixture.get('team_ids',{}).items() if key(k)==key(name)),None)
        if len(rows)<5 and ident and str(ident).isdigit():
            try:
                data,checked=fetch_index(HOST+'/results?team='+str(ident),bucket)
                for item in result_index(data):
                    day=parse_dt(item['date']+'T00:00:00+00:00')
                    # The index supplies only a UTC day. Admit complete interior days.
                    if not (cutoff-timedelta(days=15)).date()<day.date()<min(cutoff,parse_dt(checked)).date():
                        continue
                    if second_source.norm(name) not in item['teams'] or item['url']==fixture['source']:
                        continue
                    if any(r['source']==item['url'] for r in rows):
                        continue
                    side=item['teams'].index(second_source.norm(name))
                    rows.append(dict(id=item['url'].split('/')[-2],date=day.isoformat(),date_precision='day',
                                     checked_at=checked,format='BO3',source=item['url'],opponent=item['teams'][1-side],
                                     result='W' if item['scores'][side]==2 else 'L'))
                    if len(rows)>=5:
                        break
            except ERRORS:
                pass
        if not slug:
            return
        try:
            index = html.fromstring(second_source.fetch('/teams/'+second_source.ALIASES.get(slug,slug)+'/matches',bucket))
            paths = list(dict.fromkeys(index.xpath('//a[starts-with(@href,"/matches/")]/@href')))
        except ERRORS:
            return
        def check(path):
            try:
                body=second_source.fetch(path,bucket)
                doc=html.fromstring(body)
                events=json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])
                event=next(v for v in events if isinstance(v,dict) and v.get('@type')=='SportsEvent')
                sides=event['name'].split(' vs ')
                if len(sides)!=2 or event['url']!=second_source.HOST+path:
                    return
                side=[second_source.norm(v) for v in sides].index(second_source.norm(name))
                start=parse_dt(event['startDate'])
                end=parse_dt(event['endDate']) if event.get('endDate') else None
                checked=datetime.now(timezone.utc)
                if not cutoff-timedelta(days=15)<=start<min(checked,cutoff):
                    return
                if checked>=cutoff and (not end or not start<=end<cutoff):
                    return
                maps=[]
                for el in doc.find_class('c-match-score-map'):
                    label=el.getparent().find('a')
                    pair=list(map(int,re.findall(r'\d+',el.text_content())))
                    if label is not None and len(pair)==2 and max(pair)>=13 and pair[0]!=pair[1]:
                        maps.append(dict(map=label.text_content().strip().lower().replace('dust ii','dust2'),
                                         score=pair if side==0 else pair[::-1]))
                wins=sum(m['score'][0]>m['score'][1] for m in maps)
                score=[wins,len(maps)-wins]
                # Two played maps can also be an unfinished BO5.
                context=' '.join(str(event.get(k,'')) for k in ('name','description'))
                context+=' '+' '.join(e.text_content() for e in doc.xpath('//*[contains(@class,"match-format") or contains(@class,"best-of")]'))
                formats=set(re.findall(r'\b(?:bo\s*|best.of.)([12357])\b',context,re.I))
                if len(formats)!=1 or not completed_score('BO'+next(iter(formats)),score):
                    return
                return dict(id=path,date=start.isoformat(),checked_at=checked.isoformat(),format='BO'+next(iter(formats)),
                            result=outcome(score,0),source=event['url'],opponent=sides[1-side],maps=maps)
            except (OSError,ValueError,KeyError,IndexError,TypeError,StopIteration):
                return
        dates=[(cutoff-timedelta(days=i)).strftime('%d-%m-%Y') for i in range(16)]
        eligible=[p for p in paths if any(p.endswith('-'+d) for d in dates) and re.fullmatch(r'/matches/[\w-]+',p)]
        with ThreadPoolExecutor(max_workers=5) as pool:
            for row in pool.map(check,eligible[:8]):
                if not row:
                    continue
                peers=[r for r in rows if key(r['opponent'])==key(row['opponent']) and parse_dt(r['date']).date()==parse_dt(row['date']).date()]
                if not peers:
                    rows.append(row)
                elif len(peers)==1:
                    peer=peers[0]
                    if peer['source']==row['source']:
                        continue
                    if peer['result']!=row['result'] or (peer.get('maps') and peer['maps']!=row['maps']):
                        peer['conflict']=True
                    else:
                        peer['secondary_source']=row['source']
        teams[name]['series']=sorted((r for r in rows if not r.get('conflict')),key=lambda r:r['date'],reverse=True)[:5]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(check_secondary,names))
    return teams
