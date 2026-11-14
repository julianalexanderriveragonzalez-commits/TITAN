"""T8: factual objections and sensitivity of the fixed-sample additive proxy."""
def tipping_point(stress):
    if not stress['side']:
        return {'state':'EMPATE INICIAL','changes':[],'margin':0}
    base=stress['base_margin']
    margin=base
    chosen=[]
    # T7 perturbs disjoint units with fixed denominators. Their signed changes
    # therefore add. Largest adverse changes first minimize the number of flips.
    for trial in sorted(stress['withdrawals'],key=lambda r:r['adverse_margin']):
        reduction=round(base-trial['adverse_margin'],6)
        if reduction<=0:break
        chosen.append({k:trial[k] for k in ('team','group','index','date','shared')})
        margin=round(margin-reduction,6)
        if margin<0:
            return {'state':'INVERSIÓN','changes':chosen,'margin':margin}
    return {'state':'EMPATE' if margin==0 else 'SIN INVERSIÓN','changes':chosen,'margin':margin}


def objections(report):
    conflicts=[]
    pending=[]
    late=[]
    for row in report['multisource']['series']:
        label=row['team']+' vs. '+row['opponent']
        link=row['secondary'] or row['primary']
        if row['prematch']=='CONTRADICCIÓN':
            conflicts.append({'text':label+' · marcadores incompatibles','source':link})
        for p in row['prematch_players']:
            if p['state']=='K-D EN CONFLICTO':
                conflicts.append({'text':label+' · K-D de '+p['player'],'source':link})
        if row['prematch']!='CORROBORADA':
            pending.append(label)
        if row['after_cutoff']:
            if row['review']=='CONTRADICCIÓN':
                late.append({'text':label+' · marcadores incompatibles','source':link})
            for p in row['players']:
                if p['state']=='K-D EN CONFLICTO':
                    late.append({'text':label+' · K-D de '+p['player'],'source':link})
    for team in report.get('source_network',{}).get('hltv',[]):
        for row in team['series']:
            if row['state']=='CONTRADICCIÓN':
                target=conflicts if row['before'] else late
                target.append({'text':row['team']+' vs. '+row['opponent']+' · marcador HLTV incompatible','source':row['url']})
    n=report['casefile']['observations_at_cutoff']
    stress=report['robustness']
    if not stress['side']:
        strongest='El indicador empató; la selección fue administrativa.'
    elif conflicts:
        strongest='Discrepancia documental al corte: '+conflicts[0]['text']+'. Su efecto deportivo queda por determinar.'
    elif pending:
        strongest=f'{len(pending)} de {len(report["multisource"]["series"])} marcadores carecían de corroboración BLAST–BO3.gg antes del corte.'
    elif n<50:
        strongest=f'La muestra individual al corte contiene {n}/50 observaciones.'
    else:
        strongest='La transferibilidad causal sigue pendiente de verificación.'
    documented_tie = not stress['side'] and (n > 0 or any(
        row['prematch'] == 'CORROBORADA' for row in report['multisource']['series']))
    assessed = bool(report['multisource']['series'] and (documented_tie or stress['withdrawals']))
    tasks = report['tasks']
    pending_steps = [label for key, label in (
        ('T6_cipi_ciego', 'T6 · CIPI ciego'),
        ('T7_robustez', 'T7 · Robustez')
    ) if tasks.get(key) != 'COMPLETADA']
    reasons = list(report['casefile'].get('t6_blockers', []))
    reasons.extend(step + ' pendiente de autorización.' for step in pending_steps)
    if not assessed:
        reasons.append('Falta una prueba de sensibilidad del indicador o un empate documentado.')
    if not assessed:
        conclusion = 'REVISIÓN INCOMPLETA'
    elif pending_steps:
        conclusion = 'CERRADA SIN DIRECCIÓN CIPI AUTORIZADA'
    else:
        conclusion = 'CONTRADICCIÓN Y VOLATILIDAD REVISADAS'
    return {'diagnostic_status': 'COMPLETADA' if assessed else 'PARCIAL',
            'formal_status': 'COMPLETADA' if assessed else 'BLOQUEADA',
            'conclusion': conclusion, 'gate_reasons': reasons,
            'strongest': strongest, 'conflicts': conflicts, 'late': late, 'pending': pending,
            'individual_sample': n, 'tipping': tipping_point(stress)}
