// CPCB AQI categories: [upper bound, label, colour]
const CATS = [[50,'Good','#3aa655'],[100,'Satisfactory','#8fc43f'],[200,'Moderate','#f2c230'],
              [300,'Poor','#f08a24'],[400,'Very Poor','#e0443e'],[500,'Severe','#9b1c31']];
const cat = v => CATS.find(c => v <= c[0]) || CATS[5];
const $ = id => document.getElementById(id);

// Sample data. The real API should return this exact shape (see /api/overview/ contract).
const SAMPLE = {
  user:{name:'Maya Patel',persona:'Asthma-aware',sensitivity:'High'},
  place:'Delhi', updated:'Updated at 9:41 AM IST',
  weather:{temp:28,desc:'Partly cloudy',feels:30,hi:31,lo:23,wind:12,humidity:68,uv:'6 · High'},
  aqi:{value:88,source:'Live sensor',pm25:34,pm10:61,o3:32,no2:12,note:'A brief rise to 112 is predicted around 3 PM.'},
  hourly:[['Now',28,88,5],['10 AM',29,92,5],['11 AM',30,98,0],['12 PM',31,104,0],['1 PM',31,110,0],['2 PM',31,112,5],['3 PM',30,112,10],['4 PM',29,104,5]],
  week:[['Today',23,31,5],['Wed',23,32,0],['Thu',22,30,40],['Fri',22,29,65],['Sat',22,28,70],['Sun',23,30,30],['Mon',23,31,10]],
  curve:[88,92,104,112,108,96,84,78,76,80,86,88],
  sun:{rise:'6:04 AM',set:'6:52 PM'},rain:'0.0 mm today',
  outside:{window:'5–7 PM',text:'Cooler skies and easing particles line up for your evening walk.',aqi:78}
};

async function load(){
  const {lat, lon, place} = Aero.loc();
  try{
    const r = await fetch($('overview').dataset.api + '?' + new URLSearchParams({lat, lon, place}), {headers:{Accept:'application/json'}});
    if(r.status === 400){ const j = await r.json().catch(()=>({})); return {error: j.error || 'This location is not supported'}; }
    if(!r.ok) throw 0; return await r.json();
  }catch(e){ return {...SAMPLE, demo:true}; }          // server unreachable: fall back so the page always renders
}

