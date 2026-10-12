(function(){
"use strict";
const $=s=>document.querySelector(s);
const range=(a,b)=>Array.from({length:b-a},(_,i)=>a+i);
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
const fmtPct=(v,d)=>(v*100).toFixed(d===undefined?1:d)+'%';
const hr=h=>(h%12===0?12:h%12)+(h<12?'a':'p');
const hrLong=h=>(h%12===0?12:h%12)+(h<12?' AM':' PM');
const runs=hours=>{const hs=[...hours].sort((a,b)=>a-b);const out=[];let cur=[];hs.forEach((h,i)=>{if(i&&h-hs[i-1]>1){out.push(cur);cur=[]}cur.push(h)});if(cur.length)out.push(cur);return out};

/* ---------- Reference data ---------- */
const LINES=[
  {id:'Red', name:'Red',   color:'#c60c30',hw:6, base:26,dly:.022,rn:800},
  {id:'Blue',name:'Blue',  color:'#00a1de',hw:7, base:22,dly:.028,rn:100},
  {id:'Brn', name:'Brown', color:'#62361b',hw:6, base:17,dly:.024,rn:400},
  {id:'G',   name:'Green', color:'#009b3a',hw:9, base:14,dly:.026,rn:0},
  {id:'Org', name:'Orange',color:'#f9461c',hw:9, base:11,dly:.020,rn:700},
  {id:'P',   name:'Purple',color:'#522398',hw:12,base:8, dly:.024,rn:500},
  {id:'Pink',name:'Pink',  color:'#e27ea6',hw:10,base:9, dly:.030,rn:300},
  {id:'Y',   name:'Yellow',color:'#f9e300',hw:15,base:3, dly:.015,rn:900}
];
const COL=id=>LINES.find(l=>l.id===id).color;
const F=[.22,.16,.14,.14,.3,.58,.85,1,1,.85,.7,.68,.7,.7,.74,.86,1,1,.92,.7,.55,.45,.36,.28];
const D=[.6,.5,.5,.5,.7,1,1.5,1.9,1.8,1.3,1,1,1.05,1,1.1,1.4,1.9,2,1.6,1.1,.9,.8,.7,.6];
const PARTS={
  all:{n:'All day',h:range(0,24)},
  am:{n:'AM peak',t:'6–9 AM',h:[6,7,8]},
  mid:{n:'Midday',t:'9 AM–4 PM',h:range(9,16)},
  pm:{n:'PM peak',t:'4–7 PM',h:[16,17,18]},
  eve:{n:'Evening and overnight',t:'7 PM–6 AM',h:range(0,6).concat(range(19,24))}
};
const STA=[
  {n:'Clark/Lake',id:40380,lines:['Blue','Brn','G','Org','P','Pink']},
  {n:'Belmont',id:41320,lines:['Red','Brn','P']},
  {n:'Fullerton',id:41220,lines:['Red','Brn','P']},
  {n:'Howard',id:40900,lines:['Red','P','Y'],term:1},
  {n:'Roosevelt',id:41400,lines:['Red','Org','G']},
  {n:'Jefferson Park',id:41280,lines:['Blue']},
  {n:'Damen',id:40590,lines:['Blue']},
  {n:'Racine',id:40470,lines:['Blue']},
  {n:'O’Hare',id:40890,lines:['Blue'],term:1},
  {n:'Kimball',id:41290,lines:['Brn'],term:1},
  {n:'Midway',id:40930,lines:['Org'],term:1},
  {n:'Halsted',id:41130,lines:['Org']},
  {n:'95th/Dan Ryan',id:40450,lines:['Red'],term:1},
  {n:'Cermak-Chinatown',id:41000,lines:['Red']},
  {n:'Harlem/Lake',id:40020,lines:['G'],term:1},
  {n:'Ashland/63rd',id:40290,lines:['G'],term:1},
  {n:'Cicero',id:40480,lines:['G']},
  {n:'Pulaski',id:40150,lines:['Pink']},
  {n:'Linden',id:41050,lines:['P'],term:1},
  {n:'Dempster-Skokie',id:40140,lines:['Y'],term:1}
];
// One entry per line at each station, so a delayed line isn't bundled with quieter ones
const SL=(function(){const r=mulberry32(55);return STA.flatMap(s=>s.lines.map(L=>({n:s.n,id:s.id,L,f1:.6+r()*1.1,f2:.85+r()*.35})))})();

/* ---------- Sample data generation (hourly, per line) ---------- */
function build(seed,incidents,scale){
  const r=mulberry32(seed);
  return LINES.map(L=>{
    const hrs=range(0,24).map(h=>{
      const trains=Math.max(1,Math.round(L.base*F[h]*(1+(r()-.5)*.12)));
      let dl=L.dly*scale*D[h]*(1+(r()-.5)*.5);
      if(incidents){
        if(L.id==='Blue'&&(h===17||h===18)) dl*=2.6;
        if(L.id==='Red'&&h===8) dl*=2;
        if(L.id==='Pink'&&h===7) dl*=1.8;
      }
      dl=Math.min(.2,dl);
      const heff=Math.min(30,L.hw/Math.max(F[h],.12));
      const sched=heff;
      const head=sched*(1+5*dl)*(1+(r()-.5)*.08);
      const adh=Math.max(.55,Math.min(.99,.975-dl*2.4-r()*.02));
      const sch=Math.min(.5,.05+(1-F[h])*.22+(r()-.5)*.02);
      return {trains,dl,head,sched,adh,sch};
    });
    return {L,hrs};
  });
}
const DATA=build(1,true,1);
const PRIOR=build(2,false,.95);
const HEALTH=(function(){const r=mulberry32(9);return range(0,24).map(h=>{
  let f900=r()<.18?1:0; if(h===17)f900=5; if(h===18)f900=2;
  const f102=h===22?2:h===23?5:0;
  return {polls:60,f900,f102,age:Math.round(38+r()*10+(h===17?26:0))};
})})();

const S={part:'all',line:'all',tab:'dl'};
const selData=()=>S.line==='all'?DATA:DATA.filter(d=>d.L.id===S.line);
const selPrior=()=>S.line==='all'?PRIOR:PRIOR.filter(d=>d.L.id===S.line);

function agg(data,hours){
  let T=0,dl=0,w=0,sc=0,ad=0,sh=0;
  for(const d of data)for(const h of hours){const x=d.hrs[h];T+=x.trains;dl+=x.dl*x.trains;w+=x.head*x.trains;sc+=x.sched*x.trains;ad+=x.adh*x.trains;sh+=x.sch*x.trains}
  return {trains:T/hours.length,dl:dl/T,head:w/T,sched:sc/T,adh:ad/T,live:1-sh/T};
}
function pollStats(hours){
  let polls=0,fail=0,f900=0,f102=0;
  hours.forEach(h=>{const x=HEALTH[h];polls+=x.polls;f900+=x.f900;f102+=x.f102});
  fail=f900+f102;
  return {polls,fail,f900,f102,ok:1-fail/polls};
}

/* ---------- Map geometry ---------- */
const proj=p=>[(p[1]+87.92)*1068+8,(42.09-p[0])*1436];
const PATHS={
  Red:[[[42.0190,-87.6728],[42.0013,-87.6608],[41.9645,-87.6579],[41.9398,-87.6534],[41.9253,-87.6526],[41.9106,-87.6493],[41.8968,-87.6280],[41.8848,-87.6278],[41.8674,-87.6270],[41.8311,-87.6307],[41.7803,-87.6306],[41.7223,-87.6249]]],
  Blue:[[[41.8743,-87.8172],[41.8708,-87.7761],[41.8710,-87.7451],[41.8734,-87.7256],[41.8756,-87.6875],[41.8760,-87.6569],[41.8757,-87.6408],[41.8783,-87.6294],[41.8857,-87.6314],[41.8912,-87.6477],[41.9098,-87.6777],[41.9295,-87.7079],[41.9470,-87.7186],[41.9702,-87.7602],[41.9868,-87.8085],[41.9836,-87.8592],[41.9786,-87.9043]]],
  Brn:[[[41.9679,-87.7135],[41.9540,-87.6748],[41.9437,-87.6636],[41.9398,-87.6534],[41.9253,-87.6526],[41.9182,-87.6438],[41.9104,-87.6386],[41.8968,-87.6353],[41.8858,-87.6337]]],
  G:[[[41.8867,-87.8032],[41.8874,-87.7770],[41.8871,-87.7645],[41.8853,-87.7261],[41.8845,-87.7061],[41.8853,-87.6666],[41.8858,-87.6415],[41.8858,-87.6337],[41.8858,-87.6260],[41.8767,-87.6260],[41.8674,-87.6270],[41.8531,-87.6266],[41.8317,-87.6259],[41.7954,-87.6184],[41.7804,-87.6057]],
     [[41.7954,-87.6184],[41.7801,-87.6300],[41.7789,-87.6637]]],
  Org:[[[41.7866,-87.7377],[41.7995,-87.7246],[41.8046,-87.7047],[41.8047,-87.6846],[41.8290,-87.6810],[41.8393,-87.6663],[41.8467,-87.6484],[41.8674,-87.6270],[41.8767,-87.6260]]],
  P:[[[42.0733,-87.6907],[42.0567,-87.6837],[42.0190,-87.6728]]],
  Pink:[[[41.8517,-87.7568],[41.8537,-87.7047],[41.8542,-87.6759],[41.8577,-87.6693],[41.8715,-87.6670],[41.8853,-87.6666],[41.8858,-87.6415],[41.8858,-87.6337]]],
  Y:[[[42.0384,-87.7517],[42.0265,-87.7418],[42.0190,-87.6728]]]
};
const PX={};Object.keys(PATHS).forEach(k=>PX[k]=PATHS[k].map(poly=>poly.map(proj)));
const LOOP=[[41.8767,-87.6339],[41.8858,-87.6337],[41.8858,-87.6260],[41.8767,-87.6260]].map(proj);
const WATER=[[42.09,-87.67],[42.0733,-87.669],[42.019,-87.652],[41.98,-87.64],[41.95,-87.628],[41.93,-87.625],[41.9,-87.611],[41.89,-87.606],[41.865,-87.612],[41.84,-87.608],[41.81,-87.58],[41.77,-87.575],[41.73,-87.55],[41.70,-87.54],[41.70,-87.45],[42.09,-87.45]].map(proj);
const PLACES=[
  ['O’Hare',41.9786,-87.9043,10,-8,'start'],
  ['Forest Park',41.8743,-87.8172,0,16,'middle'],
  ['Harlem/Lake',41.8867,-87.8032,0,-9,'middle'],
  ['Midway',41.7866,-87.7377,0,16,'middle'],
  ['Kimball',41.9679,-87.7135,0,-9,'middle'],
  ['Linden',42.0733,-87.6907,9,4,'start'],
  ['Skokie',42.0384,-87.7517,-8,4,'end'],
  ['Howard',42.0190,-87.6728,9,4,'start'],
  ['Loop',41.8812,-87.6299,12,-3,'start'],
  ['95th/Dan Ryan',41.7223,-87.6249,-8,4,'end'],
  ['Cottage Grove',41.7804,-87.6057,10,16,'end'],
  ['Ashland/63rd',41.7789,-87.6637,4,-7,'end']
];
function along(poly,t){
  const seg=[];let L=0;
  for(let i=1;i<poly.length;i++){const d=Math.hypot(poly[i][0]-poly[i-1][0],poly[i][1]-poly[i-1][1]);seg.push(d);L+=d}
  let tg=t*L;
  for(let i=0;i<seg.length;i++){
    if(tg<=seg[i]){const u=seg[i]?tg/seg[i]:0;return [poly[i][0]+(poly[i+1][0]-poly[i][0])*u,poly[i][1]+(poly[i+1][1]-poly[i][1])*u]}
    tg-=seg[i];
  }
  return poly[poly.length-1];
}
const SNAP=[];
LINES.forEach((L,li)=>{
  const r=mulberry32(100+li);
  const n=Math.round(L.base*F[17]);
  const rate=DATA[li].hrs[17].dl;
  const nd=Math.round(n*rate);
  const dl=new Set();
  while(dl.size<Math.min(nd,n)){dl.add(Math.floor(r()*n))}
  for(let i=0;i<n;i++){
    const t=Math.min(.99,Math.max(.01,(i+.15+r()*.7)/n));
    const p=along(PX[L.id][0],t);
    SNAP.push({L,x:p[0],y:p[1],delayed:dl.has(i),run:L.rn+10+i});
  }
});

/* ---------- Controls ---------- */
function renderControls(){
  $('#parts').innerHTML=Object.entries(PARTS).map(([k,p])=>`<button type="button" data-part="${k}"${p.t?` title="${p.t}"`:''} aria-pressed="${S.part===k}">${p.n}</button>`).join('');
  $('#lines').innerHTML=`<button type="button" data-line="all" aria-pressed="${S.line==='all'}">All lines</button>`+
    LINES.map(L=>`<button type="button" data-line="${L.id}" aria-pressed="${S.line===L.id}"><i class="dot" style="background:${L.color}"></i>${L.name}</button>`).join('');
  document.querySelectorAll('#tabs button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===S.tab)));
}

/* ---------- KPI strip ---------- */
function sparkSvg(vals){
  const mn=Math.min(...vals),mx=Math.max(...vals),sp=(mx-mn)||1;
  const pt=h=>`${(h/23*94+1).toFixed(1)},${(25-(vals[h]-mn)/sp*22).toFixed(1)}`;
  let s=`<svg class="spark" viewBox="0 0 96 28" preserveAspectRatio="none" aria-hidden="true"><polyline fill="none" stroke="var(--muted)" opacity=".45" stroke-width="1.5" vector-effect="non-scaling-stroke" points="${range(0,24).map(pt).join(' ')}"/>`;
  runs(PARTS[S.part].h).forEach(r=>{if(r.length>1)s+=`<polyline fill="none" stroke="var(--ink)" stroke-width="2" vector-effect="non-scaling-stroke" points="${r.map(pt).join(' ')}"/>`});
  return s+'</svg>';
}
function renderKPIs(){
  const hours=PARTS[S.part].h,data=selData(),prior=selPrior();
  const a=agg(data,hours),b=agg(prior,hours),ps=pollStats(hours);
  const sp=fn=>sparkSvg(range(0,24).map(h=>fn(agg(data,[h]))));
  const pct=d=>(d>=0?'+':'-')+Math.abs(d*100).toFixed(1)+'%';
  const K=[
    {l:'Trains in service',v:a.trains.toFixed(0),d:a.trains-b.trains,df:d=>(d>=0?'+':'-')+Math.abs(d).toFixed(0),hi:null,eps:.5,sp:sp(x=>x.trains)},
    {l:'Delay rate',v:fmtPct(a.dl,1),d:a.dl-b.dl,df:pct,hi:false,eps:.0005,sp:sp(x=>x.dl)},
    {l:'Headway',v:a.head.toFixed(1)+' min',d:a.head-b.head,df:d=>(d>=0?'+':'-')+Math.abs(d).toFixed(1)+' min',hi:false,eps:.05,sp:sp(x=>x.head)}
  ];
  let html=K.map(k=>{
    let cls='';
    if(k.hi!==null&&Math.abs(k.d)>=k.eps)cls=((k.d>0)===k.hi)?'good':'bad';
    const arrow=k.d>=0?'▲':'▼';
    return `<div class="kpi"><div class="l">${k.l}</div><div class="v">${k.v}</div><div class="d ${cls}">${arrow} ${k.df(k.d)} vs last week</div>${k.sp}</div>`;
  }).join('');
  const okCls=ps.ok>=.995?'good':'bad';
  const okSp=sparkSvg(range(0,24).map(h=>1-(HEALTH[h].f900+HEALTH[h].f102)/60));
  html+=`<div class="kpi"><div class="l">Data availability</div><div class="v">${fmtPct(ps.ok,1)}</div><div class="d ${okCls}">${ps.ok>=.995?'Meets':'Below'} 99.5% target</div>${okSp}</div>`;
  $('#kpis').innerHTML=html;
}

/* ---------- Map ---------- */
function renderMap(){
  let s=`<svg viewBox="0 0 380 560" role="img" aria-label="Map of trains in service across the CTA rail network">`;
  s+=`<polygon points="${WATER.map(p=>p.join(',')).join(' ')}" fill="var(--water)"/>`;
  s+=`<text x="374" y="196" text-anchor="end" font-size="11" font-style="italic" fill="var(--waterInk)" style="font-family:var(--ui)">Lake Michigan</text>`;
  s+=`<polygon points="${LOOP.map(p=>p.join(',')).join(' ')}" fill="none" stroke="var(--muted)" stroke-width="1.5" opacity=".5"/>`;
  const order=LINES.filter(l=>l.id!==S.line).concat(LINES.filter(l=>l.id===S.line));
  order.forEach(L=>{
    const dim=S.line!=='all'&&S.line!==L.id?.18:1;
    PX[L.id].forEach(poly=>{s+=`<polyline points="${poly.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ')}" fill="none" stroke="${L.color}" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round" opacity="${dim}"/>`});
  });
  PLACES.forEach(p=>{const [x,y]=proj([p[1],p[2]]);s+=`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.6" fill="var(--surface)" stroke="var(--ink)" stroke-width="1.2"/>`});
  SNAP.forEach(t=>{
    const on=S.line==='all'||S.line===t.L.id;
    const op=on?1:.2;
    const tip=`<title>${t.L.name} Line, run ${t.run}${t.delayed?', flagged delayed':''}</title>`;
    if(t.delayed)s+=`<g opacity="${op}">${tip}<circle cx="${t.x.toFixed(1)}" cy="${t.y.toFixed(1)}" r="9" fill="none" stroke="var(--bad)" stroke-width="1.5" opacity=".6"/><circle cx="${t.x.toFixed(1)}" cy="${t.y.toFixed(1)}" r="4.6" fill="${t.L.color}" stroke="var(--surface)" stroke-width="1.5"/></g>`;
    else s+=`<g opacity="${op}">${tip}<circle cx="${t.x.toFixed(1)}" cy="${t.y.toFixed(1)}" r="4" fill="${t.L.color}" stroke="var(--surface)" stroke-width="1.5"/></g>`;
  });
  // Labels go over the trains so a train dot never hides a station name
  PLACES.forEach(p=>{const [x,y]=proj([p[1],p[2]]);s+=`<text class="lbl" x="${(x+p[3]).toFixed(1)}" y="${(y+p[4]).toFixed(1)}" text-anchor="${p[5]}">${p[0]}</text>`});
  s+='</svg>';
  $('#map').innerHTML=s;
}

/* ---------- Scorecard ---------- */
function renderScore(){
  const hours=PARTS[S.part].h;
  const rows=DATA.map(d=>({L:d.L,...agg([d],hours)}));
  const tot=agg(DATA,hours);
  let h=`<thead><tr><th>Line</th><th>Trains</th><th>Delayed</th><th>Headway</th></tr></thead><tbody>`;
  rows.forEach(r=>{
    h+=`<tr data-line="${r.L.id}" tabindex="0" class="${S.line===r.L.id?'sel':''}" aria-selected="${S.line===r.L.id}"><td><i class="dot" style="background:${r.L.color}"></i>${r.L.name}</td><td>${r.trains.toFixed(0)}</td><td>${fmtPct(r.dl,1)}<span class="mini"><b style="width:${Math.min(100,r.dl/.06*100).toFixed(0)}%"></b></span></td><td>${r.head.toFixed(1)} min</td></tr>`;
  });
  h+=`<tr class="total"><td>Network</td><td>${tot.trains.toFixed(0)}</td><td>${fmtPct(tot.dl,1)}</td><td>${tot.head.toFixed(1)} min</td></tr></tbody>`;
  $('#score').innerHTML=h;
}

/* ---------- Hourly chart ---------- */
function nice(v){const raw=v/4;const mag=Math.pow(10,Math.floor(Math.log10(raw)));const n=raw/mag;const s=(n<=1?1:n<=2?2:n<=5?5:10)*mag;return {step:s,max:Math.ceil(v/s)*s}}
function renderChart(){
  const box=$('#chart');
  const W=Math.max(280,Math.floor(box.clientWidth)||320),H=250,m={l:42,r:12,t:16,b:26};
  const iw=W-m.l-m.r,ih=H-m.t-m.b,step=iw/23,X=h=>m.l+h*step;
  const data=selData(),prior=selPrior(),hours=PARTS[S.part].h;
  const T=S.tab;
  const lineCol=S.line==='all'?'var(--ink)':COL(S.line);
  let cur,prev=null,fmt,stack=null;
  if(T==='trains'){
    stack=range(0,24).map(h=>data.map(d=>d.hrs[h].trains));
    cur=stack.map(a=>a.reduce((x,y)=>x+y,0));
    fmt=v=>Math.round(v)+' trains';
  }else{
    const k=T==='dl'?'dl':'head';
    cur=range(0,24).map(h=>agg(data,[h])[k]);
    prev=range(0,24).map(h=>agg(prior,[h])[k]);
    fmt=T==='dl'?v=>fmtPct(v,1):v=>v.toFixed(1)+' min';
  }
  const maxV=Math.max(...cur,...(prev||[0]));
  const nz=nice(maxV*1.05),max=nz.max;
  const tick=T==='dl'?v=>(v*100).toFixed(nz.step*100<1?1:0)+'%':T==='head'?v=>v.toFixed(nz.step<1?1:0):v=>String(Math.round(v));
  const Y=v=>m.t+ih-(v/max)*ih;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Hourly chart">`;
  if(S.part!=='all'&&!stack){
    runs(hours).forEach(r=>{const x0=Math.max(m.l,X(r[0])-step/2),x1=Math.min(m.l+iw,X(r[r.length-1])+step/2);s+=`<rect x="${x0.toFixed(1)}" y="${m.t}" width="${(x1-x0).toFixed(1)}" height="${ih}" fill="var(--band)"/>`});
  }
  const nt=Math.round(max/nz.step);
  for(let i=0;i<=nt;i++){const v=i*nz.step,y=Y(v);s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--rule)" stroke-width="1"/><text class="ax" x="${m.l-6}" y="${(y+4).toFixed(1)}" text-anchor="end">${tick(v)}</text>`}
  for(let h=0;h<24;h+=3)s+=`<text class="ax" x="${X(h).toFixed(1)}" y="${H-8}" text-anchor="middle">${hr(h)}</text>`;
  if(stack){
    const bw=Math.max(4,step*.72),inP=new Set(hours);
    for(let h=0;h<24;h++){
      let y=m.t+ih;
      data.forEach((d,i)=>{const bh=stack[h][i]/max*ih;y-=bh;s+=`<rect x="${(X(h)-bw/2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0,bh-.6).toFixed(1)}" fill="${d.L.color}" opacity="${S.part==='all'||inP.has(h)?.95:.3}"/>`});
    }
  }else{
    const path=arr=>arr.map((v,h)=>(h?'L':'M')+X(h).toFixed(1)+' '+Y(v).toFixed(1)).join(' ');
    s+=`<path d="${path(prev)}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 3"/>`;
    s+=`<path d="${path(cur)}" fill="none" stroke="${lineCol}" stroke-width="2.6" stroke-linejoin="round"/>`;
    let pi=0;cur.forEach((v,h)=>{if(v>cur[pi])pi=h});
    const px=X(pi),py=Y(cur[pi]);
    s+=`<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="3.8" fill="${lineCol}" stroke="var(--surface)" stroke-width="1.5"/>`;
    const tx=Math.min(W-m.r-24,Math.max(m.l+24,px));
    s+=`<text class="ax2" x="${tx.toFixed(1)}" y="${(py-9<10?py+18:py-9).toFixed(1)}" text-anchor="middle" style="font-weight:600">${fmt(cur[pi])}</text>`;
  }
  s+=`<line id="hv" y1="${m.t}" y2="${m.t+ih}" stroke="var(--muted)" stroke-dasharray="2 3" style="display:none"/></svg><div class="tip" id="tip"></div>`;
  box.innerHTML=s;
  const svg=box.querySelector('svg'),tip=$('#tip'),hv=$('#hv');
  const show=e=>{
    const r=svg.getBoundingClientRect();
    let h=Math.round(((e.clientX-r.left)*(W/r.width)-m.l)/step);h=Math.max(0,Math.min(23,h));
    hv.setAttribute('x1',X(h));hv.setAttribute('x2',X(h));hv.style.display='block';
    tip.innerHTML=`<b>${hrLong(h)}</b><br>${fmt(cur[h])}`+(prev?`<br><span style="opacity:.75">Last week ${fmt(prev[h])}</span>`:'');
    tip.style.display='block';
    const tw=tip.offsetWidth;tip.style.left=Math.min(W-tw,Math.max(0,X(h)+10))+'px';
  };
  svg.addEventListener('pointermove',show);svg.addEventListener('pointerdown',show);
  svg.addEventListener('pointerleave',()=>{tip.style.display='none';hv.style.display='none'});
  $('#legend').innerHTML=stack
    ?(S.line==='all'?LINES.map(L=>`<span><i class="dot" style="background:${L.color}"></i>${L.name}</span>`).join(''):`<span><i class="dot" style="background:${COL(S.line)}"></i>${LINES.find(l=>l.id===S.line).name} Line</span>`)
    :`<span><i class="sw" style="border-top-color:${lineCol}"></i>Today</span><span><i class="sw dash"></i>Same weekday last week</span>`;
}

/* ---------- Heatmap ---------- */
function renderHeat(){
  const box=$('#heat');
  const W=Math.max(280,Math.floor(box.clientWidth)||320),lw=58,top=20,rh=22,gap=2;
  const cw=(W-lw)/24,H=top+LINES.length*(rh+gap)+2;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Heatmap of delay rate by line and hour">`;
  for(let h=0;h<24;h+=6)s+=`<text class="ax" x="${(lw+h*cw).toFixed(1)}" y="11">${hr(h)}</text>`;
  s+=`<text class="ax" x="${W}" y="11" text-anchor="end">11p</text>`;
  if(S.part!=='all')runs(PARTS[S.part].h).forEach(r=>{s+=`<rect x="${(lw+r[0]*cw).toFixed(1)}" y="15" width="${(r.length*cw-1.5).toFixed(1)}" height="2.5" fill="var(--ink)"/>`});
  DATA.forEach((d,i)=>{
    const y=top+i*(rh+gap),sel=S.line===d.L.id;
    s+=`<g data-line="${d.L.id}" style="cursor:pointer"><rect x="0" y="${y}" width="${lw-2}" height="${rh}" fill="transparent"/><circle cx="6" cy="${y+rh/2}" r="4.5" fill="${d.L.color}"/><text class="ax2" x="16" y="${y+rh/2+4.5}" style="${sel?'font-weight:600':''}">${d.L.name}</text>`;
    d.hrs.forEach((x,h)=>{
      const a=Math.pow(Math.min(1,x.dl/.10),.8);
      s+=`<rect x="${(lw+h*cw).toFixed(1)}" y="${y}" width="${(cw-1.5).toFixed(1)}" height="${rh}" rx="2" fill="var(--soft)"/><rect x="${(lw+h*cw).toFixed(1)}" y="${y}" width="${(cw-1.5).toFixed(1)}" height="${rh}" rx="2" fill="#b3261e" fill-opacity="${a.toFixed(2)}" data-h="${h}"/>`;
    });
    if(sel)s+=`<rect x="${lw-1}" y="${y-1}" width="${(24*cw).toFixed(1)}" height="${rh+2}" rx="3" fill="none" stroke="var(--ink)" stroke-width="1.5"/>`;
    s+='</g>';
  });
  s+='</svg><div class="tip" id="heattip"></div>';
  box.innerHTML=s;
  const svg=box.querySelector('svg'),tip=$('#heattip');
  const hide=()=>{tip.style.display='none'};
  const show=e=>{
    const c=e.target.closest('[data-h]');
    if(!c)return hide();
    const h=+c.dataset.h,d=DATA.find(d=>d.L.id===c.parentNode.dataset.line);
    tip.innerHTML=`<b>${d.L.name} Line, ${hrLong(h)}</b><br>${fmtPct(d.hrs[h].dl,1)}`;
    tip.style.display='block';
    const r=svg.getBoundingClientRect(),k=r.width/W,y=+c.getAttribute('y');
    const tw=tip.offsetWidth,th=tip.offsetHeight;
    tip.style.left=Math.min(r.width-tw,Math.max(0,(lw+(h+1)*cw)*k+6))+'px';
    tip.style.top=Math.max(0,(y+rh/2)*k-th/2)+'px';
  };
  svg.addEventListener('pointermove',show);svg.addEventListener('pointerdown',show);
  svg.addEventListener('pointerleave',hide);
}

/* ---------- Station watchlist ---------- */
function renderStations(){
  const hours=PARTS[S.part].h;
  const rows=SL.filter(s=>S.line==='all'||s.L===S.line).map(s=>{
    const a=agg(DATA.filter(d=>d.L.id===s.L),hours);
    return {...s,dl:a.dl*s.f1,head:a.head*s.f2};
  }).sort((x,y)=>y.dl-x.dl).slice(0,8);
  let h=`<thead><tr><th>Line/station</th><th>Delayed</th><th>Headway</th></tr></thead><tbody>`;
  rows.forEach(s=>{
    h+=`<tr><td><div class="st"><i class="dot sm" style="background:${COL(s.L)}"></i>${s.n}</div></td><td>${fmtPct(s.dl,1)}</td><td>${s.head.toFixed(1)} min</td></tr>`;
  });
  $('#stations').innerHTML=h+'</tbody>';
}

/* ---------- Feed health ---------- */
function renderHealth(){
  const hours=PARTS[S.part].h,ps=pollStats(hours);
  const box=$('#health');
  box.innerHTML=`<div class="stats" style="grid-template-columns:1fr"><div class="stat"><div class="l">Data availability</div><div class="v ${ps.ok>=.995?'good':'bad'}">${fmtPct(ps.ok,2)}</div></div></div><div class="chartbox" id="hbars"></div>
  <div class="scroll"><table><thead><tr><th>Error Code</th><th style="text-align:left">Error Code Description</th><th>Count</th></tr></thead><tbody>
  <tr><td>0</td><td style="text-align:left">OK</td><td>${ps.polls-ps.fail}</td></tr>
  <tr><td>900</td><td style="text-align:left">Server error</td><td>${ps.f900}</td></tr>
  <tr><td>102</td><td style="text-align:left">Daily usage limit exceeded</td><td>${ps.f102}</td></tr></tbody></table></div>`;
  const hb=$('#hbars');
  const W=Math.max(260,Math.floor(hb.clientWidth)||300),H=110,m={l:26,r:4,t:8,b:22};
  const iw=W-m.l-m.r,ih=H-m.t-m.b,step=iw/24,bw=Math.max(3,step*.66);
  const tot=HEALTH.map(x=>x.f900+x.f102),mxF=Math.max(...tot,1),inP=new Set(hours);
  let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Failed polls per hour">`;
  s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${m.t+ih}" y2="${m.t+ih}" stroke="var(--rule)"/><text class="ax" x="${m.l-5}" y="${m.t+ih+4}" text-anchor="end">0</text><text class="ax" x="${m.l-5}" y="${m.t+9}" text-anchor="end">${mxF}</text>`;
  HEALTH.forEach((x,h)=>{
    const op=S.part==='all'||inP.has(h)?1:.3,cx=m.l+h*step+(step-bw)/2;
    const h1=x.f900/mxF*ih,h2=x.f102/mxF*ih;
    s+=`<rect x="${cx.toFixed(1)}" y="${(m.t+ih-h1).toFixed(1)}" width="${bw.toFixed(1)}" height="${h1.toFixed(1)}" fill="var(--bad)" opacity="${op}"><title>${hrLong(h)}: ${x.f900} server errors</title></rect>`;
    s+=`<rect x="${cx.toFixed(1)}" y="${(m.t+ih-h1-h2).toFixed(1)}" width="${bw.toFixed(1)}" height="${h2.toFixed(1)}" fill="var(--warn)" opacity="${op}"><title>${hrLong(h)}: ${x.f102} usage-limit errors</title></rect>`;
    if(h%6===0)s+=`<text class="ax" x="${(m.l+h*step+step/2).toFixed(1)}" y="${H-6}" text-anchor="middle">${hr(h)}</text>`;
  });
  s+='</svg>';
  hb.innerHTML=s+`<div class="legend"><span><i class="dot" style="background:var(--bad)"></i>Server error (900)</span><span><i class="dot" style="background:var(--warn)"></i>Usage limit (102)</span></div>`;
}

/* ---------- Orchestration ---------- */
function renderAll(){renderControls();renderKPIs();renderMap();renderScore();renderChart();renderHeat();renderStations();renderHealth()}
document.addEventListener('click',e=>{
  const b=e.target.closest('[data-part],[data-line],[data-tab]');
  if(!b)return;
  if(b.dataset.part)S.part=b.dataset.part;
  if(b.dataset.tab)S.tab=b.dataset.tab;
  if(b.dataset.line!==undefined){const v=b.dataset.line;S.line=(S.line===v&&v!=='all')?'all':v}
  renderAll();
});
document.addEventListener('keydown',e=>{
  if((e.key==='Enter'||e.key===' ')&&e.target.matches&&e.target.matches('tr[data-line]')){e.preventDefault();e.target.click()}
});
let lastW=0;
const ro=new ResizeObserver(()=>{const w=document.body.clientWidth;if(w===lastW)return;lastW=w;renderChart();renderHeat();renderHealth()});
ro.observe(document.body);
renderAll();
})();
