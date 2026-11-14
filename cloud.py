"""TITAN Cloud R3.4: WSGI web service, stdlib-only MVP.

Run locally with python cloud.py, or in production with gunicorn cloud:app.
Set TITAN_DB to select the SQLite database location.
"""
from __future__ import annotations
import hashlib
import re
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from http.cookies import CookieError, SimpleCookie
from wsgiref.simple_server import make_server
from titan import prepare_review, finalize_review, parse_dt
from competitive_review import evaluate as compare_portfolios
from titan import TASKS
from postmatch import official_result, review as postmatch_review
from research import automatic_input
from casefile import build_casefile, workflow
from volatility import objections as assess_volatility
from identity import build_identity
from multisource import dossier
from source_network import collect as collect_sources
from osint_context import context as public_context
from audit import run as audit_match

APP_VERSION = 'TITAN-CLOUD-0.4-R3.4'
MAX_BYTES = 120_000


def db_path():
    return Path(os.getenv('TITAN_DB', './data/titan.sqlite3'))


def init_database():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS browser_predictions (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, created_utc TEXT NOT NULL,
            input_json TEXT NOT NULL, report_json TEXT NOT NULL,
            actual_winner TEXT, evaluated_utc TEXT
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS postmatch_reviews
                      (id TEXT PRIMARY KEY, audit_json TEXT NOT NULL)''')


def reply(start, status, body, content_type='application/json; charset=utf-8', extra=()):
    raw = body.encode('utf-8') if isinstance(body, str) else body
    hdr = [('Content-Type', content_type), ('Content-Length', str(len(raw))),
           ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
           ('Referrer-Policy', 'no-referrer'), ('X-Frame-Options', 'DENY'),
           ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]
    start(status, hdr + list(extra))
    return [raw]


def json_reply(start, status, obj, extra=()):
    return reply(start, status, json.dumps(obj, ensure_ascii=False), extra=extra)


def validate_input(payload):
    if not isinstance(payload, dict):
        raise ValueError('El cuerpo debe ser un objeto JSON')
    m = payload.get('match')
    if not isinstance(m, dict):
        raise ValueError('Falta match')
    for key in ('team_a', 'team_b', 'cutoff', 'id'):
        if not isinstance(m.get(key), str) or not m[key].strip():
            raise ValueError('Falta el campo match.' + key)
    if len(m['team_a']) > 80 or len(m['team_b']) > 80 or len(m['id']) > 120:
        raise ValueError('Nombre o ID demasiado largo')
    if m['team_a'].strip().casefold() == m['team_b'].strip().casefold():
        raise ValueError('Los equipos deben ser distintos')
    cutoff = parse_dt(m['cutoff'])
    if not isinstance(payload.get('teams'), dict):
        raise ValueError('Falta teams')
    for name in (m['team_a'], m['team_b']):
        team = payload['teams'].get(name)
        if not isinstance(team, dict):
            raise ValueError('Falta información de ' + name)
        for field in ('series','mechanisms'):
            if not isinstance(team.get(field, []), list) or len(team.get(field, [])) > 100:
                raise ValueError('Campo inválido: '+field)
        for x in team.get('series', []):
            if not isinstance(x, dict): raise ValueError('Serie inválida')
            if 'date' in x: parse_dt(x['date'])
        for x in team.get('mechanisms', []):
            if not isinstance(x, dict): raise ValueError('Mecanismo inválido')
            if 'date' in x: parse_dt(x['date'])
    return cutoff


def process_json(environ):
    try:
        size = int(environ.get('CONTENT_LENGTH', '0'))
    except ValueError:
        raise ValueError('Content-Length inválido')
    if size <= 0 or size > MAX_BYTES:
        raise ValueError('JSON vacío o demasiado grande')
    if not environ.get('CONTENT_TYPE','').startswith('application/json'):
        raise ValueError('Se requiere application/json')
    try:
        return json.loads(environ['wsgi.input'].read(size).decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('JSON mal formado')


def same_origin(env):
    # Browsers attach Origin to cross-origin JSON requests. Reject mismatches.
    origin = env.get('HTTP_ORIGIN')
    if not origin: return True
    proto = env.get('HTTP_X_FORWARDED_PROTO', env.get('wsgi.url_scheme','http')).split(',')[0].strip()
    host = env.get('HTTP_HOST','')
    return origin == proto + '://' + host


def app(environ, start_response):
    cookies = SimpleCookie()
    try:
        cookies.load(environ.get('HTTP_COOKIE', ''))
    except CookieError:
        cookies.clear()
    cookie = cookies.get('titan_session')
    token = cookie.value if cookie else ''
    if not re.fullmatch('[a-f0-9]{64}', token):
        token = secrets.token_hex(32)
        secure = environ.get('HTTP_X_FORWARDED_PROTO', environ.get('wsgi.url_scheme')) == 'https'
        cookie_header = f'titan_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000'
        if secure:
            cookie_header += '; Secure'
        original_start = start_response

        def start_response(status, headers):
            return original_start(status, headers + [('Set-Cookie', cookie_header)])

    owner = hashlib.sha256(token.encode('ascii')).hexdigest()
    method, path = environ.get('REQUEST_METHOD','GET'), environ.get('PATH_INFO','/')
    if method == 'GET' and path == '/':
        p = Path(__file__).with_name('index.html')
        return reply(start_response, '200 OK', p.read_bytes(), 'text/html; charset=utf-8')
    if method == 'GET' and path == '/app.css':
        p = Path(__file__).with_name('app.css')
        return reply(start_response, '200 OK', p.read_bytes(), 'text/css; charset=utf-8')
    if method == 'GET' and path == '/app.js':
        p = Path(__file__).with_name('app.js')
        return reply(start_response, '200 OK', p.read_bytes(), 'text/javascript; charset=utf-8')
    if method == 'GET' and path == '/health':
        return json_reply(start_response, '200 OK', {'status':'ok','version':APP_VERSION})
    if method == 'POST' and not same_origin(environ):
        return json_reply(start_response, '403 Forbidden', {'error':'Origen no permitido'})
    try:
        if method == 'POST' and path in ('/api/analyze','/api/freeze'):
            payload = process_json(environ)
            cutoff = validate_input(payload)
            evidence = None
            if payload.get('research_mode') == 'automatic':
                try:
                    payload['teams'], evidence = automatic_input(payload['match'])
                except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
                    return json_reply(start_response, '422 Unprocessable Entity', {
                        'error': 'Investigación pendiente. ' + (str(exc) if isinstance(exc, ValueError) else 'BLAST no entregó evidencia utilizable.')
                    })
            report = prepare_review(payload)
            report['tasks']['T2_ventana_15_dias'] = 'PARCIAL'
            if evidence:
                diagnostics = audit_match(report, payload, evidence)
                report['identity'] = build_identity(evidence, cutoff)
                report['multisource'] = dossier(evidence, cutoff)
                report['source_network'] = collect_sources(evidence,cutoff)
                floor=report['source_network']['floor']
                if floor['review_ratings']:
                    diagnostics['controls']['piso_colectivo_cce']={'estado':'PARCIAL',
                        'detalle':f"HLTV 3.0: {floor['prematch_alerts']} alertas en {floor['prematch_ratings']} ratings al corte; última revisión: {floor['review_alerts']} en {floor['review_ratings']}. La compensación requiere pruebas por ronda."}
                report['tasks']['T3_multifuente'] = report['multisource']['status']
                report['osint'] = public_context(evidence, cutoff, report['source_network'])
                report['tasks']['T4_osint'] = report['osint']['status']
                report['audit'] = diagnostics
                report['tasks']['T1_anonimizacion'] = report['identity']['status']
                report['window']['player_counts'] = diagnostics['window_player_counts']
                report['window']['individual_scope'] = 'RETROSPECTIVA' if diagnostics['retrospective'] else 'PREPARTIDO'
                counts = diagnostics['window_player_counts']
                if diagnostics['retrospective']:
                    report['window']['prematch_player_counts'] = {
                        slot: {f'Jugador {i}':count for i,count in enumerate(evidence['teams'][name]['player_series'].values(),1)}
                        for slot,name in zip(('Equipo A','Equipo B'),(payload['match']['team_a'],payload['match']['team_b']))}
                else:
                    report['window']['prematch_player_counts'] = counts

                if parse_dt(evidence['retrieved']) >= cutoff:
                    report['window']['prematch_player_counts'] = {}
                counts = report['window'].get('prematch_player_counts', {})
                full_sample = (len(counts) == 2 and all(len(players) == 5 and min(players.values()) >= 5
                                                       for players in counts.values()))
                report['tasks']['T2_ventana_15_dias'] = 'COMPLETADA' if full_sample else 'PARCIAL'
                report['controls_R33_R34'] = {k:v['estado'] for k,v in diagnostics['controls'].items()}
                report['casefile'] = build_casefile(report, evidence)
                report['tasks']['T5_fichas_piso'] = report['casefile']['status']
                groups = report.pop('_series_for_cipi')
                names = [payload['match'][key] for key in ('team_a','team_b')]
                missing = [k.split('_')[0] for k in TASKS[:5] if report['tasks'][k]!='COMPLETADA']
                comparison = {'side':None,'families':[],'trials':[],'survives':False}
                if not missing:
                    comparison = compare_portfolios(groups,[report['osint']['rest_hours'][n] for n in names])
                comparison['pending_steps'] = missing
                comparison['sources'] = [[{'series':r['id'],'urls':r['sources']} for r in g] for g in groups]
                comparison['documented_series'] = [len(g) for g in groups]
                report['cipi_review'] = comparison
                if comparison['side']:
                    report['tasks']['T6_cipi_ciego'] = 'COMPLETADA'
                    if comparison['survives']:
                        report['tasks']['T7_robustez'] = 'COMPLETADA'
                        report['cipi_decision'] = {'side':comparison['side'],'robust_side':comparison['side'],
                                                  'aliases':dict(zip('AB',names)),'input_sha256':report['input_sha256']}
                report['volatility'] = assess_volatility(report)
                report['tasks']['T8_contradicciones'] = report['volatility']['formal_status']
                report['methodology_notes'].append('Las fichas consultadas después del corte solo se usan para revisión retrospectiva.')

            if evidence:
                report['fixture_source'] = evidence['source']
                report['collection'] = {'checked':evidence['retrieved'],'unavailable_pages':evidence.get('unavailable_pages'),
                                        'reconstructed':bool(evidence.get('reconstructed')),
                                        'series':{n:[{'date':s['date'],'opponent':s['opponent'],'result':s['result'],'source':s['source']}
                                                     for s in t['series']] for n,t in evidence['teams'].items()}}
            if payload.get('postmatch_hypothesis') == 'REMONTAR_TRAS_PERDER_MAPA_1':
                report['postmatch_hypothesis'] = payload['postmatch_hypothesis']
            finalize_review(report)
            if evidence:
                report['workflow'] = workflow(report,payload)
            now = datetime.now(timezone.utc)
            if cutoff <= now:
                if path.endswith('analyze'):
                    if evidence:
                        try:
                            actual = official_result(report['match'], report['fixture_source'])
                        except (OSError, ValueError, KeyError, TypeError) as exc:
                            actual = {'origin':'PENDIENTE','detail':str(exc)[:200]}
                        report['postmatch'] = postmatch_review(report, actual, None, now.isoformat())
                    return json_reply(start_response, '200 OK', report)
                return json_reply(start_response, '409 Conflict',
                                  {'error':'El corte temporal debe ser futuro para congelar una predicción prospectiva.'})
            init_database()
            ident = secrets.token_hex(12)
            report['snapshot_id'] = ident
            timestamp = now.isoformat()
            with sqlite3.connect(db_path(), timeout=10) as db:
                db.execute('INSERT INTO browser_predictions (owner, id, created_utc, input_json, report_json) VALUES (?,?,?,?,?)',
                           (owner, ident, timestamp, json.dumps(payload,ensure_ascii=False),json.dumps(report,ensure_ascii=False)))
            if path.endswith('analyze'):
                return json_reply(start_response, '200 OK', report)
            return json_reply(start_response, '201 Created', {'id':ident,'created_utc':timestamp,'report':report})
        if method == 'GET' and re.fullmatch(r'/api/history/[0-9a-f]{24}',path):
            init_database()
            with sqlite3.connect(db_path(),timeout=10) as db:
                row=db.execute('SELECT report_json,actual_winner,created_utc,evaluated_utc,audit_json FROM browser_predictions LEFT JOIN postmatch_reviews USING(id) WHERE owner=? AND id=?',
                               (owner,path.rsplit('/',1)[-1])).fetchone()
            if row is None:
                return json_reply(start_response,'404 Not Found',{'error':'Registro no encontrado'})
            report=json.loads(row[0])
            if row[4]:
                report['postmatch']=json.loads(row[4])
            elif row[1]:
                report['postmatch']=postmatch_review(report, {'winner':row[1],'origin':'MANUAL'},row[2],row[3])
            return json_reply(start_response,'200 OK',report)
        if method == 'GET' and path == '/api/history':
            init_database()
            with sqlite3.connect(db_path(), timeout=10) as db:
                rows = db.execute('SELECT id,created_utc,report_json,actual_winner,evaluated_utc FROM browser_predictions WHERE owner=? ORDER BY created_utc DESC LIMIT 100',(owner,)).fetchall()
            items=[]
            for ident,created,rep,actual,ev in rows:
                r=json.loads(rep)
                items.append({'id':ident,'created_utc':created,'match':r['match'], 'selection':r['selection'],
                              'fixture_source':r.get('fixture_source'),'confidence':r['confidence'],'actual_winner':actual,
                              'correct':None if actual is None else r['selection']==actual,
                              'evaluated_utc':ev})
            return json_reply(start_response, '200 OK', {'items':items})
        if method == 'POST' and path.startswith('/api/evaluate/'):
            ident = path.rsplit('/',1)[-1]
            if len(ident)!=24 or any(c not in '0123456789abcdef' for c in ident):
                raise ValueError('ID inválido')
            payload = process_json(environ)
            winner = payload.get('winner') if isinstance(payload,dict) else None
            init_database()
            with sqlite3.connect(db_path(), timeout=10) as db:
                row = db.execute('SELECT report_json,actual_winner,created_utc FROM browser_predictions WHERE id=? AND owner=?',(ident,owner)).fetchone()
                if not row: return json_reply(start_response,'404 Not Found',{'error':'Registro no encontrado'})
                r=json.loads(row[0]); allowed=(r['match']['team_a'],r['match']['team_b'])

                if row[1] is not None:
                    return json_reply(start_response,'409 Conflict',{'error':'Este resultado ya fue registrado y es inmutable'})
                # Forbid recording outcome before the pre-match cutoff.
                if datetime.now(timezone.utc) <= parse_dt(r['match']['cutoff']):
                    return json_reply(start_response,'409 Conflict',{'error':'Aún no pasó el corte temporal del partido'})
                evaluated = datetime.now(timezone.utc).isoformat()
                if r.get('fixture_source'):
                    try:
                        actual = official_result(r['match'], r['fixture_source'])
                    except (OSError, ValueError, TypeError, KeyError) as exc:
                        return json_reply(start_response,'422 Unprocessable Entity',{'error':'Resultado pendiente en BLAST. '+str(exc)[:150]})
                    if winner is not None and winner != actual['winner']:
                        raise ValueError('El ganador indicado contradice la ficha oficial.')
                    winner = actual['winner']
                else:
                    if winner not in allowed:
                        raise ValueError('Ganador real inválido')
                    actual = {'winner':winner,'origin':'MANUAL'}
                audit = postmatch_review(r,actual,row[2],evaluated)
                changed=db.execute('UPDATE browser_predictions SET actual_winner=?,evaluated_utc=? WHERE id=? AND actual_winner IS NULL',
                                   (winner,evaluated,ident)).rowcount
                if not changed:
                    return json_reply(start_response,'409 Conflict',{'error':'Resultado ya registrado.'})
                db.execute('INSERT INTO postmatch_reviews VALUES (?,?)',(ident,json.dumps(audit,ensure_ascii=False)))
            return json_reply(start_response,'200 OK',{'id':ident,'winner':winner,'correct':audit['correct'],'postmatch':audit})
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        return json_reply(start_response,'400 Bad Request',{'error':str(exc)[:350]})
    return json_reply(start_response,'404 Not Found',{'error':'Ruta no encontrada'})


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=int(os.getenv('PORT','8765')))
    args=parser.parse_args()
    print(f'TITAN Cloud escuchando en http://{args.host}:{args.port}')
    with make_server(args.host,args.port,app) as httpd: httpd.serve_forever()
