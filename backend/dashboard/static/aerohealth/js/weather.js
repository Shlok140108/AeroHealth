/* Weather page: conventional weather-app view + live location tracker map. Depends on location.js (Aero). */
const $ = id => document.getElementById(id);
const esc = Aero.esc;

/* ---------- units ---------- */
let units = 'c';
try { units = localStorage.getItem('aero_units') === 'f' ? 'f' : 'c'; } catch (e) { /* ignore */ }
const T = c => c == null ? '–' : Math.round(units === 'f' ? c * 9 / 5 + 32 : c);
const SPEED = k => k == null ? '–' : Math.round(units === 'f' ? k * 0.621371 : k) + (units === 'f' ? ' mph' : ' km/h');
const DIST = k => k == null ? '–' : (units === 'f' ? (k * 0.621371).toFixed(1) + ' mi' : k + ' km');

const CPCB = [[50, 'Good', '#3aa655'], [100, 'Satisfactory', '#8fc43f'], [200, 'Moderate', '#f2c230'],
              [300, 'Poor', '#f08a24'], [400, 'Very Poor', '#e0443e'], [500, 'Severe', '#9b1c31']];
const USAQI = [[50, 'Good', '#3aa655'], [100, 'Moderate', '#f2c230'], [150, 'Unhealthy for sensitive groups', '#f08a24'],
               [200, 'Unhealthy', '#e0443e'], [300, 'Very unhealthy', '#8e3a9b'], [999, 'Hazardous', '#7e0023']];
const band = (scale, v) => scale.find(c => v <= c[0]) || scale[scale.length - 1];

const clock12 = iso => { const [h, m] = iso.slice(11, 16).split(':').map(Number); return `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`; };

/* ---------- weather rendering ---------- */
let data = null, seq = 0;

function renderWeather() {
  if (!data) return;
  const c = data.current, loc = Aero.loc(), live = Aero.state === 'tracking';
  const hero = $('hero'); hero.className = 'wx-hero ' + c.theme;
  hero.innerHTML = `
    <div class="wx-place">📍 ${esc(loc.place)} ${live ? '<span class="livebadge"><i class="dot"></i>LIVE</span>' : ''}</div>
    <div class="wx-main">
      <div><div class="wx-temp">${T(c.temp)}°</div><div class="wx-desc">${esc(c.desc)}</div>
        <div class="wx-sub">Feels like ${T(c.feels)}° · H ${T(c.hi)}° L ${T(c.lo)}°</div></div>
      <div class="wx-icon" aria-hidden="true">${c.icon}</div></div>
    <div class="wx-sub">${rainLine()} · Observed ${clock12(data.observed_at)} local time</div>`;

  $('hours').innerHTML = `<h3>Next 24 hours</h3><div class="hstrip">${data.hourly.map((h, i) => `
    <div class="hcell ${i ? '' : 'now'}"><span class="muted">${esc(h.label)}</span><span class="hi">${h.icon}</span>
    <b>${T(h.temp)}°</b><span class="rain">${h.rain >= 10 ? '💧' + h.rain + '%' : '&nbsp;'}</span></div>`).join('')}</div>`;

  const lo = Math.min(...data.daily.map(d => d.lo)), hi = Math.max(...data.daily.map(d => d.hi)), span = hi - lo || 1;
  $('days').innerHTML = `<h3>7-day forecast</h3>` + data.daily.map(d => `
    <div class="drow"><b>${esc(d.day)}</b><span class="di" title="${esc(d.desc)}">${d.icon}</span>
      <span class="rain">${d.rain >= 10 ? '💧' + d.rain + '%' : ''}</span><span class="muted">${T(d.lo)}°</span>
      <div class="bar"><i style="left:${(d.lo - lo) / span * 100}%;right:${100 - (d.hi - lo) / span * 100}%"></i></div><b>${T(d.hi)}°</b></div>`).join('');

  const tile = (title, body, sub = '', cls = '') => `<div class="tile"><div class="muted">${title}</div><div class="tv ${cls}">${body}</div><div class="muted">${sub}</div></div>`;
  const a = data.aqi;
  let aqiTile = tile('AIR QUALITY', 'N/A', 'Air-quality data unavailable');
  if (a && (a.cpcb != null || a.us_aqi != null)) {
    const useC = a.cpcb != null, v = useC ? a.cpcb : a.us_aqi, k = band(useC ? CPCB : USAQI, v);
    aqiTile = tile('AIR QUALITY', `<span style="color:${k[2]}">${v}</span>`, `${k[1]} · ${useC ? 'CPCB (model estimate)' : 'US AQI'}` +
      (a.pm25 != null ? `<br>PM2.5 ${a.pm25} µg/m³` : ''));
  }
  $('tiles').innerHTML = [
    tile('FEELS LIKE', T(c.feels) + '°', c.feels > c.temp + 1 ? 'Humidity makes it feel warmer' : c.feels < c.temp - 1 ? 'Wind makes it feel cooler' : 'Similar to the actual temperature'),
    tile('WIND', `${SPEED(c.wind)} <span class="arrow" style="transform:rotate(${(c.wind_deg ?? 0) + 180}deg)">↑</span>`,
         `From ${c.wind_dir ?? '–'}` + (c.gust != null ? ` · gusts ${SPEED(c.gust)}` : '')),
    tile('HUMIDITY', c.humidity + '%', `Dew point ${T(c.dew)}°`),
    tile('UV INDEX', c.uv ?? '–', c.uv_label),
    tile('VISIBILITY', DIST(c.visibility_km), c.visibility_km != null && c.visibility_km < 4 ? 'Reduced visibility' : 'Clear view'),
    tile('PRESSURE', (c.pressure ?? '–') + ' hPa', `Cloud cover ${c.cloud ?? '–'}%`),
    tile('SUNRISE · SUNSET', `🌅 ${data.sun.rise}`, `🌇 ${data.sun.set}`, 'sm'),
    aqiTile,
  ].join('');
}

