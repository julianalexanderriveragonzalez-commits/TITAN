"""Resolve public HLTV fixtures without an organizer or team directory."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from time import time
from urllib.request import Request, urlopen

from lxml import html
from titan import parse_dt

HOST = 'https://www.hltv.org'
PATH = r'/matches/\d{5,10}/[a-z0-9-]+'
ERRORS = (OSError, ValueError, IndexError, OverflowError)
SNAPSHOT = Path(__file__).with_name('nodwin_fixture.json')


def key(name):
    return ''.join(c for c in name.casefold() if c.isalnum())


@lru_cache(maxsize=96)
def read(path, bucket):
    if path not in ('/matches', '/results') and not re.fullmatch(PATH, path):
        raise ValueError('Ruta HLTV inválida')
    with urlopen(Request(HOST + path, headers={'User-Agent':'TITAN-CS2/1.0'}), timeout=4) as response:
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
            history[team[0]] = list(dict.fromkeys(box.xpath('.//td[@class="past-matches-map"]/div/a[translate(text(),"BO","bo")="bo3"]/@href')))[:5]
    for box in doc.xpath('//*[@class="lineup standard-box"]'):
        team = box.xpath('.//a[starts-with(@href,"/team/")]/text()')
        if team:
            rosters[team[0]] = box.xpath('.//td//div[@class="text-ellipsis"]/text()')
    return dict(names=names, source=HOST+path, tournament=event[0], format='BO'+fmt[1],
                kickoff=datetime.fromtimestamp(int(timestamp[0])/1000,timezone.utc).isoformat(),
                checked=checked, rosters=rosters, history=history)


def lookup(match):
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
        except ERRORS:
            pass
    for path in list(dict.fromkeys(candidates))[:6]:
        try:
            record = sheet(read(path,bucket),path,datetime.now(timezone.utc).isoformat())
        except ERRORS:
            continue
        if matches(record):
            return record
    if matches(saved):
        return saved
    return None


def histories(fixture, match):
    names = [match['team_a'],match['team_b']]
    teams = {n:{'series':[],'mechanisms':[]} for n in names}
    cutoff = parse_dt(match['cutoff'])
    if datetime.now(timezone.utc)>=cutoff:
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
            if (not all(scores) or sorted(int(s[0]) for s in scores) not in ([0,2],[1,2])
                    or record['format']!='BO3' or not cutoff-timedelta(days=15)<=start<parse_dt(record['checked'])<cutoff):
                return
            return name,dict(id=path.split('/')[2],date=start.isoformat(),format='BO3',
                             result='W' if int(scores[idx][0])==2 else 'L',source=record['source'],opponent=sides[1-idx])
        except ERRORS:
            return
    items=[(name,path) for name in names for side,paths in fixture['history'].items() if key(name)==key(side) for path in paths]
    with ThreadPoolExecutor(max_workers=8) as workers:
        for row in workers.map(previous,items):
            if row:
                teams[row[0]]['series'].append(row[1])
    return teams
