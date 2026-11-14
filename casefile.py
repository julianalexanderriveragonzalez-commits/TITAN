"""Join T1–T4 into an inspectable dossier. Late evidence stays outside the verdict."""
from titan import parse_dt, window_rows
from causal import build_causal
from pathlib import Path
import json


def build_casefile(report, evidence):
    cutoff=parse_dt(report['match']['cutoff'])
    by_source={(r['team'],r['primary']):r for r in report['multisource']['series']}
    teams={}
    observed=0
    for slot, name in zip(('Equipo A','Equipo B'),(report['match']['team_a'],report['match']['team_b'])):
        team=evidence['teams'][name]
        sheets=[{'alias':f'Jugador {i}','name':nick,'observations':[]}
                for i,nick in enumerate(team['player_series'],1)]
        collective=[]
        for series in window_rows(team['series'],cutoff,series=True)[0][:5]:
            sources=by_source[(name,series['source'])]
            maps=series['maps']
            primary_before=parse_dt(evidence['retrieved'])<cutoff
            collective.append({'id':series['id'],'date':series['date'],'opponent':series['opponent'],
                               'maps':maps,'source':series['source'],'result':series['result'],
                               'prematch':sources['prematch'],'review':sources['review']})
            for sheet in sheets:
                lines=series['players'].get(sheet['name'],{})
                ordered=[lines.get(str(i),lines.get(i)) for i in range(1,len(maps)+1)]
                full=primary_before and bool(ordered) and all(isinstance(line,dict) and
                     all(type(line.get(k))==int for k in ('kills','deaths')) for line in ordered)
                kd=[sum(line[k] for line in ordered) for k in ('kills','deaths')] if full else None
                observed+=int(full)
                def claim(rows):
                    return next((p['state'] for p in rows if p['player'].casefold()==sheet['name'].casefold()),'SIN CONSTANCIA')
                sheet['observations'].append({'id':series['id'],'opponent':series['opponent'],
                    'date':series['date'],'source':series['source'],'secondary':sources['secondary'],
                    'kd_at_cutoff':kd,'prematch':claim(sources['prematch_players']),
                    'review':claim(sources['players'])})
        teams[slot]={'name':name,'players':sheets,'series':collective}
    causal=build_causal(report,evidence)
    blockers=[]
    if observed<50: blockers.append(f'Muestra individual prepartido {observed}/50.')
    if causal['prematch']['series']<10: blockers.append(f"Series con secuencias de apertura al corte: {causal['prematch']['series']}/10.")
    if not causal['prematch']['compatible']: blockers.append('Sin secuencia repetida y compatible con el siguiente rival al corte.')
    blockers.append('Falta validar la explicación táctica y las alternativas con eventos ordenados de ronda.')
    record=json.loads(Path(__file__).with_name('mirage_rounds.json').read_text())
    review=record if any(s['id']==record['series_id'] and any(m['map'].removeprefix('de_')==record['map'] for m in s['maps'])
                         for t in teams.values() for s in t['series']) else None
    return {'round_review':review,'causal':causal,'t6_blockers':blockers,'teams':teams,'observations_at_cutoff':observed,
            'series_count':sum(len(t['series']) for t in teams.values()),
            'status':'PARCIAL' if observed or any(t['series'] for t in teams.values()) else 'PENDIENTE',
            'transferability':'Contraste por mapa, lado, primera baja y relación de equipamiento. La compatibilidad describe una hipótesis.',
            'missing':['Rol por serie','KAST y rating comparable de serie','Causalidad y compensación por ronda']}


def workflow(report, payload):
    """Run adverse sensitivity on the same blind proxy used for the selection."""
    adverse=report['robustness']['adverse']
    worst={'changed_date':adverse['date'],'margin':adverse['adverse_margin']} if adverse else None
    evidence_gap=report['casefile']['missing']
    objections=[]
    if report['multisource']['confirmed_before']<report['casefile']['series_count']:
        objections.append('Falta corroboración prepartido de marcadores.')
    if report['casefile']['observations_at_cutoff']<50:
        objections.append('La muestra individual prepartido es insuficiente.')
    if worst and worst['margin']<=0:
        objections.append('La inversión de una observación elimina o invierte la dirección del indicador.')
    if not objections:
        objections.append('Transferibilidad causal pendiente de demostración.')
    phases=[
        ('Documentación', [('T1_anonimizacion','Identidad y alineación',report['identity']['status']),
          ('T2_ventana_15_dias','Ventana y elegibilidad',str(report['casefile']['series_count'])+'/10 series'),
          ('T3_multifuente','Investigación multifuente',str(report['multisource']['confirmed_before'])+' series corroboradas al corte'),
          ('T4_osint','Contexto público',', '.join(report['osint']['pending'])),
          ('T5_fichas_piso','Expediente y transferibilidad',' · '.join(evidence_gap))]),
        ('Evaluación ciega',[('T6_cipi_ciego','CIPI ciego',' '.join(report['casefile']['t6_blockers'])),
          ('T7_robustez','Robustez','Diagnóstico del indicador provisional. T7 formal requiere una dirección CIPI autorizada en T6.'),
          ('T8_contradicciones','Contradicción y volatilidad',' '.join(objections))]),
        ('Resolución',[('T9_desbloqueo_identidad','Contraste de identidad','La liberación formal depende del cerrojo de evidencia.'),
          ('T10_veredicto','Veredicto',report['selection_type']+' · '+report['confidence']),
          ('T11_postpartido','Auditoría posterior','Requiere predicción congelada, resultado y contraste del mecanismo.')])]
    msi={'fase':report['osint']['items'][0]['text'],'formato':'BO3','consecuencia de perder':None,
         'recompensa de ganar':None,'modalidad LAN/online':None,'experiencia comparable':None,'recuperación':None}
    pve={}
    for alias,t in report['casefile']['teams'].items():
        pve[alias]={}
        for sheet in t['players']:
            differences=[r['kd_at_cutoff'][0]-r['kd_at_cutoff'][1] for r in sheet['observations'] if r['kd_at_cutoff']]
            pve[alias][sheet['alias']]={'series':len(differences),'minimum':min(differences,default=None),
                                         'maximum':max(differences,default=None)}
    report['tasks']['T8_contradicciones']='PARCIAL'
    return {'msi':msi,'pve_kd_range':pve,'adverse':worst,'objections':objections,'phases':[
        {'name':phase,'steps':[{'id':key.split('_')[0],'label':label,'state':report['tasks'][key],'reason':reason}
        for key,label,reason in steps]} for phase,steps in phases]}
