"""Public match results and regional press; preserve the time of observation."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from time import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from lxml import html
from second_source import norm
from collective_floor import collect as collect_floor, compensation_cases
from titan import parse_dt

REGIONS=('dust2.us','dust2.dk','dust2.in','dust2.com.br')
TEAM_IDS={'vitality':9565,'mouz':4494}
HLTV='https://www.hltv.org'


@lru_cache(maxsize=30)
def fetch(url,bucket):
    with urlopen(Request(url,headers={'User-Agent':'TITAN-CS2/1.0'}),timeout=5) as response:
        data=response.read(2500001)
    if len(data)>2500000:raise ValueError('Fuente demasiado grande')
    return data,datetime.now(timezone.utc).isoformat()


def result_index(data):
    out={}
    for el in html.fromstring(data).find_class('result-con'):
        href=el.xpath('./a/@href')
        if not href or not re.fullmatch(r'/matches/\d+/[a-z0-9-]+',href[0]):continue
        names=[norm(n.text_content()) for n in el.find_class('team')]
        score=el.find_class('result-score')
        fmt=el.find_class('map-text')
        if len(names)!=2 or not score or not fmt or fmt[0].text_content().strip().lower()!='bo3':continue
        nums=re.fullmatch(r'\s*([012])\s*-\s*([012])\s*',score[0].text_content())
        if not nums:continue
        scores=list(map(int,nums.groups()))
        if max(scores)!=2 or min(scores)>1:continue
        stamp=el.get('data-zonedgrouping-entry-unix','')
        if not stamp.isdigit():continue
        date=datetime.fromtimestamp(int(stamp)/1000,timezone.utc).date().isoformat()
        out[href[0].split('/')[2]]={'teams':names,'scores':scores,'date':date,'url':HLTV+href[0]}
    if not out:raise ValueError('Sin resultados BO3 legibles')
    return list(out.values())


def reconcile(name,series,index,checked,cutoff):
    candidates=[m for m in index if m['date']==parse_dt(series['date']).date().isoformat()
                and set(m['teams'])=={norm(name),norm(series['opponent'])}]
    row={'team':name,'opponent':series['opponent'],'date':series['date'],'checked':checked,
         'before':parse_dt(checked)<cutoff,'state':'SIN COINCIDENCIA'}
    if len(candidates)!=1:
        if candidates:row['state']='COINCIDENCIA AMBIGUA'
        return row
    match=candidates[0]
    scores=match['scores'][::1 if match['teams'][0]==norm(name) else -1]
    expected=[sum(m['score'][0]>m['score'][1] for m in series['maps']),
              sum(m['score'][0]<m['score'][1] for m in series['maps'])]
    row.update(score=scores,expected=expected,url=match['url'],
               state='MARCADOR CORROBORADO' if scores==expected else 'CONTRADICCIÓN')
    return row


def regional(domain,names,cutoff,bucket):
    url='https://www.'+domain+'/rss'
    try:
        data,checked=fetch(url,bucket)
        channel=ElementTree.fromstring(data).find('channel')
        if channel is None:raise ValueError('Formato desconocido')
        items=[];seen=set()
        for el in channel.findall('item')[:80]:
            title=(el.findtext('title') or '').strip()
            link=el.findtext('link') or ''
            if urlsplit(link).scheme!='https' or urlsplit(link).hostname not in (domain,'www.'+domain):continue
            if not any(re.search(r'(?<!\w)'+re.escape(n)+r'(?!\w)',title,re.I) for n in names):continue
            try:date=parsedate_to_datetime(el.findtext('pubDate') or '')
            except (TypeError,ValueError,OverflowError):continue
            if date.tzinfo is None or not cutoff-timedelta(days=15)<=date<cutoff or date>parse_dt(checked):continue
            if title.casefold() in seen:continue
            seen.add(title.casefold())
            items.append({'title':title,'url':link,'published':date.isoformat()})
        return {'name':domain,'url':url,'checked':checked,'state':'CONSULTADA','items':items,'before':parse_dt(checked)<cutoff}
    except (OSError,ValueError,ElementTree.ParseError):
        return {'name':domain,'url':url,'state':'ACCESO LIMITADO','items':[],'checked':datetime.now(timezone.utc).isoformat()}


def collect(evidence,cutoff):
    names=list(evidence['teams']);bucket=int(time()//900)
    snapshot=json.loads(Path(__file__).with_name('hltv_snapshot.json').read_text())
    def results(name):
        ident=TEAM_IDS.get(norm(name))
        query='team='+str(ident) if ident else 'startDate='+(cutoff-timedelta(days=15)).date().isoformat()+'&endDate='+cutoff.date().isoformat()
        url=HLTV+'/results?'+query
        known=snapshot['teams'].get(norm(name))
        from_snapshot=known and snapshot['fixture']==evidence['source'] and parse_dt(snapshot['cutoff'])==cutoff
        try:
            if from_snapshot:
                index,checked=known,snapshot['checked']
            else:
                data,checked=fetch(url,bucket)
                index=result_index(data)
            rows=[reconcile(name,s,index,checked,cutoff) for s in evidence['teams'][name]['series']]
            return {'name':name,'url':url,'state':'CONSULTADA','checked':checked,'snapshot':bool(from_snapshot),'series':rows}
        except (ValueError,OSError,OverflowError):
            return {'name':name,'url':url,'state':'ACCESO LIMITADO','checked':datetime.now(timezone.utc).isoformat(),'series':[]}
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs=[pool.submit(results,n) for n in names]
        archived=snapshot['fixture']==evidence['source'] and parse_dt(snapshot['cutoff'])==cutoff
        news=[] if archived else [pool.submit(regional,d,names,cutoff,bucket) for d in REGIONS]
        network={'hltv':[j.result() for j in jobs],'regional':snapshot['regional'] if archived else [j.result() for j in news], 'archived':archived}
    network['floor']=collect_floor(network,cutoff,snapshot.get('series_ratings',{}) if archived else None,lambda url:fetch(url,bucket))
    compensation_cases(network['floor'],evidence)
    return network
