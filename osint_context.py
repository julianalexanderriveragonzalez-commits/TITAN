"""T4. Keep public context separate from the sporting score."""
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from time import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from xml.etree import ElementTree

from titan import parse_dt

FEED = 'https://www.hltv.org/rss/news'


@lru_cache(maxsize=2)
def headlines(bucket):
    try:
        with urlopen(Request(FEED, headers={'User-Agent':'TITAN-CS2/1.0'}), timeout=4) as response:
            body = response.read(750001)
        if len(body)>750000:
            raise ValueError('oversized feed')
        root = ElementTree.fromstring(body)
        if root.find('channel') is None:
            raise ValueError('unrecognized feed')
        items = [{key: (item.findtext(tag) or '').strip() for key,tag in
                  [('title','title'),('published','pubDate'),('url','link')]}
                 for item in root.findall('./channel/item')[:100]]
        state = 'CONSULTADA'
    except (OSError,ValueError,ElementTree.ParseError):
        items, state = [], 'ACCESO LIMITADO'
    return state, datetime.now(timezone.utc).isoformat(), items


def context(evidence, cutoff, network=None):
    retrieved = evidence['retrieved']
    historical = datetime.now(timezone.utc) >= cutoff
    items = [{'category':'Encuentro y fase','text':evidence['tournament']+' · '+evidence['stage'],
              'source':evidence['source'],'checked':retrieved,'published':None,
              'scope':'PREPARTIDO' if parse_dt(retrieved)<cutoff else 'RETROSPECTIVA'}]
    sources=[{'name':'BLAST · ficha del encuentro','state':'CONSULTADA','checked':retrieved}]
    if historical:
        sources.append({'name':'HLTV · noticias','state':'SIN CAPTURA PREPARTIDO DEL BOLETÍN','checked':None})
    else:
        state, checked, entries = headlines(int(time()//600))
        sources.append({'name':'HLTV · noticias','state':state,'checked':checked})
        names = list(evidence['teams'])
        seen=set()
        for entry in entries:
            link=urlsplit(entry['url'])
            if link.scheme!='https' or link.hostname not in ('hltv.org','www.hltv.org'):
                continue
            article=re.fullmatch(r'/news/(\d+)/[\w-]+/?',link.path)
            if not article or article[1] in seen:
                continue
            try:
                published=parsedate_to_datetime(entry['published'])
                if published.tzinfo is None or not cutoff-timedelta(days=15)<=published<=parse_dt(checked) or published>=cutoff:
                    continue
            except (TypeError,ValueError,OverflowError):
                continue
            if not any(re.search(r'(?<!\w)'+re.escape(n)+r'(?!\w)',entry['title'],re.I) for n in names):
                continue
            seen.add(article[1])
            items.append({'category':'Titular relacionado · pendiente de validar','text':entry['title'],
                          'source':entry['url'],'checked':checked,'published':published.isoformat(),
                          'scope':'PREPARTIDO' if parse_dt(checked)<cutoff else 'RETROSPECTIVA'})
    for feed in (network or {}).get('regional',[]):
        sources.append({'name':feed['name'],'state':feed['state'],'checked':feed.get('checked')})
        for entry in feed.get('items',[]):
            if entry.get('duplicate') or not feed.get('before'):
                continue
            items.append({'category':'Titular relacionado · pendiente de validar','text':entry['title'],
                          'source':entry['url'],'checked':feed['checked'],'published':entry['published'],
                          'scope':'PREPARTIDO'})
    pending=[]
    rest={}
    for name,team in evidence['teams'].items():
        lineup=team.get('fixture_lineup_evidence',{})
        roster={n.casefold() for n in team.get('player_series',{})}
        if not (len(roster)==5 and roster=={n.casefold() for n in lineup.get('players',[])}
                and lineup.get('source')==evidence['source'] and lineup.get('checked_at')
                and parse_dt(lineup['checked_at'])<cutoff):
            pending.append(name+' · quinteto sin confirmar')
        rows=team.get('series',[])
        if not rows or parse_dt(retrieved)>=cutoff:
            pending.append(name+' · sin calendario capturado al corte')
            continue
        latest=max(rows,key=lambda r:parse_dt(r['date']))
        end=latest.get('finished_at')
        if not end or not parse_dt(latest['date'])<=parse_dt(end)<=parse_dt(retrieved):
            pending.append(name+' · falta hora final de la última serie')
        else:
            rest[name]=round((cutoff-parse_dt(end)).total_seconds()/3600,2)
            items.append({'category':'Intervalo entre series documentadas','text':name+' · '+str(rest[name])+' h',
                          'source':latest['source'],'checked':retrieved,'published':end,'scope':'PREPARTIDO'})
    if not any((s['name'].startswith('HLTV') or s['name'].startswith('dust2.') or s['name']=='esportsinsider.com') and s['state']=='CONSULTADA' and s['checked']
               and parse_dt(s['checked'])<cutoff for s in sources):
        pending.append('Boletín público sin consulta previa al corte')
    for item in items:
        if item['category'].startswith('Titular') and any(re.search(r'(?<!\w)'+re.escape(n)+r'(?!\w)',item['text'],re.I) for n in evidence['teams']) and re.search(
                r'roster|stand.in|substitut|bench|injur|illness|role swap|visa',item['text'],re.I):
            pending.append('Contrastar cambio anunciado: '+item['text'])
    return {'status':'PARCIAL' if pending or len(rest)!=2 else 'COMPLETADA',
            'items':items,'sources':sources,'pending':pending,'rest_hours':rest,
            'scoring_effect':'LOG utiliza el intervalo entre series conocidas. Viajes, descanso efectivo y estados personales quedan sin inferir.'}
