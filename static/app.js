const examRoot=document.querySelector('.exam');
const qs=[...document.querySelectorAll('.question')];
const nums=[...document.querySelectorAll('.question-number')];
const form=document.getElementById('examForm');
let i=Number(examRoot?.dataset.currentQuestion ?? 0) || 0;
let remaining=Number(examRoot?.dataset.remaining ?? 0) || 0;
const isPaused=examRoot?.dataset.paused==='1';
let saveTimer=null;

function collectState(){
  const answers={}; const chutes=[];
  qs.forEach(q=>{
    const n=q.dataset.num;
    const checked=q.querySelector('input[name="q'+n+'"]:checked');
    const chute=q.querySelector('input[name="chute_'+n+'"]');
    if(checked) answers[n]=checked.value;
    if(chute?.checked) chutes.push(Number(n));
  });
  return {answers,chutes,current_question:i};
}

async function saveState(){
  try{
    const r=await fetch('/salvar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collectState())});
    const data=await r.json();
    if(typeof data.remaining==='number') remaining=data.remaining;
  }catch(e){}
}

function scheduleSave(){
  clearTimeout(saveTimer);
  saveTimer=setTimeout(saveState,250);
}

function updateMap(){
  qs.forEach((q,j)=>{
    const n=q.dataset.num,b=nums[j];
    const answer=q.querySelector('input[name="q'+n+'"]:checked');
    const chute=q.querySelector('input[name="chute_'+n+'"]');
    const small=b?.querySelector('small');
    b?.classList.toggle('answered',!!answer);
    b?.classList.toggle('chute',!!chute?.checked);
    if(small) small.textContent=chute?.checked?'🎯':answer?'✓':'—';
  });
}

function show(n,instant=false){
  if(!qs.length)return;
  i=Math.max(0,Math.min(qs.length-1,n));
  qs.forEach((q,j)=>q.classList.toggle('active',j===i));
  nums.forEach((b,j)=>b.classList.toggle('current',j===i));
  const progress=document.getElementById('progress');
  if(progress) progress.textContent=i+1+' / '+qs.length;
  const finish=document.querySelector('.finish');
  const allAnswered=qs.every(q=>!!q.querySelector('input[name="q'+q.dataset.num+'"]:checked'));
  if(finish) finish.hidden=!allAnswered;
  const prev=document.getElementById('prev'),next=document.getElementById('next');
  if(prev) prev.disabled=i===0;
  if(next) next.disabled=i===qs.length-1;
  updateMap();
  scheduleSave();
  window.scrollTo({top:0,behavior:instant?'auto':'smooth'});
}

function renderTimer(){
  const el=document.getElementById('timer');
  if(!el)return;
  const total=Math.max(0,Math.floor(remaining));
  const h=Math.floor(total/3600),m=Math.floor((total%3600)/60),s=total%60;
  el.textContent=[h,m,s].map(v=>String(v).padStart(2,'0')).join(':');
  el.classList.toggle('timer-warning',total<=1800 && total>300);
  el.classList.toggle('timer-danger',total<=300);
}

async function finishByTime(){
  await saveState();
  const hidden=document.createElement('input');
  hidden.type='hidden'; hidden.name='finalizar'; hidden.value='1';
  form.appendChild(hidden);
  form.submit();
}

document.getElementById('prev')?.addEventListener('click',()=>show(i-1));
document.getElementById('next')?.addEventListener('click',()=>show(i+1));
nums.forEach((b,j)=>b.addEventListener('click',()=>show(j)));
document.getElementById('openMap')?.addEventListener('click',()=>document.getElementById('questionMap')?.classList.add('open'));
document.getElementById('closeMap')?.addEventListener('click',()=>document.getElementById('questionMap')?.classList.remove('open'));

document.querySelectorAll('#questions input').forEach(el=>el.addEventListener('change',()=>{updateMap();show(i,true);}));

form?.addEventListener('submit',e=>{
  const unanswered=qs.filter(q=>!q.querySelector('input[name="q'+q.dataset.num+'"]:checked')).length;
  if(e.submitter?.name==='finalizar' && unanswered>0 && remaining>0){
    if(!confirm('Você ainda possui '+unanswered+' questão(ões) sem resposta. Deseja finalizar mesmo assim?')) e.preventDefault();
  }
});

function tick(){
  if(remaining<=0)return;
  remaining=Math.max(0,remaining-1);
  renderTimer();
  if(remaining===0) finishByTime();
}

show(i,true);
updateMap();
renderTimer();
if(!isPaused) setInterval(tick,1000);
setInterval(saveState,10000);

// O formulário de pausa usa submit nativo para garantir que a pausa sempre seja enviada ao servidor.
window.addEventListener('beforeunload',()=>{
  try{
    navigator.sendBeacon('/salvar',new Blob([JSON.stringify(collectState())],{type:'application/json'}));
  }catch(e){}
});
