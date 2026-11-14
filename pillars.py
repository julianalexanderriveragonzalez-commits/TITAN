"""Independent evidence coverage, distinct from sequential task authorization."""
from urllib.parse import urlsplit
from datetime import datetime


def audit_pillars(report):
    v=report['volatility'] if 'volatility' in report else {}
    stress=report['robustness']
    multi=report.get('multisource',{})
    rows=multi.get('series',[])
    context=report.get('osint',{})
    network=report.get('source_network',{})
    floor=network.get('floor',{})
    cipi=report.get('cipi_review',{})
    counts=report.get('casefile',{}).get('observations_at_cutoff',0)
    documentary=report.get('stage_findings',{})
    verdict=report['verdict']
    cutoff=verdict['cutoff']
    def parse_dt(value):
        return datetime.fromisoformat(value.replace("Z","+00:00"))
    refs=[(r.get(key),r.get(time)) for r in rows for key,time in
          [('primary','primary_checked'),('secondary','secondary_checked')]]
    primary=[(r.get('primary'),r.get('primary_checked')) for r in rows]
    osint=[(r.get('source'),r.get('checked')) for r in context.get('items',[])]
    ratings=[(r.get('source'),r.get('checked')) for r in floor.get('series',[])]
    def sources(records):
        return [{'url':url,'checked':at,'scope':'PREPARTIDO' if parse_dt(at)<parse_dt(cutoff) else 'POSTERIOR'}
                for url,at in dict.fromkeys(records) if url and at and urlsplit(url).scheme=='https']
    blind_sources=[]
    if report.get('fixture_source') and report.get('identity',{}).get('primary_checked'):
        blind_sources=[(report['fixture_source'],report['identity']['primary_checked'])]
    result=[]
    unknown='Efecto individual sin medir.'
    def add(name,status,observation,gap,impact,records):
        result.append(dict(id=len(result)+1,name=name,status=status,observation=observation,
                           gap=gap,impact=impact,sources=sources(records)))
    add('Ventana y participación','COMPLETADA' if counts==50 and documentary.get('T2_ventana_15_dias')=='COMPLETADA' else 'PARCIAL',
        f'{counts}/50 observaciones individuales documentadas al corte. Ventana de 15 días aplicada.',
        'Faltan observaciones por jugador.' if counts<50 else 'Consultar el detalle por jugador.',
        'La muestra insuficiente impide autorizar CIPI.' if counts<50 else unknown,primary)
    confirmed=multi.get('confirmed_before',0)
    add('Investigación multifuente','PARCIAL' if rows else 'PENDIENTE',
        f'{confirmed}/{len(rows)} antecedentes corroborados al corte. {multi.get("confirmed_review",0)} en la última revisión.',
        'La independencia de publicaciones con títulos distintos requiere rastrear su origen.',
        'T3 impide autorizar CIPI.' if documentary.get('T3_multifuente')!='COMPLETADA' else unknown,refs)
    add('OSINT y conducta competitiva','PARCIAL' if any(x['scope']=='PREPARTIDO' for x in sources(osint)) else 'PENDIENTE',
        'Contexto pendiente: '+', '.join(context.get('pending',[])) if context.get('pending') else 'Ver cobertura de contexto y boletines.',
        'Cambios de función y declaraciones requieren contraste documental.',unknown,osint)
    add('Contradicción material','PARCIAL' if v else 'PENDIENTE',
        v.get('strongest','Sin revisión documental.'),'Falta valorar el efecto de cada objeción por separado.',
        'CIPI perdió respaldo en escenarios de estrés.' if cipi.get('side') and not cipi.get('survives') else unknown,refs)
    worst=min((r['margin'] for r in stress['withdrawals']),default=None)
    impact=(f"Margen del indicador {stress['base_margin']:+.2f}; menor margen al retirar una observación {worst:+.2f}."
            if worst is not None else 'Sin retirada evaluable.')
    tipping=v.get('tipping',{})
    if tipping.get('state')=='INVERSIÓN':
        impact+=f" Escenario adverso con {len(tipping['changes'])} cambio(s): margen {tipping['margin']:+.2f}."
    add('Volatilidad','PARCIAL' if worst is not None or cipi.get('trials') else 'PENDIENTE',
        f"{len(stress['withdrawals'])} retiradas del indicador y {len(cipi.get('trials',[]))} ensayos CIPI.",
        'Falta aislar la dependencia por estrella, mapa y perfil rival.',impact,primary)
    add('Anonimato','PARCIAL','Cálculo por alias A/B. T9 '+report['identity_release']['status']+'.',
        'La vista documental conserva identidades.','Base de la elección: '+report['selection_basis']+'.',blind_sources)
    n=floor.get('prematch_ratings',0)
    add('Piso colectivo','PARCIAL' if n else 'PENDIENTE',
        f"{n} ratings al corte, {floor.get('prematch_alerts',0)} alertas bajo 0,80. Última revisión: {floor.get('review_ratings',0)} ratings.",
        'Falta atribuir la compensación a jugadores y rondas concretos.',unknown,ratings)
    causal=report.get('casefile',{}).get('causal',{}).get('prematch',{})
    add('Declaraciones y factor humano','PARCIAL' if causal.get('rounds') else 'PENDIENTE',
        f"{causal.get('rounds',0)} observaciones de ronda disponibles al corte. Sin cruce automático de declaraciones.",
        'Falta vincular una declaración fechada con una conducta contrastable.',unknown,osint)
    for p in result:
        p['cutoff']=cutoff
        p['scope']=('RECONSTRUCCIÓN RETROSPECTIVA' if verdict['timing']=='RETROSPECTIVO' else 'EMISIÓN PREPARTIDO')
    return result
