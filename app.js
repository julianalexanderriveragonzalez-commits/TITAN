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
  show((freeze?'Predicción congelada · ID '+r.id+'\n':'')+(rep.tie_break_explanation?'Desempate administrativo: ':'Selección provisional: ')+rep.selection+'\nTipo: '+rep.selection_type+'\nConfianza: '+rep.confidence+'\nEstado: '+rep.evidence_state+'\n\nCarencias:\n'+Object.entries(rep.missing_evidence).map(([team,gaps])=>team+': '+gaps.join('; ')).join('\n')+'\n\nControles pendientes: '+Object.values(rep.controls_R33_R34).filter(v=>v!=='COMPLETADA').length+'\n\n'+(rep.tie_break_explanation||''));
  if(rep.blind_scoring){
    const blind=rep.blind_scoring;
    const line=document.createElement('p');
    line.textContent='Puntuación ciega · Equipo A: '+blind.scores.A+' · Equipo B: '+blind.scores.B+' · '+(blind.sporting_side?'Indicador favorable a '+blind.sporting_side:'Empate deportivo');
    $('result').append(line);
  }
  if(rep.audit) renderAudit(rep.audit);
  if(rep.research) renderEvidence(rep.research);
  if(freeze) await history();
 }catch(e){show('Error: '+e.message)}
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
      for(const r of rows){const a=document.createElement('a');a.href=r.source;a.target='_blank';a.rel='noopener noreferrer';a.textContent=r.date.slice(0,10)+' vs. '+r.opponent+' · '+r.kills+'–'+r.deaths+' K-D · '+r.adr+' ADR';d.append(a,document.createElement('br'));}
    }
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
