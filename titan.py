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


def analyze(data: dict[str, Any]) -> dict[str, Any]:
    """Deterministic locked pre-match report. Never uses later match results."""
    matchup = data['match']
    cutoff = parse_dt(matchup['cutoff'])
    name_a, name_b = matchup['team_a'], matchup['team_b']
    a = data['teams'][name_a]; b = data['teams'][name_b]
    sa, notes_a, gaps_a, n_a = _score_team(a, cutoff)
    sb, notes_b, gaps_b, n_b = _score_team(b, cutoff)
    delta = round(sa - sb, 6)
    # Forced tie-break is declared and carries NO competitive significance.
    # Alphabetical choice is deterministic, unbiased to input order and transparent.
    if abs(delta) < 1e-9:
        winner = sorted([name_a, name_b], key=str.casefold)[0]
        tie = 'Desempate administrativo alfabético, NO evidencia de ventaja competitiva.'
    else:
        winner = name_a if delta > 0 else name_b
        tie = None
    tasks = {t: 'PENDIENTE' for t in TASKS}
    tasks['T1_anonimizacion'] = 'PENDIENTE'  # Only identity-separated scoring, not a full blind audit.
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
