/* Read-only charts. Every x coordinate uses the same stored intraday domain. */
const actionColors = {BUY:'#15803d', HOLD:'#2563eb', SELL:'#e11d48', ABSTAIN:'#9333ea'};
let visualRun;
async function loadVisualization(id) {
  visualRun = id;
  const section = document.querySelector('#visualization');
  const status = document.querySelector('#visual-status');
  section.hidden = false;
  for (const name of ['decision-overview','symbol-buttons','decision-charts','minute-detail'])
    document.getElementById(name).replaceChildren();
  status.textContent = 'Loading exact historical snapshot…';
  try {
    const response = await fetch(`/api/runs/${id}/visualization`), data = await response.json();
    if (visualRun !== id) return;
    if (!response.ok) throw Error(data.error);
    renderVisualization(data);
    status.textContent = `Run ${data.run_id} · ${data.trading_date} · immutable historical snapshot`;
  } catch (error) {
    if (visualRun === id) status.textContent = `Visualization unavailable: ${error.message}`;
  }
}
function renderVisualization(data) {
  const ns = 'http://www.w3.org/2000/svg', width = 400, left = 65, right = 385;
  const overview = document.querySelector('#decision-overview');
  const charts = document.querySelector('#decision-charts');
  const buttons = document.querySelector('#symbol-buttons');
  const detail = document.querySelector('#minute-detail');
  const symbols = Object.keys(data.symbols);
  let symbol = symbols.includes('AAPL') ? 'AAPL' : symbols[0], pinned = false, minuteIndex = 0;
  const times = [...new Set(Object.values(data.symbols).flat().map(b=>b.timestamp))].sort();
  const start = Date.parse(times[0]), end = Date.parse(times.at(-1));
  const x = t => left + (Date.parse(t)-start)/(end-start || 1)*(right-left);
  const number = v => v !== null && v !== undefined && Number.isFinite(Number(v));
  const show = v => v === null || v === undefined ? 'Unavailable' : String(v);
  function svgNode(tag, attrs={}, text) {
    const node = document.createElementNS(ns, tag);
    for (const [key,value] of Object.entries(attrs)) node.setAttribute(key,value);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function marker(svg, time, value, action, label, select, kind='decision') {
    const px=x(time), py=value;
    let node;
    if (kind==='fill') node=svgNode('circle',{cx:px,cy:py,r:3});
    else if (kind==='forced_close') node=svgNode('rect',{x:px-4,y:py-4,width:8,height:8,fill:'white'});
    else {
      const points = action==='BUY' ? `${px},${py-6} ${px-5},${py+4} ${px+5},${py+4}` :
        action==='SELL' ? `${px},${py+6} ${px-5},${py-4} ${px+5},${py-4}` :
        `${px},${py-5} ${px+5},${py} ${px},${py+5} ${px-5},${py}`;
      node=svgNode('polygon',{points});
    }
    node.setAttribute('stroke',actionColors[action] || '#444');
    if(kind!=='forced_close') node.setAttribute('fill',actionColors[action] || '#444');
    node.setAttribute('tabindex','0'); node.setAttribute('role','button'); node.setAttribute('aria-label',label);
    node.append(svgNode('title',{},label));
    node.addEventListener('click',event=>{event.stopPropagation();select(true)});
    node.addEventListener('focus',()=>select(false));
    node.addEventListener('keydown',event=>{
      if(['Enter',' ','Escape'].includes(event.key)) {
        event.preventDefault();event.stopPropagation();
        if(event.key==='Escape') {pinned=false;inspect(times[minuteIndex]);}
        else select(true);
      }
    });
    svg.append(node);
  }
  function inspect(time, pin=false) {
    minuteIndex = Math.max(0,times.indexOf(time));
    if(pin) pinned=true;
    for(const line of charts.querySelectorAll('.crosshair')) {line.setAttribute('x1',x(time));line.setAttribute('x2',x(time));}
    const decision = data.decisions.find(d=>d.symbol===symbol && d.minute===time);
    const bar = decision ? decision.reference_bar : data.symbols[symbol].filter(b=>b.timestamp<time).at(-1);
    const lines = [`${time} · ${symbol}${pinned?' · pinned':''}`,
      `Decision reference price: ${bar ? '$'+bar.close+' (bar '+bar.timestamp+')' : 'Unavailable'}`];
    if(decision) {
      lines.push(`Decision: ${decision.action}${decision.error?' · '+decision.error:''}`);
      for(const action of Object.keys(actionColors)) lines.push(`${action}: ${show(decision.probabilities?.[action])}`);
      const f=decision.input || {};
      lines.push(`SMA spread: ${number(f.sma20)&&number(f.sma60)&&Number(f.sma60)!==0?(f.sma20-f.sma60)/f.sma60:'Unavailable'}`);
      for(const key of ['momentum_30','relative_volume','volatility_20','trend','position_state','position_quantity','minutes_remaining']) lines.push(`${key}: ${show(f[key])}`);
      for(const fill of decision.fills) lines.push(`Execution/fill: ${fill.timestamp} · ${fill.side} ${fill.quantity} shares · $${fill.price}`);
    } else lines.push('No decision at this minute.');
    for(const fill of data.fills.filter(f=>f.symbol===symbol && f.timestamp===time))
      lines.push(`Fill at selected minute: ${fill.timestamp} · ${fill.side} ${fill.quantity} shares · $${fill.price} · ${fill.reason}`);
    detail.textContent=lines.join('\n');
  }
  function choose(selected,time,pin) {
    if(symbol!==selected) {symbol=selected;draw();}
    inspect(time,pin);
  }
  for(const name of symbols) {
    const button=document.createElement('button');button.type='button';button.textContent=name;
    button.addEventListener('click',()=>{symbol=name;draw();inspect(times[minuteIndex])});buttons.append(button);
    const row=svgNode('svg',{viewBox:'0 0 400 55',role:'group','aria-label':`${name} non-HOLD decisions`});
    row.append(svgNode('text',{x:2,y:24,'font-size':13},name),svgNode('line',{x1:left,x2:right,y1:20,y2:20,stroke:'#ccc'}));
    for(const d of data.decisions.filter(d=>d.symbol===name && d.action!=='HOLD'))
      marker(row,d.minute,20,d.action,`${name} ${d.action} ${d.minute}`,pin=>choose(name,d.minute,pin));
    row.append(svgNode('text',{x:left,y:48,'font-size':12},times[0].slice(11,16)),svgNode('text',{x:right,y:48,'text-anchor':'end','font-size':12},times.at(-1).slice(11,16)));
    overview.append(row);
  }
  function draw() {
    charts.replaceChildren();
    for(const b of buttons.children)b.setAttribute('aria-pressed',String(b.textContent===symbol));
    const decisions=data.decisions.filter(d=>d.symbol===symbol), bars=data.symbols[symbol];
    const fills=data.fills.filter(f=>f.symbol===symbol);
    function chart(title,series,reference=null,fixed=null,price=false,probability=false) {
      const heading=document.createElement('h4');heading.textContent=`${symbol} · ${title}`;
      const legend=document.createElement('p');legend.className='chart-legend';
      const svg=svgNode('svg',{viewBox:'0 0 400 160',tabindex:0,role:'group','aria-label':`${symbol} ${title}; arrow keys inspect minutes`, 'data-domain':`${times[0]}/${times.at(-1)}`});
      const values=series.flatMap(s=>s.points.filter(p=>number(p.value)).map(p=>Number(p.value)));
      if(series.some(s=>s.bars))values.push(0);
      if(reference!==null)values.push(reference);
      if(price) values.push(...fills.map(f=>Number(f.price)));
      let low=fixed?fixed[0]:Math.min(...values), high=fixed?fixed[1]:Math.max(...values);
      if(!Number.isFinite(low)){low=0;high=1;}
      if(!fixed && reference===0){high=Math.max(Math.abs(low),Math.abs(high));low=-high;}
      const y=v=>130-(v-low)/(high-low||1)*110;
      svg.append(svgNode('text',{x:2,y:22,'font-size':12},high.toPrecision(4)),svgNode('text',{x:2,y:130,'font-size':12},low.toPrecision(4)));
      if(reference!==null) svg.append(svgNode('line',{x1:left,x2:right,y1:y(reference),y2:y(reference),stroke:'#999','stroke-dasharray':'3 3'}),svgNode('text',{x:left+3,y:y(reference)-3,'font-size':11},reference===1?'1.0x':'0'));
      series.forEach((s,index)=>{
        const label=document.createElement('span');label.textContent=` ${s.name}`;label.style.color=s.color;legend.append(label);
        let path='',connected=false;
        for(const p of s.points) {
          if(!number(p.value)){connected=false;continue;}
          if(s.bars)svg.append(svgNode('line',{x1:x(p.time),x2:x(p.time),y1:y(0),y2:y(p.value),stroke:s.color,'stroke-width':1}));
          else {path+=`${connected?'L':'M'}${x(p.time)},${y(p.value)} `;connected=true;}
        }
        if(!s.bars)svg.append(svgNode('path',{d:path,fill:'none',stroke:s.color,'stroke-width':2,'stroke-dasharray':probability?['','7 3','3 2','1 3'][index]:'' ,'aria-label':s.name}));
      });
      if(price || probability) for(const d of decisions.filter(d=>d.action!=='HOLD')) {
        const value=price?d.reference_bar?.close:d.probabilities?.[d.action];
        if(number(value))marker(svg,d.minute,y(value),d.action,`${symbol} ${d.action} ${d.minute}`,pin=>inspect(d.minute,pin));
      }
      if(price)for(const f of fills)marker(svg,f.timestamp,y(f.price),f.side.toUpperCase(),`${symbol} ${f.reason} fill ${f.timestamp} $${f.price}`,pin=>inspect(f.timestamp,pin),f.reason==='forced_close'?'forced_close':'fill');
      svg.append(svgNode('line',{class:'crosshair',x1:x(times[minuteIndex]),x2:x(times[minuteIndex]),y1:10,y2:135,stroke:'#555','pointer-events':'none'}));
      for(const index of [0,Math.floor((times.length-1)/2),times.length-1])svg.append(svgNode('text',{x:x(times[index]),y:154,'text-anchor':index===0?'start':index===times.length-1?'end':'middle','font-size':12},times[index].slice(11,16)));
      function pointer(event,pin) {
        const rect=svg.getBoundingClientRect(), pos=(event.clientX-rect.left)/rect.width*width;
        const index=Math.max(0,Math.min(times.length-1,Math.round((pos-left)/(right-left)*(times.length-1))));
        inspect(times[index],pin);
      }
      svg.addEventListener('pointermove',event=>{if(!pinned)pointer(event,false)});
      svg.addEventListener('click',event=>pointer(event,true));
      svg.addEventListener('focus',()=>inspect(times[minuteIndex]));
      svg.addEventListener('keydown',event=>{
        if(event.target!==svg)return;
        if(['ArrowLeft','ArrowRight','Home','End','Enter','Escape'].includes(event.key))event.preventDefault();
        if(event.key==='Escape')pinned=false;
        if(event.key==='ArrowLeft')minuteIndex=Math.max(0,minuteIndex-1);
        if(event.key==='ArrowRight')minuteIndex=Math.min(times.length-1,minuteIndex+1);
        if(event.key==='Home')minuteIndex=0;
        if(event.key==='End')minuteIndex=times.length-1;
        inspect(times[minuteIndex],event.key==='Enter');
      });
      charts.append(heading,legend,svg);
    }
    chart('Historical close (bar timestamp); decisions use the previous bar',[
      {name:'Historical close',color:'#2563eb',points:bars.map(b=>({time:b.timestamp,value:b.close}))}],null,null,true);
    chart('Action probabilities',Object.entries(actionColors).map(([name,color])=>({name,color,points:decisions.map(d=>({time:d.minute,value:d.probabilities?.[name]}))})),null,[0,1],false,true);
    chart('SMA spread (sma20 − sma60) / sma60',[{name:'SMA spread',color:'#0891b2',points:decisions.map(d=>({time:d.minute,value:number(d.input?.sma20)&&number(d.input?.sma60)&&Number(d.input.sma60)!==0?(d.input.sma20-d.input.sma60)/d.input.sma60:null}))}],0);
    for(const [key,title,color,reference] of [['momentum_30','30-minute momentum','#b45309',0],['relative_volume','Relative volume','#db2777',1]])
      chart(title,[{name:title,color,bars:key==='relative_volume',points:decisions.map(d=>({time:d.minute,value:d.input?.[key]}))}],reference);
  }
  document.querySelector('#unpin-minute').onclick=()=>{pinned=false;inspect(times[minuteIndex]);};
  draw();inspect(times[minuteIndex]);
}