function rainLine() {
  const h = data.hourly.find((x, i) => i > 0 && x.rain >= 50);
  if (data.current.precip > 0) return `Raining now (${data.current.precip} mm)`;
  return h ? `Rain likely around ${h.label}` : 'No rain expected in the next 24 hours';
}

function note(msg) { const n = $('wxnote'); n.hidden = !msg; n.textContent = msg || ''; }

async function fetchWeather() {
  const { lat, lon } = Aero.loc(), mine = ++seq;
  try {
    const r = await fetch($('wxapp').dataset.api + '?' + new URLSearchParams({ lat, lon }));
    const j = await r.json().catch(() => ({}));
    if (mine !== seq) return;                         // a newer request (e.g. you moved again) supersedes this one
    if (!r.ok) throw new Error(j.error || 'Could not load the weather');
    data = j; note(''); renderWeather();
  } catch (e) {
    if (mine !== seq) return;
    if (data) { note(`${e.message}. Showing the last update.`); }
    else {
      $('hero').className = 'wx-hero cloud-day';
      $('hero').innerHTML = `<div class="skeleton"><b>Couldn't load the weather</b><br>${esc(e.message)}<br><button class="ghost" id="retry" style="margin-top:12px">Try again</button></div>`;
      $('retry').onclick = fetchWeather;
    }
  }
}

/* ---------- units toggle ---------- */
function paintUnits() { document.querySelectorAll('#units button').forEach(b => b.classList.toggle('on', b.dataset.u === units)); }
document.querySelectorAll('#units button').forEach(b => b.onclick = () => {
  units = b.dataset.u; try { localStorage.setItem('aero_units', units); } catch (e) { /* ignore */ }
  paintUnits(); renderWeather(); paintStats();
});
paintUnits();

/* ---------- live tracker map ---------- */
let map = null, dot = null, ring = null, trail = null, follow = true;

