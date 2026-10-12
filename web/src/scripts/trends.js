(function(){
"use strict";
const $=s=>document.querySelector(s);
const range=(a,b)=>Array.from({length:b-a},(_,i)=>a+i);
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
const fmtPct=(v,d)=>(v*100).toFixed(d===undefined?1:d)+'%';
const mean=a=>a.reduce((x,y)=>x+y,0)/a.length;

/* ---------- Reference data ---------- */
const LINES=[
  {id:'Red', name:'Red',   color:'#c60c30',hw:6, base:26,dly:.022},
  {id:'Blue',name:'Blue',  color:'#00a1de',hw:7, base:22,dly:.028},
  {id:'Brn', name:'Brown', color:'#62361b',hw:6, base:17,dly:.024},
  {id:'G',   name:'Green', color:'#009b3a',hw:9, base:14,dly:.026},
  {id:'Org', name:'Orange',color:'#f9461c',hw:9, base:11,dly:.020},
  {id:'P',   name:'Purple',color:'#522398',hw:12,base:8, dly:.024},
  {id:'Pink',name:'Pink',  color:'#e27ea6',hw:10,base:9, dly:.030},
  {id:'Y',   name:'Yellow',color:'#f9e300',hw:15,base:3, dly:.015}
];
const COL=id=>LINES.find(l=>l.id===id).color;
const LI=id=>LINES.findIndex(l=>l.id===id);
const F=[.22,.16,.14,.14,.3,.58,.85,1,1,.85,.7,.68,.7,.7,.74,.86,1,1,.92,.7,.55,.45,.36,.28];
const D=[.6,.5,.5,.5,.7,1,1.5,1.9,1.8,1.3,1,1,1.05,1,1.1,1.4,1.9,2,1.6,1.1,.9,.8,.7,.6];
const DPS=[
  {k:'am', n:'AM peak', t:'6–9 AM',    h:[6,7,8]},
  {k:'mid',n:'Midday',  t:'9 AM–4 PM', h:range(9,16)},
  {k:'pm', n:'PM peak', t:'4–7 PM',    h:[16,17,18]},
  {k:'eve',n:'Evening and overnight',t:'7 PM–6 AM',h:range(0,6).concat(range(19,24))}
];
const FP=DPS.map(p=>mean(p.h.map(h=>F[h]))),DDP=DPS.map(p=>mean(p.h.map(h=>D[h])));
const WKT=[.55,.85,.65,.95],WKD=[.7,.85,.8,.9];
const STA=[
  {n:'Clark/Lake',id:40380,lines:['Blue','Brn','G','Org','P','Pink']},
  {n:'Belmont',id:41320,lines:['Red','Brn','P']},
  {n:'Fullerton',id:41220,lines:['Red','Brn','P']},
  {n:'Howard',id:40900,lines:['Red','P','Y']},
  {n:'Roosevelt',id:41400,lines:['Red','Org','G']},
  {n:'Jefferson Park',id:41280,lines:['Blue']},
  {n:'Damen',id:40590,lines:['Blue']},
  {n:'Racine',id:40470,lines:['Blue']},
  {n:'O’Hare',id:40890,lines:['Blue']},
  {n:'Kimball',id:41290,lines:['Brn']},
  {n:'Midway',id:40930,lines:['Org']},
  {n:'Halsted',id:41130,lines:['Org']},
  {n:'95th/Dan Ryan',id:40450,lines:['Red']},
  {n:'Cermak-Chinatown',id:41000,lines:['Red']},
  {n:'Harlem/Lake',id:40020,lines:['G']},
  {n:'Ashland/63rd',id:40290,lines:['G']},
  {n:'Cicero',id:40480,lines:['G']},
  {n:'Pulaski',id:40150,lines:['Pink']},
  {n:'Linden',id:41050,lines:['P']},
  {n:'Dempster-Skokie',id:40140,lines:['Y']}
];
// One entry per line at each station, so a delayed line isn't bundled with quieter ones
const SL=(function(){const r=mulberry32(55);return STA.flatMap(s=>s.lines.map(L=>({n:s.n,id:s.id,L,li:[LI(L)],f1:.6+r()*1.1})))})();
const hash=(i,k)=>{const x=Math.sin(i*12.9898+k*78.233)*43758.5453;return x-Math.floor(x)};

/* ---------- Calendar ---------- */
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const DOWN=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const N=730,END=Date.UTC(2026,8,29);
const DAYS=range(0,N).map(i=>{const t=END-(N-1-i)*864e5,d=new Date(t);return {t,dow:(d.getUTCDay()+6)%7,dm:d.getUTCDate(),mo:d.getUTCMonth(),yr:d.getUTCFullYear(),doy:Math.floor((t-Date.UTC(d.getUTCFullYear(),0,0))/864e5)}});
const di=(y,m,d)=>N-1-Math.round((END-Date.UTC(y,m-1,d))/864e5);
const fmtD=i=>MON[DAYS[i].mo]+' '+DAYS[i].dm;
const fmtDL=i=>DOWN[DAYS[i].dow]+' '+fmtD(i);
const EV=[
  {k:'A',t:'Winter storm slows every line',a:di(2026,1,25),b:di(2026,1,26)},
  {k:'B',t:'Pink Line track work with reduced service',a:di(2026,6,8),b:di(2026,6,21)},
  {k:'C',t:'Blue Line signal problems',a:di(2026,7,14),b:di(2026,7,22)},
  {k:'D',t:'API outage, about 6 hours of polls missing',a:di(2026,8,3),b:di(2026,8,3)},
  {k:'E',t:'Heat wave slow zones on the Red Line',a:di(2026,8,18),b:di(2026,8,20)}
];
const inEv=(k,i)=>{const e=EV.find(x=>x.k===k);return i>=e.a&&i<=e.b};

/* ---------- Sample daily mart (date x line x time of day) ---------- */
const ROWS=[],HEALTH=[];
(function(){
  const r=mulberry32(2026);
  for(let i=0;i<N;i++){
    const day=DAYS[i],wk=day.dow>=5;
    const season=1+.22*Math.cos(2*Math.PI*(day.doy-15)/365);
    const trend=1.06-.12*(i/(N-1));
    const dn=.85+r()*.3;
    const storm=inEv('A',i),pinkW=inEv('B',i),blueS=inEv('C',i),outage=inEv('D',i),heat=inEv('E',i);
    const burst=r()<.04?12+Math.floor(r()*20):0;
    const fdp=DPS.map((p,pi)=>{const polls=p.h.length*60;let f=Math.round(polls*.0015*(r()*2));if(pi===3&&burst)f+=burst;return f});
    if(outage){fdp[0]+=60;fdp[1]+=300}
    ROWS.push(LINES.map(L=>DPS.map((p,pi)=>{
      const polls=p.h.length*60,ok=Math.max(0,polls-fdp[pi]);
      const tf=FP[pi]*(wk?WKT[pi]:1);
      let dl=L.dly*DDP[pi]*(wk?WKD[pi]:1)*season*trend*dn*(.85+r()*.3);
      let tr=L.base*tf*(.94+r()*.12);
      if(storm){dl*=2.2;tr*=.9}
      if(pinkW&&L.id==='Pink'){dl*=1.5;tr*=.75}
      if(blueS&&L.id==='Blue')dl*=2.4;
      if(heat)dl*=(L.id==='Red'?2:1.25);
      dl=Math.min(.25,dl);
      const heff=Math.min(30,L.hw/Math.max(tf,.12));
      const head=heff*(1+5*dl)*(.97+r()*.06);
      const sp=Math.min(.5,.05+(1-Math.min(1,tf))*.22);
      const t=tr*ok;
      return {polls,ok,t,d:t*dl,hs:head*t,hn:t,en:t,sn:t*sp};
    })));
    HEALTH.push({polls:1440,fail:fdp.reduce((a,b)=>a+b,0)});
  }
})();

/* ---------- State and aggregation ---------- */
const RL={30:'30 days',90:'90 days',180:'6 months',365:'year'};
const S={range:90,dayType:'all',dp:'all',line:'all',tab:'dl'};
const lineIdx=()=>S.line==='all'?range(0,LINES.length):[LI(S.line)];
const dpIdx=()=>S.dp==='all'?[0,1,2,3]:[DPS.findIndex(p=>p.k===S.dp)];
const winFrom=()=>N-S.range,winTo=()=>N-1;
const okDay=i=>S.dayType==='all'||(S.dayType==='wd'?DAYS[i].dow<5:DAYS[i].dow>=5);
const Z=()=>({polls:0,ok:0,t:0,d:0,hs:0,hn:0,en:0,sn:0});
function add(s,x){s.polls+=x.polls;s.ok+=x.ok;s.t+=x.t;s.d+=x.d;s.hs+=x.hs;s.hn+=x.hn;s.en+=x.en;s.sn+=x.sn;return s}
function daySum(i,lines,dps){const s=Z();for(const li of lines)for(const pi of dps)add(s,ROWS[i][li][pi]);return s}
function winSum(a,b,lines,dps){const s=Z();for(let i=a;i<=b;i++){if(!okDay(i))continue;for(const li of lines)for(const pi of dps)add(s,ROWS[i][li][pi])}return s}
function healthSum(a,b){let polls=0,fail=0;for(let i=a;i<=b;i++){if(!okDay(i))continue;polls+=HEALTH[i].polls;fail+=HEALTH[i].fail}return {polls,fail}}
const M={
  dl:{f:s=>s.d/s.t},
  head:{f:s=>s.hs/s.hn},
  trains:{f:(s,n)=>s.t/(s.ok/n)}
};
function series(a,b,lines,dps){const idx=[],ds=[];for(let i=a;i<=b;i++){if(!okDay(i))continue;idx.push(i);ds.push(daySum(i,lines,dps))}return {idx,ds}}
const metricArr=(ds,k,n)=>ds.map(s=>M[k].f(s,n));
function rollArr(ds,k,n,w){w=w||7;return ds.map((_,j)=>{const s=Z();for(let q=Math.max(0,j-w+1);q<=j;q++)add(s,ds[q]);return M[k].f(s,n)})}
let CTX={};
function buildCtx(){
  const lines=lineIdx(),dps=dpIdx();
  CTX={lines,dps,n:lines.length,
    cur:series(winFrom(),winTo(),lines,dps),
    prior:series(winFrom()-S.range,winFrom()-1,lines,dps)};
}
function weekly(){
  const keys=[],map=new Map();
  for(let i=winFrom();i<=winTo();i++){const k=i-DAYS[i].dow;if(!map.has(k)){map.set(k,keys.length);keys.push(k)}}
  const W=LINES.map(()=>keys.map(()=>Z()));
  const dps=dpIdx();
  for(let i=winFrom();i<=winTo();i++){
    if(!okDay(i))continue;
    const w=map.get(i-DAYS[i].dow);
    for(let li=0;li<LINES.length;li++)add(W[li][w],daySum(i,[li],dps));
  }
  return {keys,W};
}

/* ---------- Controls ---------- */
function renderControls(){
  $('#ranges').innerHTML=Object.entries(RL).map(([k,v])=>`<button type="button" data-range="${k}" aria-pressed="${S.range==k}">${k==30?'30 days':k==90?'90 days':k==180?'6 months':'1 year'}</button>`).join('');
  $('#daytypes').innerHTML=[['all','All days'],['wd','Weekdays'],['we','Weekends']].map(([k,v])=>`<button type="button" data-day="${k}" aria-pressed="${S.dayType===k}">${v}</button>`).join('');
  $('#dps').innerHTML=`<button type="button" data-dp="all" aria-pressed="${S.dp==='all'}">All day</button>`+DPS.map(p=>`<button type="button" data-dp="${p.k}" title="${p.t}" aria-pressed="${S.dp===p.k}">${p.n}</button>`).join('');
  $('#lines').innerHTML=`<button type="button" data-line="all" aria-pressed="${S.line==='all'}">All lines</button>`+
    LINES.map(L=>`<button type="button" data-line="${L.id}" aria-pressed="${S.line===L.id}"><i class="dot" style="background:${L.color}"></i>${L.name}</button>`).join('');
  document.querySelectorAll('#tabs button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===S.tab)));
}

/* ---------- KPIs ---------- */
function sparkSvg(vals){
  const mn=Math.min(...vals),mx=Math.max(...vals),sp=(mx-mn)||1,L=vals.length-1||1;
  const pt=(v,j)=>`${(j/L*94+1).toFixed(1)},${(25-(v-mn)/sp*22).toFixed(1)}`;
  return `<svg class="spark" viewBox="0 0 96 28" preserveAspectRatio="none" aria-hidden="true"><polyline fill="none" stroke="var(--ink)" stroke-width="1.8" vector-effect="non-scaling-stroke" points="${vals.map(pt).join(' ')}"/></svg>`;
}
function renderKPIs(){
  const {lines,dps,n,cur}=CTX;
  const a=winSum(winFrom(),winTo(),lines,dps),b=winSum(winFrom()-S.range,winFrom()-1,lines,dps);
  const pt=d=>(d>=0?'+':'-')+Math.abs(d*100).toFixed(1)+'%';
  const defs=[
    {l:'Trains in service',k:'trains',fmt:v=>v.toFixed(0),df:d=>(d>=0?'+':'-')+Math.abs(d).toFixed(0),hi:null,eps:.5},
    {l:'Delay rate',k:'dl',fmt:v=>fmtPct(v,1),df:pt,hi:false,eps:.0005},
    {l:'Headway',k:'head',fmt:v=>v.toFixed(1)+' min',df:d=>(d>=0?'+':'-')+Math.abs(d).toFixed(1)+' min',hi:false,eps:.05}
  ];
  let html=defs.map(k=>{
    const v=M[k.k].f(a,n),p=M[k.k].f(b,n),d=v-p;
    let cls='';if(k.hi!==null&&Math.abs(d)>=k.eps)cls=((d>0)===k.hi)?'good':'bad';
    return `<div class="kpi"><div class="l">${k.l}</div><div class="v">${k.fmt(v)}</div><div class="d ${cls}">${d>=0?'▲':'▼'} ${k.df(d)} vs prior ${RL[S.range]}</div>${sparkSvg(rollArr(cur.ds,k.k,n))}</div>`;
  }).join('');
  const ha=healthSum(winFrom(),winTo()),hb=healthSum(winFrom()-S.range,winFrom()-1);
  const sa=1-ha.fail/ha.polls,sb=1-hb.fail/hb.polls,dd=sa-sb;
  const daily=[];for(let i=winFrom();i<=winTo();i++)if(okDay(i))daily.push(1-HEALTH[i].fail/HEALTH[i].polls);
  html+=`<div class="kpi"><div class="l">Data availability</div><div class="v">${fmtPct(sa,2)}</div><div class="d ${Math.abs(dd)>=.0002?(dd>0?'good':'bad'):''}">${dd>=0?'▲':'▼'} ${(dd>=0?'+':'-')+Math.abs(dd*100).toFixed(2)} pt vs prior ${RL[S.range]}</div>${sparkSvg(daily)}</div>`;
  $('#kpis').innerHTML=html;
}

/* ---------- Trend chart ---------- */
function nice(span){const raw=span/4;const mag=Math.pow(10,Math.floor(Math.log10(raw)));const n=raw/mag;return (n<=1?1:n<=2?2:n<=5?5:10)*mag}
function renderChart(){
  const box=$('#chart');
  const W=Math.max(280,Math.floor(box.clientWidth)||320),H=270,m={l:46,r:12,t:26,b:26};
  const iw=W-m.l-m.r,ih=H-m.t-m.b;
  const k=S.tab,n=CTX.n,cs=CTX.cur,ps=CTX.prior,idx=cs.idx;
  const daily=metricArr(cs.ds,k,n),roll=rollArr(cs.ds,k,n),prev=rollArr(ps.ds,k,n).slice(0,daily.length);
  const Mn=daily.length,step=iw/Math.max(1,Mn-1),X=j=>m.l+j*step;
  const all=daily.concat(roll,prev);
  let lo=Math.min(...all),hi=Math.max(...all);
  if(k==='dl'||k==='head'||k==='trains')lo=0;else lo=Math.floor((lo-.01)*20)/20;
  const st=nice((hi-lo)*1.05||1),max=lo+Math.ceil((hi-lo)/st)*st+(hi-lo<=0?st:0);
  const Y=v=>m.t+ih-((v-lo)/(max-lo))*ih;
  const fmt=k==='dl'?v=>fmtPct(v,1):k==='head'?v=>v.toFixed(1)+' min':k==='trains'?v=>Math.round(v)+' trains':v=>fmtPct(v,1);
  const tick=k==='dl'?v=>(v*100).toFixed(st*100<1?1:0)+'%':k==='head'?v=>v.toFixed(st<1?1:0):k==='trains'?v=>String(Math.round(v)):v=>(v*100).toFixed(st*100<1?1:0)+'%';
  const col=S.line==='all'?'var(--ink)':COL(S.line);
  let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Trend chart">`;
  const evs=EV.map(e=>{let j0=-1,j1=-1;idx.forEach((i,j)=>{if(i>=e.a&&i<=e.b){if(j0<0)j0=j;j1=j}});return j0<0?null:{e,j0,j1}}).filter(Boolean);
  evs.forEach(o=>{const x0=Math.max(m.l,X(o.j0)-step/2),x1=Math.min(m.l+iw,X(o.j1)+step/2),w=Math.max(3,x1-x0);
    s+=`<rect x="${x0.toFixed(1)}" y="${m.t}" width="${w.toFixed(1)}" height="${ih}" fill="var(--band)"/><circle cx="${(x0+w/2).toFixed(1)}" cy="${m.t-12}" r="8" fill="var(--sel)"/><text x="${(x0+w/2).toFixed(1)}" y="${m.t-8}" text-anchor="middle" font-size="11" font-weight="600" fill="var(--selInk)" style="font-family:var(--ui)">${o.e.k}</text>`});
  const nt=Math.round((max-lo)/st);
  for(let i=0;i<=nt;i++){const v=lo+i*st,y=Y(v);s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--rule)"/><text class="ax" x="${m.l-6}" y="${(y+4).toFixed(1)}" text-anchor="end">${tick(v)}</text>`}
  let lastX=-99;
  for(let j=0;j<Mn;j++){
    const d=DAYS[idx[j]];let lab=null;
    if(S.range<=30){if(j%7===0)lab=fmtD(idx[j])}
    else if(j===0?d.dm<=15:d.mo!==DAYS[idx[j-1]].mo)lab=MON[d.mo]+(d.mo===0?' ’'+String(d.yr).slice(2):'');
    if(lab&&X(j)-lastX>=32){s+=`<text class="ax" x="${X(j).toFixed(1)}" y="${H-8}" text-anchor="middle">${lab}</text>`;lastX=X(j)}
  }
  const path=arr=>arr.map((v,j)=>(j?'L':'M')+X(j).toFixed(1)+' '+Y(v).toFixed(1)).join(' ');
  s+=`<path d="${path(daily)}" fill="none" stroke="${col}" stroke-width="1" opacity=".4"/>`;
  s+=`<path d="${path(prev)}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 3"/>`;
  s+=`<path d="${path(roll)}" fill="none" stroke="${col}" stroke-width="2.6" stroke-linejoin="round"/>`;
  s+=`<line id="hv" y1="${m.t}" y2="${m.t+ih}" stroke="var(--muted)" stroke-dasharray="2 3" style="display:none"/></svg><div class="tip" id="tip"></div>`;
  box.innerHTML=s;
  const svg=box.querySelector('svg'),tip=$('#tip'),hv=$('#hv');
  const show=e=>{
    const r=svg.getBoundingClientRect();
    let j=Math.round(((e.clientX-r.left)*(W/r.width)-m.l)/step);j=Math.max(0,Math.min(Mn-1,j));
    hv.setAttribute('x1',X(j));hv.setAttribute('x2',X(j));hv.style.display='block';
    tip.innerHTML=`<b>${fmtDL(idx[j])}</b><br>Day ${fmt(daily[j])}<br>7-day avg ${fmt(roll[j])}`+(j<prev.length?`<br><span style="opacity:.75">Prior period ${fmt(prev[j])}</span>`:'');
    tip.style.display='block';tip.style.left=Math.min(W-tip.offsetWidth,Math.max(0,X(j)+10))+'px';
  };
  svg.addEventListener('pointermove',show);svg.addEventListener('pointerdown',show);
  svg.addEventListener('pointerleave',()=>{tip.style.display='none';hv.style.display='none'});
  const avgLbl=S.dayType==='all'?'Rolling 7-day average':S.dayType==='wd'?'Rolling average of 7 weekdays':'Rolling average of 7 weekend days';
  $('#legend').innerHTML=`<span><i class="sw thin" style="border-top-color:${col}"></i>Daily</span><span><i class="sw" style="border-top-color:${col}"></i>${avgLbl}</span><span><i class="sw dash"></i>Prior ${RL[S.range]}</span>`;
  $('#evlist').innerHTML=evs.length?evs.map(o=>`<li><span class="evk">${o.e.k}</span><span>${o.e.a===o.e.b?fmtD(o.e.a):fmtD(o.e.a)+' to '+fmtD(o.e.b)}: ${o.e.t} <span style="color:var(--muted)">(sample event)</span></span></li>`).join(''):'<li style="color:var(--muted)">No sample events fall in this range.</li>';
}

/* ---------- Scorecard ---------- */
function spark2(vals,col){
  const v=vals.filter(x=>isFinite(x));if(v.length<2)return '';
  const mn=Math.min(...v),mx=Math.max(...v),sp=(mx-mn)||1;
  const pts=vals.map((x,j)=>isFinite(x)?`${(j/(vals.length-1)*62+1).toFixed(1)},${(18-(x-mn)/sp*16).toFixed(1)}`:null).filter(Boolean).join(' ');
  return `<svg class="tspark" width="64" height="20" viewBox="0 0 64 20" aria-hidden="true"><polyline fill="none" stroke="${col}" stroke-width="1.8" points="${pts}"/></svg>`;
}
function renderScore(WK){
  const dps=dpIdx(),a=winFrom(),b=winTo(),pa=a-S.range,pb=a-1;
  const row=(name,li,color,sel,wkSeries)=>{
    const lines=li===null?range(0,LINES.length):[li];
    const c=winSum(a,b,lines,dps),p=winSum(pa,pb,lines,dps);
    const dl=c.d/c.t,pdl=p.d/p.t,d=dl-pdl;
    const cls=Math.abs(d)>=.0005?(d<0?'good':'bad'):'';
    return `<tr ${li!==null?`data-line="${LINES[li].id}" tabindex="0" aria-selected="${sel}" class="${sel?'sel':''}"`:'class="total"'}><td>${color?`<i class="dot" style="background:${color}"></i>`:''}${name}</td><td>${fmtPct(dl,1)}</td><td class="${cls}">${d>=0?'+':'-'}${Math.abs(d*100).toFixed(1)}%</td><td class="hide-sm">${(c.hs/c.hn).toFixed(1)} min</td><td class="hide-sm">${(c.t/(c.ok/lines.length)).toFixed(0)}</td><td>${spark2(wkSeries,'var(--ink)')}</td></tr>`;
  };
  let h=`<thead><tr><th>Line</th><th>Delayed</th><th>Change</th><th class="hide-sm">Headway</th><th class="hide-sm">Trains</th><th>Weekly trend</th></tr></thead><tbody>`;
  LINES.forEach((L,li)=>{h+=row(L.name,li,L.color,S.line===L.id,WK.W[li].map(s=>s.t?s.d/s.t:NaN))});
  const netW=WK.keys.map((_,w)=>{const s=Z();LINES.forEach((_,li)=>add(s,WK.W[li][w]));return s.t?s.d/s.t:NaN});
  h+=row('Network',null,null,false,netW)+'</tbody>';
  $('#score').innerHTML=h;
}

/* ---------- Weekly heatmap ---------- */
function renderHeat(WK){
  const box=$('#heat');
  const W=Math.max(280,Math.floor(box.clientWidth)||320),lw=58,top=20,rh=22,gap=2;
  const nw=WK.keys.length,cw=(W-lw)/nw,H=top+LINES.length*(rh+gap)+2;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Heatmap of delay rate by line and week">`;
  let lastX=-99,prevMo=-1;
  WK.keys.forEach((k,w)=>{const d=DAYS[Math.max(0,k)];const x=lw+w*cw;if(d.mo!==prevMo){if(x-lastX>=30){s+=`<text class="ax" x="${x.toFixed(1)}" y="11">${MON[d.mo]}</text>`;lastX=x}prevMo=d.mo}});
  let best={v:0};
  LINES.forEach((L,li)=>{
    const y=top+li*(rh+gap),sel=S.line===L.id;
    s+=`<g data-line="${L.id}" style="cursor:pointer"><rect x="0" y="${y}" width="${lw-2}" height="${rh}" fill="transparent"/><circle cx="6" cy="${y+rh/2}" r="4.5" fill="${L.color}"/><text class="ax2" x="16" y="${y+rh/2+4.5}" style="${sel?'font-weight:600':''}">${L.name}</text>`;
    WK.W[li].forEach((c,w)=>{
      if(!c.t)return;
      const v=c.d/c.t;if(v>best.v)best={v,L,k:WK.keys[w]};
      const a=Math.pow(Math.min(1,v/.08),.8);
      s+=`<rect x="${(lw+w*cw).toFixed(1)}" y="${y}" width="${Math.max(1,cw-1).toFixed(1)}" height="${rh}" fill="var(--soft)"/><rect x="${(lw+w*cw).toFixed(1)}" y="${y}" width="${Math.max(1,cw-1).toFixed(1)}" height="${rh}" fill="#b3261e" fill-opacity="${a.toFixed(2)}"><title>${L.name}, week of ${fmtD(Math.max(0,WK.keys[w]))}: ${fmtPct(v,1)} delayed</title></rect>`;
    });
    if(sel)s+=`<rect x="${lw-1}" y="${y-1}" width="${(nw*cw+1).toFixed(1)}" height="${rh+2}" rx="3" fill="none" stroke="var(--ink)" stroke-width="1.5"/>`;
    s+='</g>';
  });
  box.innerHTML=s+'</svg>';
  $('#heatcap').textContent=best.L?`Highest week: ${best.L.name} Line, week of ${fmtD(Math.max(0,best.k))}, with ${fmtPct(best.v,1)} of trains flagged delayed.`:'';
}

/* ---------- Day of week x time of day ---------- */
function renderDow(){
  const box=$('#dow');
  const W=Math.max(260,Math.floor(box.clientWidth)||300),lw=Math.min(112,W*.34),top=22,rh=34,gap=2;
  const cw=(W-lw)/7,H=top+4*(rh+gap)+2;
  const sums=DPS.map(()=>DOWN.map(()=>Z()));
  for(let i=winFrom();i<=winTo();i++)DPS.forEach((_,pi)=>add(sums[pi][DAYS[i].dow],daySum(i,CTX.lines,[pi])));
  const vals=sums.map(r=>r.map(c=>c.t?c.d/c.t:0)),mx=Math.max(...vals.flat())||1;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Delay rate by day of week and time of day">`;
  DOWN.forEach((d,c)=>{const dim=S.dayType==='wd'&&c>=5||S.dayType==='we'&&c<5;s+=`<text class="ax" x="${(lw+c*cw+cw/2).toFixed(1)}" y="14" text-anchor="middle" opacity="${dim?.4:1}">${d}</text>`});
  DPS.forEach((p,pi)=>{
    const y=top+pi*(rh+gap),sel=S.dp===p.k;
    s+=`<text class="ax2" x="0" y="${y+rh/2+4.5}" style="${sel?'font-weight:600':''}">${p.n.replace('Evening and overnight','Evening, night')}</text>`;
    vals[pi].forEach((v,c)=>{
      const a=.1+.9*(v/mx),dim=S.dayType==='wd'&&c>=5||S.dayType==='we'&&c<5;
      s+=`<g opacity="${dim?.4:1}"><rect x="${(lw+c*cw).toFixed(1)}" y="${y}" width="${(cw-2).toFixed(1)}" height="${rh}" rx="2" fill="var(--soft)"/><rect x="${(lw+c*cw).toFixed(1)}" y="${y}" width="${(cw-2).toFixed(1)}" height="${rh}" rx="2" fill="#b3261e" fill-opacity="${a.toFixed(2)}"/><text x="${(lw+c*cw+cw/2-1).toFixed(1)}" y="${y+rh/2+4}" text-anchor="middle" font-size="12" style="font-family:var(--ui);fill:${a>.55?'#fff':'var(--ink)'}">${(v*100).toFixed(1)}%</text></g>`;
    });
    if(sel)s+=`<rect x="${lw-1}" y="${y-1}" width="${(7*cw).toFixed(1)}" height="${rh+2}" rx="3" fill="none" stroke="var(--ink)" stroke-width="1.5"/>`;
  });
  box.innerHTML=s+'</svg>';
}

/* ---------- Stations ---------- */
function renderStations(){
  const dps=dpIdx(),a=winFrom(),b=winTo(),pa=a-S.range,pb=a-1;
  const rows=SL.filter(s=>S.line==='all'||s.L===S.line).map(s=>{
    const c=winSum(a,b,s.li,dps),p=winSum(pa,pb,s.li,dps);
    let over=0,days=0;
    for(let i=a;i<=b;i++){if(!okDay(i))continue;const d=daySum(i,s.li,dps);days++;if(d.d/d.t*s.f1*(.8+.4*hash(i,s.id+s.li[0]))>.04)over++}
    const dl=c.d/c.t*s.f1,pdl=p.d/p.t*s.f1;
    return {...s,dl,d:dl-pdl,over,days};
  }).sort((x,y)=>y.dl-x.dl).slice(0,8);
  let h=`<thead><tr><th>Line/station</th><th>Delayed</th><th>Change</th><th>Days over 4%</th></tr></thead><tbody>`;
  rows.forEach(s=>{
    const cls=Math.abs(s.d)>=.0005?(s.d<0?'good':'bad'):'';
    h+=`<tr><td><div class="st"><i class="dot sm" style="background:${COL(s.L)}"></i>${s.n}</div></td><td>${fmtPct(s.dl,1)}</td><td class="${cls}">${s.d>=0?'+':'-'}${Math.abs(s.d*100).toFixed(1)}%</td><td>${s.over} of ${s.days}</td></tr>`;
  });
  $('#stations').innerHTML=h+'</tbody>';
}

/* ---------- Feed health ---------- */
function renderHealth(){
  const a=winFrom(),b=winTo(),hs=healthSum(a,b);
  const days=[];for(let i=a;i<=b;i++)if(okDay(i))days.push(i);
  const low=days.filter(i=>1-HEALTH[i].fail/HEALTH[i].polls<.995).length;
  let worst=days[0];days.forEach(i=>{if(HEALTH[i].fail>HEALTH[worst].fail)worst=i});
  const box=$('#health');
  box.innerHTML=`<div class="stats"><div class="stat"><div class="l">Data availability</div><div class="v ${1-hs.fail/hs.polls>=.995?'good':'bad'}">${fmtPct(1-hs.fail/hs.polls,2)}</div></div><div class="stat"><div class="l">Days under 99.5%</div><div class="v">${low}</div></div><div class="stat"><div class="l">Worst day</div><div class="v">${fmtD(worst)}</div></div></div><div class="chartbox" id="hb"></div><div class="legend"><span><i class="sw dash"></i>99.5% target, 7 failed polls a day</span><span>Bars past the top are clipped and labeled</span></div>`;
  const hb=$('#hb'),W=Math.max(260,Math.floor(hb.clientWidth)||300),H=120,m={l:28,r:4,t:12,b:20};
  const iw=W-m.l-m.r,ih=H-m.t-m.b,cap=30,step=iw/days.length,bw=Math.max(1,step*.8);
  const Y=v=>m.t+ih-Math.min(v,cap)/cap*ih;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Failed polls per day">`;
  [0,10,20,30].forEach(v=>{s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--rule)"/><text class="ax" x="${m.l-5}" y="${(Y(v)+4).toFixed(1)}" text-anchor="end">${v}</text>`});
  days.forEach((i,j)=>{
    const f=HEALTH[i].fail,x=m.l+j*step,over=f>cap;
    s+=`<rect x="${x.toFixed(1)}" y="${Y(f).toFixed(1)}" width="${bw.toFixed(1)}" height="${(m.t+ih-Y(f)).toFixed(1)}" fill="${f>7.2?'var(--bad)':'var(--muted)'}" opacity="${f>7.2?1:.55}"><title>${fmtDL(i)}: ${f} failed polls</title></rect>`;
    if(over)s+=`<text class="ax" x="${(x+bw/2).toFixed(1)}" y="${m.t-2}" text-anchor="middle" style="fill:var(--bad)">${f}</text>`;
  });
  s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${Y(7.2).toFixed(1)}" y2="${Y(7.2).toFixed(1)}" stroke="var(--ink)" stroke-dasharray="4 3"/>`;
  hb.innerHTML=s+'</svg>';
}

/* ---------- Orchestration ---------- */
function renderAll(){
  buildCtx();
  const WK=weekly();
  renderControls();renderKPIs();renderChart();renderScore(WK);renderHeat(WK);renderDow();renderStations();renderHealth();
}
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-range],[data-day],[data-dp],[data-line],[data-tab]');
  if(!b)return;
  const d=b.dataset;
  if(d.range)S.range=+d.range;
  if(d.day)S.dayType=d.day;
  if(d.dp)S.dp=d.dp;
  if(d.tab)S.tab=d.tab;
  if(d.line!==undefined){S.line=(S.line===d.line&&d.line!=='all')?'all':d.line}
  renderAll();
});
document.addEventListener('keydown',e=>{
  if((e.key==='Enter'||e.key===' ')&&e.target.matches&&e.target.matches('tr[data-line]')){e.preventDefault();e.target.click()}
});
let lastW=0;
new ResizeObserver(()=>{const w=document.body.clientWidth;if(w===lastW)return;lastW=w;renderAll()}).observe(document.body);
renderAll();
})();
