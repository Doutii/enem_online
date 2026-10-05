const qs=[...document.querySelectorAll('.question')];
const nums=[...document.querySelectorAll('.question-number')];
const form=document.getElementById('examForm');
let i={{ current_question }} || 0;
let remaining={{ remaining }} || 0;
let saveTimer=null;

function collectState(){
  const answers={}; const chutes=[];
  qs.forEach(q=>{
    const n=q.dataset.num;
    const checked=q.querySelector(`input[name="q${n}"]:checked`);
    const chute=q.querySelector(`input[name="chute_${n}"]`);
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
    const answer=q.querySelector(`input[name="q${n}"]:checked`);
    const chute=q.querySelector(`input[name="chute_${n}"]`);
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
  const progress=document.getElementById('progress'),bar=document.getElementById('progressBar');
  if(progress)progress.textContent=`${i+1} / ${qs.length}`;
  if(bar)bar.style.width=`${((i+1)/qs.length)*100}%`;
  document.getElementById('prev').disabled=i===0;
  document.getElementById('next').disabled=i===qs.length-1;
  updateMap();
  scheduleSave();
  window.scrollTo({top:0,behavior:instant?'auto':'smooth'});
}

document.getElementById('prev').onclick=()=>show(i-1);
document.getElementById('next').onclick=()=>show(i+1);
nums.forEach((b,j)=>b.addEventListener('click',()=>show(j)));

document.querySelectorAll('#questions input').forEach(el=>el.addEventListener('change',()=>{updateMap();scheduleSave();}));

form?.addEventListener('submit',e=>{
  const unanswered=qs.filter(q=>!q.querySelector(`input[name="q${q.dataset.num}"]:checked`)).length;
  if(e.submitter?.name==='finalizar' && unanswered>0 && remaining>0){
    if(!confirm(`Você ainda possui ${unanswered} questão(ões) sem resposta. Deseja finalizar mesmo assim?`)) e.preventDefault();
  }
});

function renderTimer(){
  const el=document.getElementById('timer');
  if(!el)return;
  const total=Math.max(0,remaining);
  const h=Math.floor(total/3600),m=Math.floor((total%3600)/60),s=total%60;
  el.textContent=[h,m,s].map(v=>String(v).padStart(2,'0')).join(':');
  el.classList.toggle('timer-warning',total<=1800);
  el.classList.toggle('timer-danger',total<=300);
}

function tick(){
  remaining=Math.max(0,remaining-1);
  renderTimer();
  if(remaining===0){
    saveState().finally(()=>{
      const hidden=document.createElement('input'); hidden.type='hidden'; hidden.name='finalizar'; hidden.value='1'; form.appendChild(hidden);
      form.submit();
    });
  }
}
setInterval(tick,1000);

show(i,true);
updateMap();
renderTimer();
setInterval(saveState,10000);
