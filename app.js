'use strict';
const $ = id => document.getElementById(id);
function data() {
  const a=$('a').value.trim(),b=$('b').value.trim(),d=$('date').value;
  if(!a || !b || a===b || !d) throw Error('Introduce dos equipos distintos y la fecha del encuentro.');
  return {research_mode:$('manual').checked?'manual':'automatic',match:{id:crypto.randomUUID(),team_a:a,team_b:b,cutoff:d+':00-05:00'},teams:{[a]:$('manual').checked?JSON.parse($('sa').value):{},[b]:$('manual').checked?JSON.parse($('sb').value):{}}};
}
async function api(url,method='GET',body){
  const r=await fetch(url,{method,headers:method==='POST'?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,cache:'no-store'});
  const value=await r.json(); if(!r.ok) throw Error(value.error||'Error de servidor'); return value;
}
function show(text){$('result').textContent=text;}
async function action(freeze){
 try{
  show($('manual').checked?'Analizando datos manuales…':'Buscando el encuentro y comprobando mapas y jugadores en BLAST…');
  const p=data(); const r=await api(freeze?'/api/freeze':'/api/analyze','POST',p);
  const rep=freeze?r.report:r;
  renderReport(rep,freeze?r.id:null);
  if(freeze) await history();
 }catch(e){show('Error: '+e.message)}
}
function renderReport(rep,id){
  show((id?'Predicción congelada · ID '+id+'\n':'')+(rep.tie_break_explanation?'Desempate administrativo: ':'Selección provisional: ')+rep.selection+'\nTipo: '+rep.selection_type+'\nConfianza: '+rep.confidence+'\nEstado: '+rep.evidence_state+'\n\nCarencias:\n'+Object.entries(rep.missing_evidence).map(([team,gaps])=>team+': '+gaps.join('; ')).join('\n')+'\n\nControles pendientes: '+Object.values(rep.controls_R33_R34).filter(v=>v!=='COMPLETADA').length+'\n\n'+(rep.tie_break_explanation||''));
  if(rep.blind_scoring){
    const blind=rep.blind_scoring;
    const line=document.createElement('p');
    line.textContent='Puntuación ciega · Equipo A: '+blind.scores.A+' · Equipo B: '+blind.scores.B+' · '+(blind.sporting_side?'Indicador favorable a '+blind.sporting_side:'Empate deportivo');
    $('result').append(line);
  }
  if(rep.identity) renderIdentity(rep.identity);
  if(rep.window){
    const w=rep.window, el=document.createElement('p');
    el.textContent='T1 · '+rep.tasks.T1_anonimizacion+' | T2 · Ventana UTC desde '+w.start_inclusive+' (incluido) hasta '+w.end_exclusive+' (excluido). '+Object.entries(w.teams).map(([n,v])=>n+': '+v.used+'/5 BO3').join(' · ');
    $('result').append(el);
    for(const [slot,players] of Object.entries(w.prematch_player_counts||{})){
      const row=document.createElement('p');row.textContent='Muestra prepartido · '+slot+' · '+Object.entries(players).map(([n,c])=>n+': '+c+'/5').join(', ');$('result').append(row);
    }
  }
  if(rep.multisource) renderSources(rep.multisource);
  if(rep.osint) renderContext(rep.osint);
  if(rep.audit) renderAudit(rep.audit);
  if(rep.research) renderEvidence(rep.research);
  if(rep.casefile) renderCasefile(rep);
}
$('analyze').onclick=()=>action(false);
$('freeze').onclick=()=>action(true);
$('refresh').onclick=history;
async function history(){
 try{
  const r=await api('/api/history'); const div=$('history'); div.replaceChildren();
  if(!r.items.length){div.textContent='No hay predicciones congeladas.';return;}
  for(const x of r.items){
   const p=document.createElement('p');p.textContent=x.match.team_a+' vs. '+x.match.team_b+' · '+x.selection+' · '+x.confidence+(x.actual_winner?' · Resultado: '+x.actual_winner+(x.correct?' ✓':' ✗'):' · pendiente'); div.append(p);
   const open=document.createElement('button');open.className='secondary';open.textContent='Abrir expediente';
   open.onclick=async()=>{try{renderReport(await api('/api/history/'+x.id),x.id);$('result').scrollIntoView();}catch(e){show(e.message);}};div.append(open);
   if(!x.actual_winner){const btn=document.createElement('button');btn.className='secondary';btn.textContent='Registrar resultado';btn.onclick=async()=>{
     const winner=prompt('Ganador real (escribe exactamente '+x.match.team_a+' o '+x.match.team_b+')');if(winner===null)return;
     try{await api('/api/evaluate/'+x.id,'POST',{winner});await history()}catch(e){alert(e.message)}
   };div.append(btn)}
  }
 }catch(e){$('history').textContent='Error: '+e.message}
}
history();

