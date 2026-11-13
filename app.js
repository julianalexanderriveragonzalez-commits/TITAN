'use strict';
const $ = id => document.getElementById(id);
function data() {
  const a=$('a').value.trim(),b=$('b').value.trim(),d=$('date').value;
  if(!a || !b || a===b || !d) throw Error('Introduce dos equipos distintos y la fecha del encuentro.');
  return {match:{id:crypto.randomUUID(),team_a:a,team_b:b,cutoff:d+':00-05:00'},teams:{[a]:JSON.parse($('sa').value),[b]:JSON.parse($('sb').value)}};
}
async function api(url,method='GET',body){
  const r=await fetch(url,{method,headers:method==='POST'?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,cache:'no-store'});
  const value=await r.json(); if(!r.ok) throw Error(value.error||'Error de servidor'); return value;
}
function show(text){$('result').textContent=text;}
async function action(freeze){
 try{
  show('Procesando información…');
  const p=data(); const r=await api(freeze?'/api/freeze':'/api/analyze','POST',p);
  const rep=freeze?r.report:r;
  show((freeze?'Predicción congelada · ID '+r.id+'\n':'')+'Ganador seleccionado: '+rep.selection+'\nTipo: '+rep.selection_type+'\nConfianza: '+rep.confidence+'\nEstado: '+rep.evidence_state+'\n\nCarencias:\n'+Object.entries(rep.missing_evidence).map(([team,gaps])=>team+': '+gaps.join('; ')).join('\n')+'\n\nControles pendientes: '+Object.keys(rep.controls_R33_R34).length+'\n\n'+(rep.tie_break_explanation||''));
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
