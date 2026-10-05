const qs=[...document.querySelectorAll('.question')];
const nums=[...document.querySelectorAll('.question-number')];
let i=0;

function show(n){
  if(!qs.length)return;
  i=Math.max(0,Math.min(qs.length-1,n));
  qs.forEach((q,j)=>q.classList.toggle('active',j===i));
  nums.forEach((b,j)=>b.classList.toggle('current',j===i));
  const progress=document.getElementById('progress');
  const currentNum=document.getElementById('currentNum');
  const bar=document.getElementById('progressBar');
  if(progress)progress.textContent=`${i+1} / ${qs.length}`;
  if(currentNum)currentNum.textContent=String(qs[i].dataset.num).padStart(2,'0');
  if(bar)bar.style.width=`${((i+1)/qs.length)*100}%`;
  document.getElementById('prev').disabled=i===0;
  document.getElementById('next').disabled=i===qs.length-1;
  updateMap();
  window.scrollTo({top:0,behavior:'smooth'});
}

function updateMap(){
  qs.forEach((q,j)=>{
    const num=q.dataset.num;
    const b=nums[j];
    const answer=q.querySelector(`input[name="q${num}"]:checked`);
    const chute=q.querySelector(`input[name="chute_${num}"]`);
    const small=b?.querySelector('small');
    b?.classList.toggle('answered',!!answer);
    b?.classList.toggle('chute',!!chute?.checked);
    if(small)small.textContent=chute?.checked?'🎯':answer?'✓':'—';
  });
}

document.getElementById('prev').onclick=()=>show(i-1);
document.getElementById('next').onclick=()=>show(i+1);
nums.forEach((b,j)=>b.addEventListener('click',()=>show(j)));

document.querySelectorAll('#questions input').forEach(el=>{
  el.addEventListener('change',updateMap);
});

const jumpButton=document.getElementById('jumpButton');
const jumpPanel=document.getElementById('jumpPanel');
const jumpInput=document.getElementById('jumpInput');
const jumpGo=document.getElementById('jumpGo');

jumpButton?.addEventListener('click',()=>{
  jumpPanel.hidden=!jumpPanel.hidden;
  if(!jumpPanel.hidden){jumpInput.focus();jumpInput.select();}
});

function jump(){
  const n=parseInt(jumpInput.value,10);
  if(Number.isNaN(n)||n<1||n>qs.length)return;
  show(n-1);
  jumpPanel.hidden=true;
  jumpInput.value='';
}
jumpGo?.addEventListener('click',jump);
jumpInput?.addEventListener('keydown',e=>{if(e.key==='Enter')jump();});

const map=document.getElementById('questionMap');
document.getElementById('openMap')?.addEventListener('click',()=>map.classList.add('open'));
document.getElementById('closeMap')?.addEventListener('click',()=>map.classList.remove('open'));

nums.forEach(b=>b.addEventListener('click',()=>{
  map?.classList.remove('open');
}));

show(0);
updateMap();