function renderEvidence(audit){
  const panel=$('result');
  function line(text){const el=document.createElement('div');el.textContent=text;panel.append(el);}
  function source(text,url){const a=document.createElement('a');a.textContent=text;a.href=url;a.target='_blank';a.rel='noopener noreferrer';panel.append(a);}
  line('Fuente y cobertura');
  source(audit.tournament+' · '+audit.stage,audit.source);
  if(audit.fixture_corroboration) source(' · Segunda referencia del cruce',audit.fixture_corroboration);
  line('Consulta: '+audit.retrieved+(audit.cached_snapshot?' · copia documental previa al encuentro':''));
  for(const [name,t] of Object.entries(audit.teams)){
    line(name+' · '+t.series.length+'/5 BO3 verificados');
    if(t.observed) line('Mapas decisivos ganados: '+t.observed.deciders.join('/')+' · Series remontadas tras perder el primer mapa: '+t.observed.comebacks.join('/'));
    line('Series con todos los mapas por jugador: '+(Object.entries(t.player_series).map(([n,c])=>n+' '+c+'/5').join(', ')||'sin alineación verificable'));
    for(const url of t.score_conflicts||[]) source('Ficha excluida: marcador de serie y mapas incompatibles',url);
    for(const s of t.series){
      const details=document.createElement('details'), label=document.createElement('summary');
      label.textContent=s.date.slice(0,10)+' vs. '+s.opponent+' · '+s.result;
      details.append(label);panel.append(details);
      const body=document.createElement('div');
      body.textContent=s.maps.map(m=>m.map.replace('de_','')+' '+m.score.join('–')).join(' · ');
      details.append(body);
      if(s.verification){
        const v=s.verification, ref=document.createElement(v.source?'a':'span');
        if(v.source){ref.href=v.source;ref.target='_blank';ref.rel='noopener noreferrer';}
        ref.textContent='BO3.gg · '+v.state;
        details.append(ref);
      }
      for(const [player,maps] of Object.entries(s.players)){
        const row=document.createElement('div');
        row.textContent=player+' · '+Object.entries(maps).map(([n,v])=>'M'+n+' '+v.kills+'–'+v.deaths+' K-D, ADR '+(v.adr??'s/d')).join(' / ');
        details.append(row);
      }
      const link=document.createElement('a');link.href=s.source;link.textContent='Ver ficha BLAST';link.target='_blank';link.rel='noopener noreferrer';details.append(link);
    }
  }
  line('Páginas sin datos utilizables: '+audit.unavailable_pages+'. Ver cobertura por control en la auditoría.');
}

