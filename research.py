"""Read public BLAST match pages on demand, retaining only dated CS2 evidence."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from time import time
from urllib.request import Request, urlopen

from titan import parse_dt

HOST = 'https://blast.tv'
TEAM = r'/cs/team/[0-9a-f]{8}/[a-z0-9-]+'
MATCH = r'/cs/tournaments/[a-z0-9-]+/match/[0-9a-f]{8}/[a-z0-9-]+'
STREAM = re.compile(r'streamController\.enqueue\(("(?:\\.|[^"\\])*")\)')


@lru_cache(maxsize=64)
def page(path, bucket):
    if path != '/cs/team' and not re.fullmatch(f'{TEAM}|{MATCH}', path):
        raise ValueError('Ruta de fuente inválida')
    with urlopen(Request(HOST + path, headers={'User-Agent': 'TITAN-CS2/1.0'}), timeout=8) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('Página demasiado grande')
    return data.decode()


def links(html, pattern):
    return list(dict.fromkeys(re.findall('href="(' + pattern + ')"', html)))


def records(html):
    """Decode selected public React Router records from its indexed JSON stream."""
    pool = []
    for raw in STREAM.findall(html):
        line = json.loads(raw).strip()
        if re.match(r'^P\d+:', line):
            line = line.partition(':')[2]
        if line.startswith('['):
            pool.extend(json.loads(line))
    def read(index, depth):
        if type(index) != int or not 0 <= index < len(pool) or depth < 0:
            return None
        item = pool[index]
        if isinstance(item, list):
            return [read(n, depth-1) for n in item if type(n) == int]
        if isinstance(item, dict):
            return {pool[int(k[1:])]: read(n, depth-1) for k, n in item.items() if k[1:].isdigit() and int(k[1:]) < len(pool)}
        return item
    for i, item in enumerate(pool):
        if isinstance(item, dict):
            keys = {pool[int(k[1:])] for k in item if k[1:].isdigit() and int(k[1:]) < len(pool)}
            if ('teamA' in keys and 'maps' in keys) or 'playerSteamId' in keys or {'players','fromDate','toDate'} <= keys:
                yield read(i, 4)


def detail(path, bucket):
    rows = list(records(page(path, bucket)))
    prefix = path.split('/')[-2]
    match = next((r for r in rows if str(r.get('id','')).startswith(prefix) and isinstance(r.get('scheduledAt'), str) and 'maps' in r), None)
    if not match:
        raise ValueError('Ficha incompleta')
    return match, [r for r in rows if r.get('matchId') == match['id'] and r.get('playerSteamId')]


def normalize(name):
    return re.sub(r'[^a-z0-9]', '', name.casefold())


def research(match):
    names = [match['team_a'], match['team_b']]
    cutoff = parse_dt(match['cutoff'])
    now = datetime.now(timezone.utc)
    if cutoff <= now:
        raise ValueError('La investigación automática prospectiva exige un encuentro futuro.')
    bucket = int(time() // 600)
    directory = links(page('/cs/team', bucket), TEAM)
    paths = []
    for name in names:
        candidates = [p for p in directory if normalize(p.split('/')[-1]) == normalize(name)]
        if len(candidates) != 1:
            raise ValueError('Equipo fuera del directorio disponible de BLAST: '+name)
        paths.append(candidates[0])
    with ThreadPoolExecutor(max_workers=5) as workers:
        pages = list(workers.map(lambda p: page(p, bucket), paths))
        listed = [links(html, MATCH) for html in pages]
        shared = set(listed[0]) & set(listed[1])
        # Discover the fixture using both team schedules, never a guessed match URL.
        def load(path):
            try:
                return path, detail(path, bucket)
            except (OSError, ValueError, KeyError, TypeError):
                return path, None
        all_paths = list(dict.fromkeys(p for items in listed for p in items[:10]))
        details = dict(workers.map(load, all_paths))
    team_ids = [path.split('/')[-2] for path in paths]
    def sides(m):
        return [(m.get(side) or {}).get('id','')[:8] for side in ('teamA','teamB')]
    candidates = [(p,item[0]) for p,item in details.items() if p in shared and item and set(sides(item[0])) == set(team_ids) and parse_dt(item[0]['scheduledAt']) == cutoff]
    if len(candidates) != 1:
        raise ValueError('BLAST no confirmó ambos equipos y la hora exacta. Revisa la hora de Colombia.')
    target, fixture = candidates[0]
    if fixture['type'] != 'BO3':
        raise ValueError('El formato confirmado queda fuera del alcance BO3.')
    teams, report = {}, {}
    for name, tid, html, paths_for_team, profile in zip(names,team_ids,pages,listed,paths):
        rosters = [r for r in records(html) if r.get('players') and isinstance(r.get('fromDate'),str) and r['fromDate'] <= now.date().isoformat() and not r.get('toDate')]
        roster = (rosters or [{}])[0].get('players',[])
        players = {str(p['ingameId']):p['nickname'] for p in roster if isinstance(p,dict) and p.get('ingameId') and p.get('nickname')}
        series = []
        conflicts = []
        for path in paths_for_team:
            item = details.get(path)
            if path == target or not item:
                continue
            m, stats = item
            if tid not in sides(m) or m['type'] != 'BO3':
                continue
            maps = [g for g in m.get('maps') or [] if isinstance(g,dict) and (g.get('teamAScore') or g.get('teamBScore'))]
            scores = [m.get('teamAScore'),m.get('teamBScore')]
            if 2 not in scores or len(maps) not in (2,3):
                continue
            if not all(isinstance(g,dict) and type(g.get('teamAScore')) is int and type(g.get('teamBScore')) is int and g['teamAScore'] != g['teamBScore'] for g in maps):
                continue
            map_wins = sum(g['teamAScore'] > g['teamBScore'] for g in maps)
            if scores != [map_wins,len(maps)-map_wins]:
                if cutoff-timedelta(days=15) <= parse_dt(m['scheduledAt']) <= now:
                    conflicts.append(HOST+path)
                continue
            start = parse_dt(m['scheduledAt'])
            # When BLAST omits map end times, the complete score was already
            # observable at collection, which itself must precede the fixture.
            end = max(parse_dt(g['endedAt']) for g in maps) if all(g.get('endedAt') for g in maps) else None
            if not cutoff-timedelta(days=15) <= start <= now or (end and not start <= end <= now):
                continue
            side = sides(m).index(tid)
            lines = {}
            for r in stats:
                nick = players.get(str(r['playerSteamId']))
                n = r.get('mapNumber')
                if nick and type(n) == int and 1 <= n <= len(maps) and type(r.get('kills')) is int and type(r.get('deaths')) is int:
                    lines.setdefault(nick,{})[n] = {k:r.get(k) for k in ('kills','deaths','adr','firstKills','utilityDamage')}
            series.append({'id':m['id'],'date':start.isoformat(),'finished_at':end.isoformat() if end else None,'format':'BO3','source':HOST+path,'result':'W' if scores[side]==2 else 'L','opponent':m[['teamB','teamA'][side]]['name'],'maps':[{'map':g['name'],'score':[g['teamAScore'],g['teamBScore']][::1 if side==0 else -1]} for g in maps],'players':lines})
        series.sort(key=lambda s:s['date'],reverse=True)
        series=series[:5]
        teams[name]={'series':series,'mechanisms':[]}
        deciders = [s for s in series if len(s['maps']) == 3]
        lost_openers = [s for s in series if s['maps'][0]['score'][0] < s['maps'][0]['score'][1]]
        observed = {
            'deciders': [sum(s['result']=='W' for s in deciders),len(deciders)],
            'comebacks': [sum(s['result']=='W' for s in lost_openers),len(lost_openers)]
        }
        report[name]={'observed':observed,'profile':HOST+profile,'score_conflicts':conflicts,'series':series,'player_series':{nick:sum(len(s['players'].get(nick,{}))==len(s['maps']) for s in series) for nick in players.values()}}
    return teams, {'source':HOST+target,'tournament':fixture['tournament']['name'],'stage':fixture['name'],'cutoff':cutoff.isoformat(),'retrieved':now.isoformat(),'teams':report,'unavailable_pages':sum(item is None for item in details.values())}


def automatic_input(match):
    from pathlib import Path
    # A dated pre-match snapshot remains usable only for the exact fixture it documents.
    snapshot_path = Path(__file__).with_name('reference_match.json')
    names = [match['team_a'], match['team_b']]
    if snapshot_path.exists():
        data = json.loads(snapshot_path.read_text())
        source_names = {normalize(n):n for n in data['teams']}
        if (set(map(normalize,names)) == set(source_names)
            and parse_dt(match['cutoff']) == parse_dt(data['cutoff'])
            and parse_dt(data['retrieved']) < parse_dt(data['cutoff'])):
            data['teams'] = {n:data['teams'][source_names[normalize(n)]] for n in names}
            data['cached_snapshot'] = True
            return {n:{'series':v['series'],'mechanisms':[]} for n,v in data['teams'].items()}, data
    return research(match)
