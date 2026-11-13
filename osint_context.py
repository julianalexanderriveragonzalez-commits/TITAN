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


def context(evidence, cutoff):
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
    return {'status':'PARCIAL','items':items,'sources':sources,
            'pending':['Disponibilidad y suplentes','Cambios de rol o preparación','Viajes, descanso y recuperación'],
            'scoring_effect':'Sin ponderación en el pronóstico'}