function renderAudit(audit){
  const parent=$('result');
  function line(text){const el=document.createElement('p');el.textContent=text;parent.append(el);}
  line((audit.retrospective?'Revisión posterior al corte · ':'Auditoría · ')+audit.confirmed+'/'+audit.series+' series corroboradas, '+audit.sample+'/50 observaciones individuales y '+audit.rounds+' rondas en '+audit.maps+' mapas.');
  for(const [name,team] of Object.entries(audit.teams)){
    const v=team.counts;
    line(name+' · Aperturas convertidas: '+(v.converted||0)+'/'+(v.opens||0)+'. Recuperaciones tras primera baja: '+(v.recovered||0)+'/'+(v.lost_open||0)+'. Bajas de intercambio registradas: '+(v.trades||0)+'. Rondas ganadas con menor equipamiento: '+(v.down_buy_wins||0)+'/'+(v.down_buy||0)+'.');
    const d=document.createElement('details'),summary=document.createElement('summary');
    summary.textContent='Observaciones individuales · '+name;d.append(summary);
    for(const [nick,rows] of Object.entries(team.players)){
      const el=document.createElement('div');el.textContent=nick+' · '+rows.length+'/5';d.append(el);
      for(const r of rows){const a=document.createElement('span');a.textContent=r.date.slice(0,10)+' vs. '+r.opponent+' · '+r.kills+'–'+r.deaths+' K-D · '+r.adr+' ADR';d.append(a,document.createElement('br'));}
    }
    const floor=document.createElement('p');floor.textContent=team.floor_ratings?'Ratings de serie: '+team.floor_ratings+' · Alertas <0,80: '+(team.floor_alerts.map(x=>x.player+' '+x.rating).join(', ')||'ninguna'):'Piso colectivo: faltan ratings comparables de serie.';d.append(floor);
    parent.append(d);
  }
  for(const [alias,axes] of Object.entries(audit.cipi_diagnostic||{})){
    const box=document.createElement('details'),label=document.createElement('summary');label.textContent='CIPI descriptivo · '+alias;box.append(label);
    for(const [axis,value] of Object.entries(axes)){const row=document.createElement('div');row.textContent=axis+' · '+value;box.append(row);}parent.append(box);
  }
  const d=document.createElement('details'),title=document.createElement('summary');title.textContent='Ver los 12 controles R3.3/R3.4';d.append(title);
  for(const [key,v] of Object.entries(audit.controls)){const el=document.createElement('p');el.textContent=key.replaceAll('_',' ')+' · '+v.estado+' · '+v.detalle;d.append(el);}
  parent.append(d);
}

function renderIdentity(identity){
  const box=document.createElement('section');
  const heading=document.createElement('h3');
  heading.textContent='T1 · '+identity.title+' · '+identity.status;
  box.append(heading);
  function text(parent,value){const el=document.createElement('p');el.textContent=value;parent.append(el);}
  function source(parent,url,label){if(!url)return;const el=document.createElement('a');el.href=url;el.target='_blank';el.rel='noopener noreferrer';el.textContent=label;parent.append(el);}
  text(box,'Consulta BLAST · '+identity.primary_checked);
  if(identity.secondary_checked)text(box,'Consulta BO3.gg · '+identity.secondary_checked+(identity.secondary_post_cutoff?' · posterior al corte':''));
  for(const [team,t] of Object.entries(identity.teams)){
    text(box,team+' · Plantilla publicada: '+(t.roster.join(', ')||'pendiente'));
    source(box,t.roster_source,'Ver plantilla');
    text(box,'Quinteto titular del encuentro: '+t.fixture_lineup+(t.starters.length?' · '+t.starters.join(', '):''));
    for(const s of t.series){
      const d=document.createElement('details'), title=document.createElement('summary');
      title.textContent=s.date.slice(0,10)+' vs. '+s.opponent+' · '+s.prematch_status+' al corte';d.append(title);
      text(d,'Participación documentada al corte: '+(s.prematch_players.join(', ')||'pendiente'));
      if(identity.secondary_post_cutoff)text(d,'Revisión posterior · '+s.status+' · '+(s.players.join(', ')||'pendiente'));
      if(s.outside_roster.length)text(d,'Participantes fuera de la plantilla publicada: '+s.outside_roster.join(', '));
      source(d,s.source,'Ficha BLAST');source(d,s.secondary_source,' · Ficha BO3.gg');box.append(d);
    }
  }
  $('result').append(box);
}

function renderSources(t3){
  const section=document.createElement('section'),title=document.createElement('h3');
  title.textContent='T3 · Corroboración multifuente · '+t3.status;section.append(title);
  function text(parent,value){const el=document.createElement('p');el.textContent=value;parent.append(el);}
  text(section,'Antes del corte: '+t3.confirmed_before+'/'+t3.series.length+' marcadores y '+t3.kd_before+' registros individuales de K-D corroborados.');
  text(section,'Última revisión: '+t3.confirmed_review+'/'+t3.series.length+' marcadores y '+t3.kd_review+' registros individuales de K-D corroborados.');
  for(const r of t3.series){
    const box=document.createElement('details'),summary=document.createElement('summary');
    summary.textContent=r.date.slice(0,10)+' · '+r.team+' vs. '+r.opponent+' · '+r.prematch;box.append(summary);
    text(box,'Última revisión · '+r.review+(r.after_cutoff?' · posterior al corte':''));
    for(const [label,url,at] of [['BLAST',r.primary,r.primary_checked],['BO3.gg',r.secondary,r.secondary_checked]]){
      if(url){const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=label+' · '+(at||'fecha pendiente');box.append(a,document.createElement('br'));}
    }
    for(const p of r.players)text(box,p.player+' · '+p.state);
    section.append(box);
  }
  $('result').append(section);
}