function render(d){
  if(d.error){ $('weather').innerHTML = `<h3>Can't show this place</h3><p class="muted" style="margin-top:8px">${Aero.esc(d.error)}</p>`;
    for(const id of ['air','personal','hourly','week','chart','outside']) $(id).innerHTML = ''; return; }
  const c = cat(d.aqi.value), first = d.user.name.split(' ')[0];
  $('username').textContent = d.user.name; $('avatar').textContent = first[0];
  $('greeting').textContent = `A brighter day starts here, ${first}.`;
  $('stamp').innerHTML = `${new Date().toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}<br>${d.updated}${d.demo?'<br><b style="color:#e07a2f">Sample data: API not reachable</b>':''}`;

  $('weather').innerHTML = `
    <div class="muted">📍 ${Aero.esc(d.place)}</div>
    <div class="row"><div><div class="big">${d.weather.temp}°</div>
      <p><b>${d.weather.desc}</b></p><p class="muted">Feels like ${d.weather.feels}° · H ${d.weather.hi}° L ${d.weather.lo}°</p></div>
      <div style="font-size:84px">⛅</div></div>
    <div class="stats"><span>Wind<b>${d.weather.wind} km/h</b></span><span>Humidity<b>${d.weather.humidity}%</b></span><span>UV index<b>${d.weather.uv}</b></span></div>`;

  const pos = Math.min(d.aqi.value/500*100,100);
  $('air').innerHTML = `
    <h3>Take a good breath.</h3>
    <div class="big" style="color:${c[2]};margin-top:8px">${d.aqi.value}</div>
    <span class="pill" style="color:${c[2]}">${c[1]} · CPCB AQI</span> <span class="pill">${d.aqi.source}</span>
    <div class="gauge-wrap"><div class="gauge">${CATS.map(x=>`<i style="background:${x[2]}"></i>`).join('')}</div><div class="gauge-dot" style="left:${pos}%"></div></div>
    <div class="row muted"><span>0 Good</span><span>500 Severe</span></div>
    <p style="margin:10px 0;font-size:13px">${d.aqi.note}</p><b style="font-size:13px">PM2.5 · ${d.aqi.pm25} µg/m³</b>`;

  $('personal').innerHTML = `
    <div class="muted" style="font-weight:600">MADE FOR ${first.toUpperCase()}</div>
    <h2 style="margin:8px 0">${c[0]<=100?'Fresh air.':'Take it easy.'}<br>On your terms.</h2>
    <p style="font-size:13px">${c[0]<=100?'Conditions look comfortable for most outdoor plans.':'Limit long outdoor activity while particles are elevated.'}</p>
    <div class="chips"><span class="pill">${d.user.persona}</span></div>
    <p class="muted" style="margin-top:14px">Your alert sensitivity <b style="float:right;color:#e07a2f">${d.user.sensitivity}</b></p>`;

  $('hourly').innerHTML = `<div class="row"><h3>Your next 24 hours</h3><a class="btn" style="margin:0" href="/prediction/">Full prediction ↗</a></div>
    <div class="hours">${d.hourly.map((h,i)=>{const k=cat(h[2]);return `
      <div class="hour ${i?'':'now'}"><span class="muted">${h[0]}</span><b>${h[1]}°</b><span class="muted">💧${h[3]}%</span><br>
      <span class="tag" style="background:${k[2]}">AQI ${h[2]}</span></div>`}).join('')}</div>
    <div class="row muted"><span>🌅 Sunrise <b>${d.sun.rise}</b></span><span>🌇 Sunset <b>${d.sun.set}</b></span><span>☔ ${d.rain}</span></div>`;

  const lo = Math.min(...d.week.map(w=>w[1])), hi = Math.max(...d.week.map(w=>w[2])), span = hi-lo||1;
  $('week').innerHTML = `<div class="row"><h3>The week ahead</h3><span class="muted">7 days</span></div>` +
    d.week.map(w=>`<div class="week-row"><b>${w[0]}</b><span class="muted">${w[3]}%</span><span class="muted">${w[1]}°</span>
      <div class="bar"><i style="left:${(w[1]-lo)/span*100}%;right:${100-(w[2]-lo)/span*100}%"></i></div><b>${w[2]}°</b></div>`).join('');

  const pts = d.curve, max = Math.max(...pts,150), W = 600, H = 120;
  const xy = pts.map((v,i)=>`${i*W/(pts.length-1)},${H-v/max*H}`).join(' ');
  $('chart').innerHTML = `<div class="row"><h3>A clearer picture of your air</h3><span class="muted">CPCB AQI · Today</span></div>
    <svg class="curve" viewBox="0 0 ${W} ${H+8}" preserveAspectRatio="none">
      <polyline points="${xy}" fill="none" stroke="#6d47e8" stroke-width="3" stroke-linejoin="round"/></svg>
    <div class="chips"><span class="chip">PM2.5 <b>${d.aqi.pm25}</b> µg/m³</span><span class="chip">PM10 <b>${d.aqi.pm10}</b></span>
      <span class="chip">O₃ <b>${d.aqi.o3}</b></span><span class="chip">NO₂ <b>${d.aqi.no2}</b></span></div>`;

  $('outside').innerHTML = `<div class="row"><h3>Make room for outside.</h3><span>👣</span></div>
    <div class="big" style="font-size:40px;margin:10px 0">${d.outside.window}</div>
    <span class="pill" style="color:var(--brand)">Best for you</span>
    <p style="font-size:13px;margin-top:10px">${d.outside.text}</p>
    <p class="muted" style="margin-top:8px">AQI ${d.outside.aqi} · ${cat(d.outside.aqi)[1]}</p>
    <a class="btn" href="/account/">Set a fresh-air reminder →</a>`;
}

// City dropdown + live location come from location.js; any location change re-fetches.
const refresh = () => load().then(render);
Aero.bindCitySelect($('city')).then(refresh);
Aero.onChange(refresh);
Aero.autoRefresh(refresh, 10 * 60 * 1000);
