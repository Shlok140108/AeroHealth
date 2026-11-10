const CATS = [[50,'Good','#3aa655'],[100,'Satisfactory','#8fc43f'],[200,'Moderate','#f2c230'],
              [300,'Poor','#f08a24'],[400,'Very Poor','#e0443e'],[500,'Severe','#9b1c31']];
const cat = v => CATS.find(c => v <= c[0]) || CATS[5];
const $ = id => document.getElementById(id);

async function load(){
  const {lat, lon, place} = Aero.loc();
  try{
    const r = await fetch($('pred').dataset.api + '?' + new URLSearchParams({lat, lon, place}));
    if(r.status === 400){ const j = await r.json().catch(()=>({})); return {error: j.error}; }
    if(!r.ok) throw 0; return await r.json(); }
  catch(e){ return null; }               // no sample fallback: never show made-up health advice
}

function render(d){
  if(d && d.error){ $('wx').innerHTML = `<h3>Can't show this place</h3><p class="muted">${Aero.esc(d.error)}</p>`;
    $('aq').innerHTML = ''; $('health').innerHTML = ''; return; }
  if(!d){ $('wx').innerHTML = '<h3>Couldn\'t load predictions</h3><p class="muted">Check that the server is running, then pick a city again.</p>';
          $('aq').innerHTML = ''; $('health').innerHTML = ''; return; }
  $('stamp').textContent = d.updated;
  const lo = Math.min(...d.days.map(x=>x.lo)), hi = Math.max(...d.days.map(x=>x.hi)), span = hi-lo||1;

  $('wx').innerHTML = `<div class="row"><h3>Weather prediction</h3><span class="muted">7 days · ${Aero.esc(d.place)}</span></div>` +
    d.days.map(x=>`<div class="week-row"><b>${x.day}</b><span class="muted">💧${x.rain}%</span><span class="muted">${x.lo}°</span>
      <div class="bar"><i style="left:${(x.lo-lo)/span*100}%;right:${100-(x.hi-lo)/span*100}%"></i></div><b>${x.hi}°</b></div>`).join('') +
    (d.typical_temp_today!=null ? `<p class="muted" style="margin-top:10px">Our model's typical temperature for this date: ${d.typical_temp_today}°C</p>` : '');

  $('aq').innerHTML = `<div class="row"><h3>AQI prediction</h3><span class="muted">CPCB scale · 5 days</span></div>` +
    d.days.map(x=>{ if(x.aqi_avg==null) return `<div class="aq-row"><b>${x.day}</b><span class="muted">Not forecast yet</span></div>`;
      const k = cat(x.aqi_max);
      return `<div class="aq-row"><b>${x.day}</b><div class="bar"><i style="left:0;right:${100-x.aqi_max/500*100}%;background:${k[2]}"></i></div>
        <span class="tag" style="background:${k[2]}">${x.aqi_avg} avg · ${x.aqi_max} peak</span></div>`; }).join('') +
    `<p class="muted" style="margin-top:10px">Estimates from forecast pollutants; they can differ from live sensor readings.</p>`;

  const a = d.advice, k = cat(d.days[0].aqi_max);
  $('health').innerHTML = `
    <div class="card hhead" style="border-left:6px solid ${k[2]}"><div class="muted">${a.basis}</div>
      <h2 style="color:${k[2]}">${a.band}: ${a.headline}</h2></div>
    <h3 class="sub">Concerns by group</h3>
    <div class="hgrid">${a.groups.map(g=>`<div class="concern"><b>${g.who}</b><p>${g.text}</p></div>`).join('')}</div>
    <h3 class="sub">What you can do</h3>
    <ul class="acts">${a.actions.map(t=>`<li>${t}</li>`).join('')}</ul>`;
}

const go = () => load().then(render);
Aero.bindCitySelect($('city')).then(go);
Aero.onChange(go);
Aero.autoRefresh(go, 10 * 60 * 1000);