function initMap() {
  if (!window.L) { $('map').innerHTML = '<div class="skeleton">The map library could not be loaded.</div>'; return; }
  const { lat, lon } = Aero.loc();
  map = L.map('map', { zoomControl: true }).setView([lat, lon], 13);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap contributors' }).addTo(map);
  dot = L.circleMarker([lat, lon], { radius: 8, color: '#fff', weight: 3, fillColor: '#2f6fed', fillOpacity: 1 }).addTo(map);
  ring = L.circle([lat, lon], { radius: 0, color: '#2f6fed', weight: 1, fillOpacity: 0.12 }).addTo(map);
  trail = L.polyline([], { color: '#6d47e8', weight: 3, opacity: 0.7 }).addTo(map);
  map.on('dragstart', () => { follow = false; $('trk-center').hidden = false; });
  $('trk-center').onclick = () => { follow = true; $('trk-center').hidden = true; if (Aero.pos) map.setView([Aero.pos.lat, Aero.pos.lon], Math.max(map.getZoom(), 15)); };
}

const STATE_MSG = {
  off: 'Share your position and the weather follows you as you move.',
  locating: 'Waiting for your device to share its position…',
  tracking: 'Tracking. The forecast refreshes automatically when you move about 500 m.',
  weak: 'Position temporarily unavailable. Still trying…',
  denied: 'Location access is blocked. Allow it for this site in your browser settings, then try again.',
  insecure: 'Browsers only share location on https:// or localhost. Open this app at http://localhost:8000.',
  unavailable: 'This browser does not support geolocation. You can still search for a city above.',
};

function paintTracker() {
  const on = ['locating', 'tracking', 'weak'].includes(Aero.state);
  $('trk-btn').textContent = on ? 'Stop tracking' : 'Start tracking';
  $('trk-btn').classList.toggle('stop', on);
  $('trk-msg').textContent = STATE_MSG[Aero.state] || STATE_MSG.off;
}

function paintStats() {
  const p = Aero.pos, el = $('trk-stats');
  if (!p || !['tracking', 'weak'].includes(Aero.state)) { el.innerHTML = ''; return; }
  const sp = p.speed != null && p.speed >= 0 ? SPEED(p.speed * 3.6) : '–';
  const cell = (k, v) => `<div><span class="muted">${k}</span><b>${v}</b></div>`;
  el.innerHTML = cell('Latitude', p.lat.toFixed(5)) + cell('Longitude', p.lon.toFixed(5)) +
    cell('Accuracy', `±${Math.round(p.accuracy)} m`) + cell('Speed', sp) +
    cell('Heading', p.heading != null && !Number.isNaN(p.heading) ? Math.round(p.heading) + '°' : '–') +
    cell('Altitude', p.altitude != null ? Math.round(p.altitude) + ' m' : '–') +
    cell('Last fix', new Date(p.ts).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit' })) +
    (p.accuracy > 1000 ? `<div class="warn">Low accuracy: this looks like a network-based location, not GPS.</div>` : '');
}

$('trk-btn').onclick = Aero.toggleLive;
window.addEventListener('aero:livestate', () => {
  paintTracker(); paintStats(); renderWeather();
  if (Aero.state === 'off' && map) { trail.setLatLngs([]); ring.setRadius(0); Aero.trail.length = 0; }
});
window.addEventListener('aero:position', e => {
  paintStats(); if (!map) return;
  const p = e.detail, ll = [p.lat, p.lon];
  dot.setLatLng(ll); ring.setLatLng(ll); ring.setRadius(p.accuracy || 0); trail.setLatLngs(Aero.trail);
  if (follow) map.setView(ll, Math.max(map.getZoom(), 15));
});

/* ---------- wiring ---------- */
initMap(); paintTracker();
Aero.onChange(e => {
  fetchWeather();
  if (map && e.detail.source !== 'live') { map.setView([e.detail.lat, e.detail.lon], 12); dot.setLatLng([e.detail.lat, e.detail.lon]); ring.setRadius(0); }
});
Aero.autoRefresh(fetchWeather, 5 * 60 * 1000);
fetchWeather();
