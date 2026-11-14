"""Engine evidence is read from the pre-match dossier, never from client status flags."""
from statistics import mean, pstdev

ORDER = ('PVE','CCE','BMA','HFE','MSI','CIPI')


def chain(findings):
    rows=[]
    first=None
    for name in ORDER:
        finding=findings[name]
        status='BLOQUEADA' if first else finding['finding']
        rows.append(dict(finding,engine=name,status=status,blocked_by=first))
        if first is None and status!='COMPLETADA':
            first=name
    return rows


def verified(rows):
    return (isinstance(rows,list) and len(rows)==len(ORDER) and
            all(r.get('engine')==n and r.get('status')=='COMPLETADA' and
                r.get('finding')=='COMPLETADA' and not r.get('blocked_by') for r,n in zip(rows,ORDER)))


def review(report, groups, evidence=None):
    findings={}
    def record(name, status, detail, data):
        findings[name]=dict(finding=status,detail=detail,data=data)
    players={}
    alerts=[]
    responses=[]
    sources=[]
    full=len(groups)==2 and all(len({r['id'] for r in group})==5 for group in groups)
    for idx,group in enumerate(groups):
        team='AB'[idx]
        for slot in range(5):
            history=[(r['id'],r['player_ratings'][slot]) for r in sorted(group,key=lambda r:r['date'])]
            if not history:
                continue
            values=[value for _,value in history]
            lowest=min(values)
            worst_id=next(s for s,v in history if v==lowest)
            worst=next(r for r in group if r['id']==worst_id)
            players[f'{team}{slot+1}']=dict(series=len(history),minimum=lowest,
                deviation=round(pstdev(values),3),changes=sum(a!=b for a,b in zip(values,values[1:])),
                worst_series=worst['id'],team_mean=round(mean(worst['player_ratings']),3),
                peers_mean=round(mean(worst['player_ratings'][:slot]+worst['player_ratings'][slot+1:]),3))
        for r in group:
            sources.append({'team':team,'series':r['id'],'urls':r['sources']})
            low=[i+1 for i,v in enumerate(r['player_ratings']) if v<0.80]
            if low:
                alerts.append(dict(team=team,series=r['id'],players=low,
                                   traded_recoveries=r['counts'].get('traded_recovery',0)))
            responses.append(dict(team=team,series=r['id'],events=r['counts'].get('stress',0),
                                  responses=r['counts'].get('response',0),situations=r['situations']))
    record('PVE','COMPLETADA' if full else 'PARCIAL' if players else 'PENDIENTE',
           'Rating por jugador: cambios entre series, dispersión y piso comparado con sus cuatro compañeros.',players)
    record('CCE','COMPLETADA' if full and not alerts else 'PARCIAL' if sources else 'PENDIENTE',
           ('Sin caída inferior a 0,80 en las cincuenta observaciones.' if full and not alerts else
            'Los intercambios agregados no identifican qué compañero compensó una caída.'),alerts)
    adjustments=[]
    for idx,group in enumerate(groups):
        examples=[]
        for r in group:
            for first,second in zip(r['maps'],r['maps'][1:]):
                m1,w1,n1=first
                m2,w2,n2=second
                if n1>=3 and n2>=3 and 2*w1<n1 and 2*w2>n2:
                    examples.append(dict(series=r['id'],opponent=r['opponent'],maps=[m1,m2],
                                         before=[w1,n1],after=[w2,n2]))
        adjustments.append(examples)
    repeated=[]
    for group in groups:
        by_context={}
        for r in group:
            for context,events in r['recovery_sequences'].items():
                # A missed 4v5 without a trade, followed in the same situation
                # by two recovered 4v5s with traded kills.
                if any(events[i:i+3]==[(0,False),(1,True),(1,True)] for i in range(len(events)-2)):
                    by_context.setdefault(context,[]).append({'series':r['id'],'opponent':r['opponent']})
        repeated.append([{'context':list(k),'examples':rows} for k,rows in by_context.items()
                         if len({x['opponent'] for x in rows})>=2])
    record('BMA','COMPLETADA' if full and all(repeated) else 'PARCIAL' if any(groups) else 'PENDIENTE',
           'Contrasta recuperación entre mapas y repetición de intercambios tras fallar un 4v5, por mapa, lado y equipamiento. No atribuye intención.',
           {'map_changes':adjustments,'repeated':repeated})
    categories=('lost_advantage','comeback','close')
    hfe_complete=full and all(all(sum(r['situations'][k][0] for r in group)>0 for k in categories) for group in groups)
    record('HFE','COMPLETADA' if hfe_complete else 'PARCIAL' if responses else 'PENDIENTE',
           'Respuesta en la ronda siguiente tras perder un 5v4, ceder una ventaja de tres rondas o llegar a 11–11 o más en empate.',responses)
    osint=report.get('osint',{})
    msi={'fase':next((s['text'] for s in osint.get('items',[]) if s['category']=='Encuentro y fase' and s['scope']=='PREPARTIDO'),None),
         'formato':'BO3' if report.get('identity') else None,'consecuencia de perder':None,'recompensa de ganar':None,
         'modalidad':None,'experiencia comparable':None,'intervalo entre series':osint.get('rest_hours') or None}
    if msi['fase'] and evidence:
        fmt=evidence.get('stage_format') or ''
        if fmt.startswith('single-elim'):
            msi['consecuencia de perder']='Eliminación'
            msi['recompensa de ganar']='Título' if evidence['stage'].casefold()=='grand final' else 'Avance en el cuadro'
        mode=evidence.get('modality')
        if isinstance(mode,str) and mode.lower() in ('lan','online'):
            msi['modalidad']=mode
        if fmt:
            msi['experiencia comparable']={slot:sum(s.get('stage_format')==fmt for s in team['series'])
                for slot,team in zip(('A','B'),evidence['teams'].values())}
    record('MSI','COMPLETADA' if all(msi.values()) and len(msi['intervalo entre series'])==2 else 'PARCIAL' if any(msi.values()) else 'PENDIENTE',
           'Cada dimensión exige respaldo fechado. El intervalo de calendario aproxima la recuperación.',msi)
    record('CIPI','PENDIENTE','Requiere los cinco motores previos y T1–T5 verificados.',{})
    return findings,sources
