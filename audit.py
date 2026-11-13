"""Descriptive diagnostics. A coverage check never certifies an unobserved mechanism."""
from collections import Counter
from pathlib import Path
import json

from titan import _score_team, blind_evidence, parse_dt
from second_source import enrich, norm


def indicators(team):
    counts=Counter()
    observations={nick:[] for nick in team['player_series']}
    map_history=[]
    for s in team['series']:
        v=s.get('verification',{})
        if v.get('state')!='CORROBORADA':continue
        counts['confirmed']+=1
        for nick in observations:
            line=next((stats for n,stats in v.get('players',{}).items() if norm(n)==norm(nick)),None)
            if line:
                observations[nick].append({'date':s['date'],'opponent':s['opponent'],'source':v['source'],**line})
        side=v['side']
        for mapname,rr in v.get('rounds',{}).items():
            counts['maps']+=1
            rows=[pair[side] for pair in rr]
            counts['rounds']+=len(rows)
            for i,(r,pair) in enumerate(zip(rows,rr)):
                if r['first_kills']==1 and pair[1-side]['first_kills']==0:
                    counts['opens']+=1
                    counts['converted']+=r['win']
                if r['first_death']==1 and r['first_kills']==0:
                    counts['lost_open']+=1
                    counts['recovered']+=r['win']
                if type(r['trade_kills'])==int:counts['trades']+=r['trade_kills']
                enemy=pair[1-side]['equipment_value']
                if type(enemy)==int and type(r['equipment_value'])==int and 0<r['equipment_value']<enemy:
                    counts['down_buy']+=1
                    counts['down_buy_wins']+=r['win']
                # First response to three losses, on the same side of the map.
                prev=rows[max(i-3,0):i]
                if len(prev)==3 and all(p['team_side']==r['team_side'] and p['win']==0 for p in prev) and (i==3 or rows[i-4]['win'] or rows[i-4]['team_side']!=r['team_side']):
                    counts['shock']+=1
                    counts['response']+=r['win']
            map_history.append({'map':mapname,'rival':s['opponent'],'source':v['source'],'rounds':len(rr)})
    return {'counts':dict(counts),'players':observations,'maps':map_history}


def run(report,payload,evidence):
    retro=False
    if evidence.get('cached_snapshot'):
        f=Path(__file__).with_name('reference_postmatch.json')
        if f.exists():
            extra=json.loads(f.read_text())
            if extra['source']==evidence['source'] and extra['cutoff']==evidence['cutoff']:
                retro=parse_dt(extra['checked'])>=parse_dt(evidence['cutoff'])
                evidence['second_source_checked']=extra['checked']
                for name,t in evidence['teams'].items():
                    for s in t['series']:
                        key=next((k for k in extra['series'] if k.split('|')[1]==s['id'] and norm(k.split('|')[0])==norm(name)),None)
                        if key:s['verification']=extra['series'][key]
    else:
        enrich(evidence)
        retro=parse_dt(evidence['second_source_checked'])>=parse_dt(evidence['cutoff'])
    stats={n:indicators(t) for n,t in evidence['teams'].items()}
    names=list(payload['teams'])
    cutoff=parse_dt(payload['match']['cutoff'])
    blind_teams = [blind_evidence(payload['teams'][n]) for n in names]
    scores=[_score_team(t,cutoff)[0] for t in blind_teams]
    direction=lambda x:(x>0)-(x<0)
    base=direction(scores[0]-scores[1])
    retained=trials=0
    for i,n in enumerate(names):
        data=blind_teams[i]
        for j in range(len(data['series'])):
            revised=dict(data,series=data['series'][:j]+data['series'][j+1:])
            pair=scores.copy();pair[i]=_score_team(revised,cutoff)[0]
            trials+=1
            retained+=direction(pair[0]-pair[1])==base
    count=lambda k:sum(v['counts'].get(k,0) for v in stats.values())
    samples=sum(min(5,len({r['source'] for r in rows})) for t in stats.values() for rows in t['players'].values())
    conflicts=sum(len(t.get('score_conflicts',[]))+sum(s.get('verification',{}).get('state')=='CONTRADICCIÓN' for s in t['series']) for t in evidence['teams'].values())
    total=sum(len(t['series']) for t in evidence['teams'].values())
    deciders=sum(t['observed']['deciders'][1] for t in evidence['teams'].values())
    checks={}
    def check(k,state,why):
        checks[k]={'estado':state,'detalle':why}
    check('coherencia_direccional','COMPLETADA' if base else 'SIN SEÑAL','Selección consistente con el signo del indicador.' if base else 'Empate del indicador.')
    check('piso_colectivo_cce','PARCIAL' if samples else 'SIN DATOS',f'{samples}/50 fichas individuales de segunda fuente. El umbral 0,80 exige ratings comparables de serie.')
    check('transferibilidad','PARCIAL' if count('maps') else 'SIN DATOS','Rivales identificados por mapa. Falta demostrar la repetición del mecanismo ante estilos equivalentes.')
    check('rutas_bo3','PARCIAL' if total else 'SIN DATOS',f'{total}/10 series con secuencia de mapas.')
    check('estres_competitivo','PARCIAL',f"Fase del cruce: {evidence['stage']}. Faltan dimensiones del MSI.")
    check('robustez_retirada','COMPLETADA' if trials and base else 'SIN SEÑAL',f'El indicador conserva su dirección en {retained}/{trials} retiradas individuales de serie.')
    check('auditoria_sin_contaminacion','PARCIAL' if retro else 'COMPLETADA','Segunda revisión posterior, separada del pronóstico previo.' if retro else 'Consulta documental anterior al corte.' if evidence.get('second_source_checked') else 'Solo hay consulta primaria.')
    check('ser_recuperacion_extrema','PARCIAL' if count('shock') else 'SIN DATOS',f"{count('response')}/{count('shock')} primeras respuestas ganadas tras tres derrotas seguidas del mismo lado.")
    check('ame_adaptacion','PARCIAL' if count('rounds') else 'SIN DATOS','Cambios de resultado por ronda observables; decisiones tácticas y comunicación requieren evidencia adicional.')
    check('dme_mapa_decisivo','PARCIAL' if deciders else 'SIN DATOS',f'{deciders} terceros mapas en las series admitidas.')
    check('vsr_vetos','SIN DATOS','Faltan secuencias verificadas de veto y contraste con/sin veto.')
    check('ecc_contradiccion','ALERTA' if conflicts else 'PARCIAL',f'{conflicts} discrepancias detectadas; {count("confirmed")}/{total} series con marcadores coincidentes en dos fuentes.')
    cipi={}
    for index, metrics in enumerate(stats.values()):
        c=metrics['counts']
        players=metrics['players']
        cipi[['Equipo A','Equipo B'][index]]={
            'IND': f"{sum(len(v) for v in players.values())} observaciones con K-D y ADR",
            'CCE': 'Faltan rating de serie comparable, función y compensación',
            'STR': f"{c.get('converted',0)}/{c.get('opens',0)} aperturas convertidas",
            'ADP': f"{c.get('response',0)}/{c.get('shock',0)} respuestas tras tres pérdidas",
            'LOG': 'Pendiente de documentación de viajes y recuperación',
            'OPP': f"{len({s['opponent'] for s in evidence['teams'][list(evidence['teams'])[index]]['series']})} rivales documentados; comparación de estilos pendiente"
        }
    return {'cipi_diagnostic':cipi,'controls':checks,'teams':stats,'retrospective':retro,'sample':samples,'series':total,'confirmed':count('confirmed'),'rounds':count('rounds'),'maps':count('maps'),'withdrawals':[retained,trials]}