function renderContext(context){
  const panel=document.createElement('section'),title=document.createElement('h3');
  title.textContent='T4 · Contexto público · '+context.status;panel.append(title);
  for(const item of context.items){
    const row=document.createElement('p'),link=document.createElement('a');
    link.href=item.source;link.target='_blank';link.rel='noopener noreferrer';link.textContent=item.text;
    row.append(item.category+' · ',link,' · '+item.scope+' · Consulta '+item.checked);
    if(item.published)row.append(' · Publicación '+item.published);
    panel.append(row);
  }
  for(const s of context.sources){const row=document.createElement('p');row.textContent=s.name+' · '+s.state+(s.checked?' · '+s.checked:'');panel.append(row);}
  const pending=document.createElement('p');pending.textContent='Por verificar: '+context.pending.join(', ')+'. '+context.scoring_effect+'.';panel.append(pending);
  $('result').append(panel);
}

function renderCasefile(report){
  const f=report.casefile, box=document.createElement('section');
  function add(parent,tag,value){const el=document.createElement(tag);el.textContent=value;parent.append(el);return el;}
  add(box,'h3','T5 · Expediente y transferibilidad · '+f.status);
  add(box,'p',f.observations_at_cutoff+'/50 observaciones con K-D de todos los mapas antes del corte · '+f.series_count+'/10 series documentadas.');
  for(const [slot,t] of Object.entries(f.teams)){
    add(box,'h4',slot+' · '+t.name);
    for(const player of t.players){
      const d=document.createElement('details');box.append(d);
      add(d,'summary',player.alias+' · '+player.name+' · '+player.observations.filter(r=>r.kd_at_cutoff).length+'/5');
      for(const r of player.observations){
        add(d,'p',r.date.slice(0,10)+' vs. '+r.opponent+' · K-D al corte: '+(r.kd_at_cutoff?r.kd_at_cutoff.join('–'):'pendiente')+' · Segunda fuente al corte: '+r.prematch+' · Última revisión: '+r.review);
        for(const [label,url] of [['BLAST',r.source],['BO3.gg',r.secondary]])if(url){const a=add(d,'a',label+' ');a.href=url;a.target='_blank';a.rel='noopener noreferrer';}
      }
    }
    const group=document.createElement('details');box.append(group);add(group,'summary','Series colectivas · '+t.series.length+'/5');
    for(const s of t.series){add(group,'p',s.date.slice(0,10)+' vs. '+s.opponent+' · '+s.maps.map(m=>m.map.replace('de_','')+' '+m.score.join('–')).join(' / '));}
  }
  add(box,'p',f.transferability+' Faltantes: '+f.missing.join(', ')+'.');
  if(report.workflow){
    add(box,'h3','Fases y cerrojo · '+report.evidence_state);
    for(const phase of report.workflow.phases){
      const d=document.createElement('details');box.append(d);add(d,'summary',phase.name);
      for(const step of phase.steps)add(d,'p',step.id+' · '+step.label+' · '+step.state+' · '+step.reason);
    }
    const metrics=document.createElement('details');box.append(metrics);add(metrics,'summary','MSI y variabilidad individual');
    for(const [key,value] of Object.entries(report.workflow.msi))add(metrics,'p',key+' · '+(value||'Pendiente de evidencia'));
    for(const [team,players] of Object.entries(report.workflow.pve_kd_range))for(const [nick,v] of Object.entries(players)){
      add(metrics,'p',team+' · '+nick+' · Diferencial K-D por serie: '+(v.series?v.minimum+' a '+v.maximum:'sin muestra')+' · '+v.series+'/5.');
    }
    const a=report.workflow.adverse;
    if(a)add(box,'p','Escenario hipotético: cambiar una victoria por derrota el '+a.changed_date.slice(0,10)+'. Margen experimental del seleccionado: '+a.margin+'.');
  }
  $('result').append(box);
}
