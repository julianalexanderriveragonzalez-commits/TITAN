"""TITAN OMNIBRAIN 4.1-R3.4 — auditable decision engine (stdlib only).

This is a research prototype, not a verified predictor of esports outcomes.
It never fabricates data and reports missing evidence explicitly.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VERSION = 'TITAN-4.1-R3.4'
CONTROL_NAMES = [
    'coherencia_direccional', 'piso_colectivo_cce', 'transferibilidad',
    'rutas_bo3', 'estres_competitivo', 'robustez_retirada',
    'auditoria_sin_contaminacion', 'ser_recuperacion_extrema',
    'ame_adaptacion', 'dme_mapa_decisivo', 'vsr_vetos', 'ecc_contradiccion'
]
TASKS = [
    'T1_anonimizacion', 'T2_ventana_15_dias', 'T3_multifuente',
    'T4_osint', 'T5_fichas_piso', 'T6_cipi_ciego', 'T7_robustez',
    'T8_contradicciones', 'T9_desbloqueo_identidad',
    'T10_veredicto', 'T11_postpartido'
]
ALLOWED = {'COMPLETADA', 'PENDIENTE', 'BLOQUEADA', 'NO APLICA', 'PENDIENTE TEMPORAL'}


def parse_dt(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Las fechas deben incluir zona horaria (ej. -05:00).')
    return d.astimezone(timezone.utc)


def window_rows(rows, cutoff, series=False):
    """Return distinct dated evidence in [cutoff - 15 days, cutoff)."""
    admitted = []
    seen = set()
    reasons = {}
    for row in rows:
        reason = None
        try:
            start = parse_dt(row['date'])
            finish = parse_dt(row['finished_at']) if row.get('finished_at') else start
            if not cutoff - timedelta(days=15) <= start < cutoff:
                reason = 'fuera de ventana'
            elif finish < start or finish >= cutoff:
                reason = 'fin de serie incompatible'
        except (AttributeError, KeyError, TypeError, ValueError):
            reason = 'fecha inválida'
        if not reason and series and (row.get('format') != 'BO3' or row.get('result') not in ('W', 'L')):
            reason = 'formato o resultado inválido'
        if not reason and not row.get('source'):
            reason = 'sin fuente'
        if not reason and not series and row.get('score') not in (-1, 0, 1):
            reason = 'valor de mecanismo inválido'
        if not reason:
            keys = [('id', str(row['id']))] if row.get('id') else []
            keys.append(('source', str(row['source']), start) if series else
                        ('signal', str(row['source']), start, str(row.get('type', row.get('mechanism',''))), row['score']))
            if any(k in seen for k in keys):
                reason = 'duplicada'
            else:
                seen.update(keys)
                admitted.append(row)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    admitted.sort(key=lambda row: parse_dt(row['date']), reverse=True)
    return admitted, reasons


def blind_evidence(team, cutoff=None):
    """Only the fields consumed by scoring cross the identity boundary."""
    result = {}
    for group, field, allowed in (
        ('series', 'result', ('W', 'L')),
        ('mechanisms', 'score', (-1, 0, 1)),
    ):
        rows = []
        records = team.get(group, [])
        if cutoff is not None:
            records, _ = window_rows(records, cutoff, group == 'series')
        for row in records:
            try:
                date = parse_dt(row['date']).isoformat()
            except (KeyError, TypeError, AttributeError, ValueError):
                date = ''
            entry = {'date': date, 'source': bool(row.get('source')),
                     field: row.get(field) if row.get(field) in allowed else None}
            if group == 'series':
                entry['format'] = 'BO3' if row.get('format') == 'BO3' else None
            rows.append(entry)
        result[group] = rows
    return result


def blind_decision(a, b, cutoff):
    teams = [blind_evidence(a, cutoff), blind_evidence(b, cutoff)]
    results = [_score_team(team, cutoff) for team in teams]
    delta = round(results[0][0] - results[1][0], 6)
    sporting_side = 'A' if delta > 0 else 'B' if delta < 0 else None
    # On a symmetric tie an obligatory administrative label depends on position.
    # Select it deterministically from the cutoff, independently of team names.
    seed = hashlib.sha256(cutoff.isoformat().encode()).digest()
    side = sporting_side or ('A' if seed[0] % 2 == 0 else 'B')
    return results, delta, side, sporting_side


def _score_team(team: dict[str, Any], cutoff: datetime) -> tuple[float, list[str], list[str], int]:
    """Returns weighted, bounded proxy signal; no odds or fabricated win probability."""
    notes, missing = [], []
    series = []
    for s in team.get('series', []):
        try:
            when = parse_dt(s['date'])
        except (ValueError, KeyError) as e:
            missing.append(f'Serie con fecha inválida: {e}')
            continue
        if cutoff - timedelta(days=15) <= when < cutoff and s.get('format') == 'BO3':
            if s.get('result') in ('W', 'L') and s.get('source'):
                series.append(s)
            else:
                missing.append('Serie sin resultado o fuente verificable')
    series.sort(key=lambda v: v['date'], reverse=True)
    usable = series[:5]
    if len(usable) < 5:
        missing.append(f'Solo {len(usable)}/5 series BO3 documentadas en ventana')
    # Equal weights for every recent BO3; ONLY a weak proxy for comparative form.
    form = sum((1 if s['result']=='W' else -1) for s in usable) / max(5, len(usable))
    notes.append(f'{len(usable)}/5 BO3 recientes documentadas; balance normalizado {form:+.2f}')

    # Mechanism assessments MUST be supplied with sources and are explicitly bounded.
    mechanisms = team.get('mechanisms', [])
    evid = [m for m in mechanisms if m.get('source') and m.get('date') and m.get('score') in (-1,0,1)
            and cutoff-timedelta(days=15) <= parse_dt(m['date']) < cutoff]
    if len(evid) < 3:
        missing.append('Menos de 3 señales causales documentadas y fechadas')
    causal = sum(m['score'] for m in evid[:10]) / max(10, len(evid[:10]))
    notes.append(f'{len(evid)} señales de mecanismo recientes con fuente')
    return (0.5*form + 0.5*causal), notes, missing, len(usable)


def robustness(data, cutoff):
    """Perturb only the observations actually used by the original blind score."""
    names=[data['match']['team_a'],data['match']['team_b']]
    teams=[blind_evidence(data['teams'][n], cutoff) for n in names]
    groups={}
    for side,name in enumerate(names):
        for group,limit in [('series',5),('mechanisms',10)]:
            rows,_=window_rows(data['teams'][name].get(group,[]),cutoff,group=='series')
            teams[side][group]=teams[side][group][:limit]
            for i,row in enumerate(rows[:limit]):
                # A shared BO3 carries two observations; perturb it only once.
                key=(group,str(row.get('id') or row.get('source')),parse_dt(row['date']).isoformat())
                if group=='mechanisms':key+=(side,i)
                groups.setdefault(key,[]).append((side,group,i))
    def margin(pair):
        return round(_score_team(pair[0],cutoff)[0]-_score_team(pair[1],cutoff)[0],6)
    base=margin(teams)
    sign=1 if base>0 else -1 if base<0 else 0
    out={'base_margin':abs(base),'side':'A' if sign==1 else 'B' if sign==-1 else None,
         'withdrawals':[],'most_supportive':[],'adverse':None,'stable':0}
    if not sign:return out
    for refs in groups.values():
        margins=[]
        for flip in (False,True):
            pair=[{k:list(rows) for k,rows in t.items()} for t in teams]
            for side,group,i in refs:
                row=pair[side][group][i]
                if not flip:
                    pair[side][group].pop(i)
                elif group=='series':
                    pair[side][group][i]=dict(row,result='L' if row['result']=='W' else 'W')
                else:
                    pair[side][group][i]=dict(row,score=-row['score'])
            margins.append(round(sign*margin(pair),6))
        side,group,i=refs[0]
        trial={'group':group,'team':'A' if side==0 else 'B','index':i+1,'shared':len(refs)>1,
               'date':teams[side][group][i]['date'],'margin':margins[0],'adverse_margin':margins[1]}
        out['withdrawals'].append(trial)
    trials=out['withdrawals']
    out['stable']=sum(r['margin']>0 for r in trials)
    if trials:
        low=min(r['margin'] for r in trials)
        out['most_supportive']=[r for r in trials if r['margin']==low and low<abs(base)]
        worst=min(trials,key=lambda r:r['adverse_margin'])
        if worst['adverse_margin']<abs(base):out['adverse']=worst
    return out


def analyze(data: dict[str, Any]) -> dict[str, Any]:
    """Deterministic locked pre-match report. Never uses later match results."""
    matchup = data['match']
    cutoff = parse_dt(matchup['cutoff'])
    name_a, name_b = matchup['team_a'], matchup['team_b']
    a = data['teams'][name_a]; b = data['teams'][name_b]
    results, delta, side, sporting_side = blind_decision(a, b, cutoff)
    (sa, notes_a, gaps_a, n_a), (sb, notes_b, gaps_b, n_b) = results
    winner = name_a if side == 'A' else name_b
    tie = None if sporting_side else (
        'Empate deportivo. Selección administrativa por casilla y hora de corte; '
        'invertir las casillas puede cambiar el nombre seleccionado.'
    )
    tasks = {t: 'PENDIENTE' for t in TASKS}
    tasks['T1_anonimizacion'] = 'PARCIAL'  # The scoring step is blind; downstream research reports retain identities.
    tasks['T2_ventana_15_dias'] = 'COMPLETADA'
    tasks['T6_cipi_ciego'] = 'BLOQUEADA'
    tasks['T7_robustez'] = 'BLOQUEADA'
    tasks['T9_desbloqueo_identidad'] = 'BLOQUEADA'
    tasks['T10_veredicto'] = 'COMPLETADA'  # Mandatory provisional selection only.
    tasks['T11_postpartido'] = 'PENDIENTE TEMPORAL'
    # 12 controls are NOT marked completed from merely having one row of evidence.
    controls = {c: 'PENDIENTE' for c in CONTROL_NAMES}
    gaps = {name_a:gaps_a, name_b:gaps_b}
    readiness = n_a>=5 and n_b>=5
    # This engine cannot certify 50 individual observations, full causal audits or VSR.
    evidence_state = 'CERROJO DOCUMENTAL INCOMPLETO'
    confidence = 'MUY BAJA' if not readiness or abs(delta) < .15 else 'BAJA'
    report = {
        'version': VERSION, 'match': matchup, 'selection': winner,
        'selection_type': 'PROVISIONAL FORZADA', 'confidence': confidence,
        'evidence_state': evidence_state,
        'proxy_scores_not_probabilities': {name_a:round(sa,3), name_b:round(sb,3)},
        'blind_scoring': {'status': 'COMPLETADA', 'sporting_side': sporting_side,
                          'scores': {'A': sa, 'B': sb}, 'administrative': sporting_side is None},
        'window': {
            'start_inclusive': (cutoff-timedelta(days=15)).isoformat(), 'end_exclusive': cutoff.isoformat(),
            'teams': {alias: {'eligible': len(window_rows(team.get('series',[]),cutoff,True)[0]),
                              'used': used,'excluded':window_rows(team.get('series',[]),cutoff,True)[1]}
                      for alias,team,used in [('Equipo A',a,n_a),('Equipo B',b,n_b)]}},
        'difference': delta, 'tie_break_explanation': tie,
        'team_notes': {name_a: notes_a, name_b:notes_b},
        'missing_evidence': gaps, 'tasks': tasks, 'controls_R33_R34': controls,
        'methodology_notes': [
            'NO es una probabilidad de victoria, cuota, ranking ni validación causal.',
            'El motor usa balances recientes y señales de mecanismo explícitas; no infiere tácticas ni psicología.',
            'No hay certificado robusto sin 5 series por jugador, 50 fichas, 10 auditorías causales y pruebas de retirada/vetos.',
            'El ganador es obligatorio pero puede ser una simple decisión administrativa cuando no hay ventaja.',
            'Los datos posteriores al corte nunca se incorporan al cálculo prepartido.'
        ]
    }
    report['robustness'] = robustness(data,cutoff)
    report['input_sha256'] = hashlib.sha256(json.dumps(data, sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return report


def append_log(report: dict[str, Any], path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    # Use exclusive creation of individual immutable snapshots, never overwrite.
    identifier = report['input_sha256'][:16]
    dest = path / f'prepartido_{identifier}.json'
    with dest.open('x', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'Registro inmutable creado: {dest}')


def evaluate(logfile: Path, result: str) -> dict[str, Any]:
    with logfile.open(encoding='utf-8') as f:
        prior = json.load(f)
    if result not in (prior['match']['team_a'], prior['match']['team_b']):
        raise ValueError('Ganador real no coincide con los dos equipos del registro')
    return {'match_id': prior['match']['id'], 'version':prior['version'],
            'predicted':prior['selection'], 'actual': result,
            'correct':prior['selection']==result,
            'pre_match_hash':prior['input_sha256'],
            'note':'Evaluación postpartido separada; nunca modifica el pronóstico previo.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=VERSION)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('analyze', help='Analizar partido JSON')
    p.add_argument('file', type=Path); p.add_argument('--save', type=Path)
    e = sub.add_parser('evaluate', help='Auditar registro posterior')
    e.add_argument('record', type=Path); e.add_argument('--winner', required=True)
    args = parser.parse_args()
    if args.cmd == 'analyze':
        with args.file.open(encoding='utf-8') as f: d = json.load(f)
        result = analyze(d)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.save: append_log(result,args.save)
    else:
        print(json.dumps(evaluate(args.record,args.winner), ensure_ascii=False, indent=2))

if __name__ == '__main__': main()
