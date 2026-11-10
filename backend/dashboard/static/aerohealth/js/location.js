/* Shared location layer for every page: current place, city search, and live GPS tracking.
 *
 *   Aero.loc()                      -> {lat, lon, place}  (what every page should render)
 *   Aero.setLocation(lat, lon, place, source)
 *   Aero.startLive() / stopLive()   -> navigator.geolocation.watchPosition tracking
 *   window events: 'aero:location' (place changed -> pages re-fetch)
 *                  'aero:position' (every GPS fix -> tracker map)
 *                  'aero:livestate' (off | locating | tracking | weak | denied | insecure | unavailable)
 *
 * Privacy: GPS fixes stay in the browser. The server only ever receives rounded coordinates
 * to fetch weather / a place name, and nothing is stored.
 */
(function () {
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode: keep working in memory */ } },
  };
  const DEFAULT = { lat: 28.6139, lon: 77.209, place: 'Delhi' };
  const MOVE_KM = 0.5;                 // re-fetch weather after moving this far
  const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function km(a, b, c, d) {            // haversine distance in km
    const r = x => x * Math.PI / 180, dLat = r(c - a), dLon = r(d - b);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(r(a)) * Math.cos(r(c)) * Math.sin(dLon / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(h));
  }

  const Aero = { esc, km, state: 'off', pos: null, trail: [] };

  Aero.loc = () => {
    const lat = parseFloat(store.get('aero_lat')), lon = parseFloat(store.get('aero_lon'));
    if (Number.isFinite(lat) && Number.isFinite(lon)) return { lat, lon, place: store.get('aero_place') || 'Your location' };
    return { ...DEFAULT };
  };
  Aero.hasSaved = () => store.get('aero_lat') !== null;
  Aero.setLocation = (lat, lon, place, source) => {
    store.set('aero_lat', String(lat)); store.set('aero_lon', String(lon)); store.set('aero_place', place);
    emit('aero:location', { lat, lon, place, source });
  };
  Aero.onChange = fn => window.addEventListener('aero:location', fn);

  /* Re-run fn every `ms`, and again when the tab becomes visible after being hidden for a while. */
  Aero.autoRefresh = (fn, ms) => {
    let last = Date.now();
    const run = () => { last = Date.now(); fn(); };
    setInterval(() => { if (!document.hidden) run(); }, ms);
    document.addEventListener('visibilitychange', () => { if (!document.hidden && Date.now() - last > ms) run(); });
  };

  /* ---------- search & reverse geocoding ---------- */
  Aero.search = async q => {
    const r = await fetch('/api/geocode/?q=' + encodeURIComponent(q));
    if (!r.ok) throw new Error('search failed');
    return (await r.json()).results;
  };
  Aero.reverse = async (lat, lon) => {
    try {
      const r = await fetch(`/api/reverse/?lat=${lat}&lon=${lon}`);
      if (r.ok) return (await r.json()).label;
    } catch (e) { /* fall through */ }
    return `${lat.toFixed(3)}, ${lon.toFixed(3)}`;
  };

  /* ---------- live GPS tracking ---------- */
  let watchId = null, lastApplied = null, applying = false;
  const setState = (s, extra) => { Aero.state = s; emit('aero:livestate', { state: s, ...extra }); };

  async function applyFix(p) {
    if (applying) return;
    applying = true; lastApplied = { lat: p.lat, lon: p.lon };
    try {
      const label = await Aero.reverse(p.lat, p.lon);
      if (watchId !== null) Aero.setLocation(p.lat, p.lon, label, 'live');   // user may have stopped meanwhile
    } finally { applying = false; }
  }

  function onFix(g) {
    const c = g.coords;
    const p = { lat: c.latitude, lon: c.longitude, accuracy: c.accuracy, speed: c.speed, heading: c.heading,
                altitude: c.altitude, ts: g.timestamp };
    Aero.pos = p;
    Aero.trail.push([p.lat, p.lon]); if (Aero.trail.length > 500) Aero.trail.shift();
    if (Aero.state !== 'tracking') setState('tracking', { pos: p });
    emit('aero:position', p);
    if (!lastApplied || km(lastApplied.lat, lastApplied.lon, p.lat, p.lon) >= MOVE_KM) applyFix(p);
  }

  function onError(e) {
    if (e.code === 1) { Aero.stopLive(false); setState('denied'); }      // PERMISSION_DENIED
    else setState('weak');                                               // unavailable / timeout: keep watching
  }

  Aero.startLive = () => {
    if (!('geolocation' in navigator)) return setState('unavailable');
    if (!window.isSecureContext) return setState('insecure');
    if (watchId !== null) return;
    setState('locating'); store.set('aero_live', '1');
    watchId = navigator.geolocation.watchPosition(onFix, onError, { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 });
  };
  Aero.stopLive = (announce = true) => {
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    watchId = null; lastApplied = null; store.set('aero_live', '0');
    if (announce) setState('off');
  };
  Aero.toggleLive = () => (watchId === null ? Aero.startLive() : Aero.stopLive());

  /* ---------- shared city dropdown (overview + prediction pages) ---------- */
  Aero.bindCitySelect = async sel => {
    let list = [];
    try { list = (await (await fetch('/api/cities/')).json()).cities; } catch (e) { /* keep empty */ }
    if (!Aero.hasSaved() && list.length) store.set('aero_lat', String(list[0].lat)), store.set('aero_lon', String(list[0].lon)), store.set('aero_place', list[0].label);
    const build = () => {
      const { lat, lon, place } = Aero.loc(), key = `${lat},${lon}`;
      let html = list.map(c => `<option value="${c.lat},${c.lon}" data-label="${esc(c.label)}">${esc(c.label)}</option>`).join('');
      if (!list.some(c => `${c.lat},${c.lon}` === key)) html = `<option value="${key}" data-label="${esc(place)}">📍 ${esc(place)}</option>` + html;
      sel.innerHTML = html; sel.value = key;
    };
    build();
    sel.onchange = () => {
      const [la, lo] = sel.value.split(',');
      Aero.stopLive();                                 // choosing a city by hand overrides live tracking
      Aero.setLocation(+la, +lo, sel.selectedOptions[0].dataset.label, 'select');
    };
    Aero.onChange(build);
  };

  /* ---------- topbar: live button + search box ---------- */
  const LIVE_UI = {
    off:         ['', '📍 Use live location', 'Track your location and keep the weather current'],
    locating:    ['busy', 'Locating…', 'Waiting for your device to share its position'],
    tracking:    ['on', 'Live', 'Tracking your location. Click to stop.'],
    weak:        ['busy', 'Signal weak…', 'Position temporarily unavailable; still trying'],
    denied:      ['bad', 'Location blocked', 'Allow location for this site in your browser settings, then click again'],
    insecure:    ['bad', 'Needs HTTPS', 'Browsers only share location on https:// or localhost. Open the app via http://localhost:8000'],
    unavailable: ['bad', 'No GPS support', 'This browser does not support geolocation'],
  };

  function paintLiveButton() {
    const b = document.getElementById('livebtn'); if (!b) return;
    const [cls, text, tip] = LIVE_UI[Aero.state] || LIVE_UI.off;
    let label = text;
    if (Aero.state === 'tracking' && Aero.pos && Aero.pos.accuracy != null) label = `Live · ±${Math.round(Aero.pos.accuracy)} m`;
    b.className = 'livebtn ' + cls; b.title = tip;
    b.innerHTML = `<i class="dot"></i><span>${esc(label)}</span>`;
    b.setAttribute('aria-pressed', Aero.state === 'tracking' ? 'true' : 'false');
  }

  function bindSearch() {
    const input = document.getElementById('gsearch'), box = document.getElementById('gres');
    if (!input || !box) return;
    let timer = null, seq = 0, results = [];
    const close = () => { box.hidden = true; box.innerHTML = ''; };
    const pickPlace = r => {
      Aero.stopLive(); close(); input.value = '';
      Aero.setLocation(r.lat, r.lon, r.label, 'search');
    };
    input.addEventListener('input', () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) return close();
      timer = setTimeout(async () => {
        const mine = ++seq;
        try {
          results = await Aero.search(q);
          if (mine !== seq) return;                    // a newer keystroke superseded this request
          box.innerHTML = results.length
            ? results.map((r, i) => `<button type="button" data-i="${i}">${esc(r.name)}<small>${esc([r.region, r.country].filter(Boolean).join(', '))}</small></button>`).join('')
            : '<div class="none">No matching places</div>';
        } catch (e) { box.innerHTML = '<div class="none">Search is unavailable right now</div>'; }
        box.hidden = false;
      }, 300);
    });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && results[0] && !box.hidden) { e.preventDefault(); pickPlace(results[0]); }
      if (e.key === 'Escape') close();
    });
    box.addEventListener('click', e => { const b = e.target.closest('button[data-i]'); if (b) pickPlace(results[+b.dataset.i]); });
    document.addEventListener('click', e => { if (!e.target.closest('.search')) close(); });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const b = document.getElementById('livebtn');
    if (b) b.addEventListener('click', Aero.toggleLive);
    window.addEventListener('aero:livestate', paintLiveButton);
    window.addEventListener('aero:position', paintLiveButton);
    paintLiveButton(); bindSearch();
    // Resume tracking after a page change only if the browser already granted permission (no surprise prompt).
    if (store.get('aero_live') === '1' && navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: 'geolocation' }).then(s => { if (s.state === 'granted') Aero.startLive(); }).catch(() => {});
    }
  });

  window.Aero = Aero;
})();
