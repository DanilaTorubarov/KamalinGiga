/* ════════════════════════════════════════════════════════════
   THEME
   ════════════════════════════════════════════════════════════ */
function setTheme(mode){
  const root = document.documentElement;
  root.setAttribute('data-theme', mode);
  document.querySelectorAll('.theme-toggle button').forEach(b => b.classList.remove('on'));
  document.getElementById('th-'+mode).classList.add('on');
  try{ localStorage.setItem('razv-theme', mode); }catch(e){}
}
document.getElementById('th-light').onclick = ()=> setTheme('light');
document.getElementById('th-dark' ).onclick = ()=> setTheme('dark');
try{
  const saved = localStorage.getItem('razv-theme');
  if (saved === 'dark' || saved === 'light') setTheme(saved);
  else setTheme('light');
}catch(e){ setTheme('light'); }

/* ════════════════════════════════════════════════════════════
   BACKEND — only lat, lng, address, category are supported
   ════════════════════════════════════════════════════════════ */
const API_BASE = window.RAZVLEKIS_API_BASE || '/api';

const api = {
  geocode:  (address)         => apiFetch('/geocode', { method:'POST', body:{ address } }),
  listPlaces:(params)         => apiFetch('/places' + buildQs(params)),
  toggleSave:(placeId, save)  => apiFetch(`/places/${encodeURIComponent(placeId)}/save`, { method: save ? 'POST' : 'DELETE' }),
  chat:     (payload)         => apiFetch('/chat', { method:'POST', body: payload }),
  suggest:  (q, lat, lng)    => apiFetch('/suggestions' + buildQs({ q, lat, lng })),
};

async function apiFetch(path, { method='GET', body }={}){
  const headers = { Accept:'application/json' };
  let initBody;
  if (body !== undefined){ headers['Content-Type']='application/json'; initBody=JSON.stringify(body); }
  const res = await fetch(API_BASE+path, { method, headers, body:initBody, credentials:'same-origin' });
  if (!res.ok){ const text = await res.text().catch(()=>res.statusText); throw new Error(`API ${method} ${path} → ${res.status}: ${text}`); }
  if (res.status===204) return null;
  const ct = res.headers.get('content-type')||'';
  return ct.includes('application/json') ? res.json() : res.text();
}

function buildQs(o){
  if (!o) return '';
  const parts=[];
  for (const k in o){
    const v=o[k]; if(v===undefined||v===null||v==='') continue;
    if(Array.isArray(v)){ if(!v.length) continue; parts.push(encodeURIComponent(k)+'='+encodeURIComponent(v.join(','))); }
    else parts.push(encodeURIComponent(k)+'='+encodeURIComponent(v));
  }
  return parts.length ? '?'+parts.join('&') : '';
}

/* ════════════════════════════════════════════════════════════
   STATE
   ════════════════════════════════════════════════════════════ */
const state = {
  address: '',
  lat: null, lng: null,
  category: 'all',
  sort: 'near',
  filters: [],
  allPlaces: [],   // raw from API (unfiltered/unsorted)
  places: [],      // after client-side sort + filter
};
let inFlight = null;

const CAT_LABELS = {
  restaurant: 'Ресторан',
  cafe: 'Кофейня',
  bar: 'Бар',
  meal_takeaway: 'Доставка / Takeaway',
  cinema: 'Кино',
  cult: 'Культура',
  fun: 'Развлечения',
  park: 'Парк',
};

/* ════════════════════════════════════════════════════════════
   LANDING ⇄ RESULTS
   ════════════════════════════════════════════════════════════ */
const landingEl  = document.getElementById('landing');
const resultsEl  = document.getElementById('results');
const mainSearch = document.getElementById('mainSearch');
const inlineSearch = document.getElementById('inlineSearch');
const aiFab      = document.getElementById('aiFab');

function doSearch(q){
  q = (q||'').trim();
  if (!q) q = 'Москва, центр';
  state.address = q;
  inlineSearch.value = q;

  landingEl.classList.add('dismissed');

  setTimeout(async ()=>{
    landingEl.style.display = 'none';
    resultsEl.classList.add('on');
    aiFab.style.display = 'flex';
    window.scrollTo({top:0});

    try {
      const g = await api.geocode(q);
      if (g && typeof g.lat==='number' && typeof g.lng==='number'){
        state.lat = g.lat; state.lng = g.lng;
        if (g.label) state.address = g.label;
      }
    } catch (err){ console.warn('[geocode] failed', err); }

    fetchAndRender();
  }, 380);
}

function goLanding(e){
  if(e) e.preventDefault();
  resultsEl.classList.remove('on');
  aiFab.style.display = 'none';
  document.getElementById('aiPanel').classList.remove('on');
  setTimeout(()=>{
    landingEl.style.display = 'flex';
    requestAnimationFrame(()=> landingEl.classList.remove('dismissed'));
  }, 50);
}

mainSearch.addEventListener('keydown', e => { if(e.key==='Enter') doSearch(e.target.value); });

inlineSearch.addEventListener('keydown', async e => {
  if (e.key === 'Enter') {
    const val = e.target.value.trim();
    if (!val) return;
    state.address = val;
    try {
      const g = await api.geocode(val);
      if (g && typeof g.lat==='number' && typeof g.lng==='number'){
        state.lat = g.lat; state.lng = g.lng;
        if (g.label) state.address = g.label;
      }
    } catch (err){ console.warn('[geocode] inline failed', err); }
    fetchAndRender();
  }
});

/* ════════════════════════════════════════════════════════════
   AUTOCOMPLETE
   ════════════════════════════════════════════════════════════ */
let acTimer = null;
let acAbort = null;

function setupAC(input, dropId, onSelect){
  const drop = document.getElementById(dropId);
  input.addEventListener('input', ()=>{
    const q = input.value.trim();
    clearTimeout(acTimer);
    if (q.length < 2){ drop.classList.remove('on'); drop.innerHTML=''; return; }
    acTimer = setTimeout(async ()=>{
      if (acAbort) acAbort.abort();
      acAbort = new AbortController();
      try {
        const items = await api.suggest(q, state.lat, state.lng);
        if (!Array.isArray(items) || !items.length){ drop.classList.remove('on'); drop.innerHTML=''; return; }
        drop.innerHTML = '';
        items.forEach(text => {
          const el = document.createElement('div');
          el.className = 'ac-item';
          el.textContent = text;
          el.addEventListener('mousedown', e => {
            e.preventDefault();
            input.value = text;
            drop.classList.remove('on'); drop.innerHTML='';
            onSelect(text);
          });
          drop.appendChild(el);
        });
        drop.classList.add('on');
      } catch(e){ if(e.name!=='AbortError') console.warn('[suggest]', e); }
    }, 280);
  });

  input.addEventListener('blur', ()=>{ drop.classList.remove('on'); drop.innerHTML=''; });

  input.addEventListener('keydown', e => {
    if (!drop.classList.contains('on')) return;
    const items = drop.querySelectorAll('.ac-item');
    let idx = [...items].findIndex(x => x.classList.contains('ac-active'));
    if (e.key==='ArrowDown'){ e.preventDefault(); idx = (idx+1)%items.length; highlightAC(items, idx); }
    else if (e.key==='ArrowUp'){ e.preventDefault(); idx = idx<=0 ? items.length-1 : idx-1; highlightAC(items, idx); }
    else if (e.key==='Enter' && idx>=0){ e.preventDefault(); items[idx].dispatchEvent(new MouseEvent('mousedown')); }
    else if (e.key==='Escape'){ drop.classList.remove('on'); drop.innerHTML=''; }
  });
}

function highlightAC(items, idx){
  items.forEach(x => x.classList.remove('ac-active'));
  items[idx].classList.add('ac-active');
  items[idx].scrollIntoView({ block:'nearest' });
}

setupAC(mainSearch, 'acMain', text => doSearch(text));
setupAC(inlineSearch, 'acInline', async text => {
  state.address = text;
  try {
    const g = await api.geocode(text);
    if (g && typeof g.lat==='number' && typeof g.lng==='number'){
      state.lat = g.lat; state.lng = g.lng;
      if (g.label) state.address = g.label;
    }
  } catch(err){ console.warn('[geocode] inline ac failed', err); }
  fetchAndRender();
});

/* ════════════════════════════════════════════════════════════
   GEOLOCATION BUTTON
   ════════════════════════════════════════════════════════════ */
function requestGeo(e, source){
  if(e) e.preventDefault();
  const btn = e.currentTarget;
  if (!navigator.geolocation){ alert('Геолокация не поддерживается вашим браузером'); return; }

  btn.classList.add('locating');

  navigator.geolocation.getCurrentPosition(
    pos => {
      btn.classList.remove('locating');
      state.lat = pos.coords.latitude;
      state.lng = pos.coords.longitude;
      state.address = 'Моё местоположение';
      mainSearch.value = state.address;
      inlineSearch.value = state.address;

      if (source === 'main'){
        landingEl.classList.add('dismissed');
        setTimeout(()=>{
          landingEl.style.display = 'none';
          resultsEl.classList.add('on');
          aiFab.style.display = 'flex';
          window.scrollTo({top:0});
          fetchAndRender();
        }, 380);
      } else {
        fetchAndRender();
      }
    },
    err => {
      btn.classList.remove('locating');
      const msg = err.code===1 ? 'Геолокация недоступна — сайт должен работать по HTTPS. Попробуйте открыть страницу через https://physgraph.tech' : 'Не удалось определить местоположение';
      alert(msg);
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
  );
}

/* ════════════════════════════════════════════════════════════
   FETCH → store raw data, then apply filters/sort & render
   ════════════════════════════════════════════════════════════ */
async function fetchAndRender(){
  if (inFlight) inFlight.abort();
  inFlight = new AbortController();

  const grid = document.getElementById('grid');
  grid.setAttribute('aria-busy','true');

  const params = {
    lat: state.lat, lng: state.lng,
    address: state.lat==null ? state.address : undefined,
    category: state.category,
  };

  let data;
  try { data = await api.listPlaces(params); }
  catch (err){
    console.warn('[/places] failed', err);
    state.allPlaces=[]; state.places=[];
    renderError(err);
    grid.removeAttribute('aria-busy');
    return;
  }

  state.allPlaces = (data.places||[]).map(p => ({ ...p, category: p.category||'', image_url: p.image_url||null }));

  applyAndRender();
  if (data.categories) renderCategories(data.categories);
  grid.removeAttribute('aria-busy');
}

/* Client-side sort + filter on stored data — no API call */
function applyAndRender(){
  let places = [...state.allPlaces];

  if (state.filters.includes('open'))   places = places.filter(p => p.is_open===true);
  if (state.filters.includes('walk'))   places = places.filter(p => p.distance_m!=null && p.distance_m<=1000);
  if (state.filters.includes('budget')) places = places.filter(p => p.price==='$' || p.price==='$$');

  if (state.sort==='rating') places.sort((a,b)=>(b.rating??0)-(a.rating??0));
  else if (state.sort==='price') places.sort((a,b)=>priceOrder(a.price)-priceOrder(b.price));
  // default 'near' — backend already sorts by distance

  state.places = places;
  renderGrid(places);
  document.getElementById('countNum').textContent = places.length;
}

function priceOrder(p){ if(!p) return 99; return p.length; }

function renderGrid(places){
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  if (!places.length){
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'По вашему запросу ничего не найдено. Попробуйте сбросить фильтры.';
    grid.appendChild(empty);
    return;
  }
  places.forEach((p,i)=> grid.appendChild(buildCard(p,i)));
}

function renderCategories(cats){
  const tabs = document.getElementById('tabs');
  if (!cats||!cats.length) return;
  const previous = state.category;
  tabs.innerHTML = '';
  cats.forEach(cat => {
    const btn = document.createElement('button');
    btn.className = 'tab'+(cat.id===previous?' on':'');
    btn.dataset.cat = cat.id;
    btn.innerHTML = `${cat.label}<span class="count">${cat.count??0}</span>`;
    btn.addEventListener('click', () => {
      state.category = cat.id;
      tabs.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
      btn.classList.add('on');
      fetchAndRender();  // category change → new API call
    });
    tabs.appendChild(btn);
  });
}

function renderError(err){
  document.getElementById('grid').innerHTML = `<div class="empty-state">Не удалось загрузить места. ${(err&&err.message)||''}</div>`;
}

/* ════════════════════════════════════════════════════════════
   CARD
   ════════════════════════════════════════════════════════════ */
function buildCard(p, i){
  const c = document.createElement('a');
  c.className = 'card'+(p.image_url?'':' no-photo');
  c.dataset.id = p.id;
  c.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.name)}&query_place_id=${encodeURIComponent(p.id)}`;
  c.target = '_blank';
  c.rel = 'noopener';
  c.style.textDecoration = 'none';
  c.style.color = 'inherit';

  const catLabel = CAT_LABELS[p.category] || p.category || '';
  const distance = p.distance_label || (p.distance_m!=null ? formatDistance(p.distance_m) : '');
  const openLabel = 'is_open' in p ? (p.is_open ? 'Открыто' : 'Закрыто') : null;
  const ratingHtml = p.rating!=null ? `<span class="rating"><span class="star">★</span>${(+p.rating).toFixed(1)}</span><span class="dot-sep"></span>` : '';
  const priceHtml  = p.price ? `<span class="dot-sep"></span><span class="price"><b>${esc(p.price)}</b></span>` : '';
  const isSaved = p.saved || isPlaceSaved(p.id);
  const saveBtn = `
    <button class="card-save${isSaved?' saved':''}" aria-label="Сохранить" onclick="onSaveClick(event,this)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="${isSaved?'currentColor':'none'}" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
      </svg>
    </button>`;

  if (p.image_url){
    c.innerHTML = `
      <img class="card-img" src="${esc(p.image_url)}" alt="${esc(p.name)}" loading="lazy"
           onerror="this.parentElement.classList.add('no-photo'); this.outerHTML=makeNoPhoto('${esc(p.name).replace(/'/g,'\\\'')}')">
      <div class="card-top">
        <span class="badge-glass">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 0-8 8c0 6 8 12 8 12s8-6 8-12a8 8 0 0 0-8-8z"/></svg>
          ${esc(distance)}
        </span>
        ${openLabel!=null ? `<span class="badge-glass">${openLabel}</span>` : ''}
        ${saveBtn}
      </div>
      <div class="card-foot">
        <div class="card-name">${esc(p.name)}</div>
        <div class="card-meta">
          ${ratingHtml}
          <span class="cat">${esc(catLabel)}</span>
          ${priceHtml}
        </div>
      </div>`;
  } else {
    c.innerHTML = noPhotoMarkup(p, distance, openLabel, saveBtn, ratingHtml, priceHtml, catLabel);
  }

  setTimeout(()=> c.classList.add('show'), 70+i*55);
  return c;
}

function noPhotoMarkup(p, distance, openLabel, saveBtn, ratingHtml, priceHtml, catLabel){
  const letter = (p.name.match(/«([^»]+)»/)?.[1]||p.name).trim().charAt(0).toUpperCase();
  return `
    <div class="card-bg"></div>
    <div class="card-top">
      <span class="badge-glass">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 0-8 8c0 6 8 12 8 12s8-6 8-12a8 8 0 0 0-8-8z"/></svg>
        ${esc(distance)}
      </span>
      ${openLabel!=null ? `<span class="badge-glass">${openLabel}</span>` : ''}
      ${saveBtn}
    </div>
    <div class="monogram">
      <span class="letter">${esc(letter)}</span>
      <span class="strap">Фото скоро</span>
    </div>
    <div class="card-foot">
      <div class="card-name">${esc(p.name)}</div>
      <div class="card-meta">
        ${ratingHtml}
        <span class="cat">${esc(catLabel)}</span>
        ${priceHtml}
      </div>
    </div>`;
}
window.makeNoPhoto = (name)=> `<div class="card-bg"></div><div class="monogram"><span class="letter">${(name||'').charAt(0)}</span><span class="strap">Без фото</span></div>`;

function esc(s){ return String(s??'').replace(/[&<>"']/g, ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function formatDistance(m){ if(m==null) return ''; return m<1000 ? `${Math.round(m)} м` : `${(m/1000).toFixed(1)} км`; }

/* ── Cookie helpers for saved places ── */
const SAVED_COOKIE = 'razvlekis_saved';

function getSavedIds(){
  try {
    const match = document.cookie.match(new RegExp('(?:^|;\\s*)' + SAVED_COOKIE + '=([^;]*)'));
    if (match) return JSON.parse(decodeURIComponent(match[1]));
  } catch(e){}
  return [];
}

function setSavedIds(ids){
  const expires = new Date(Date.now() + 365*24*60*60*1000).toUTCString();
  document.cookie = SAVED_COOKIE + '=' + encodeURIComponent(JSON.stringify(ids)) +
    '; expires=' + expires + '; path=/; SameSite=Lax';
}

function isPlaceSaved(id){ return getSavedIds().includes(id); }

function toggleSavedId(id, save){
  let ids = getSavedIds();
  if (save) { if (!ids.includes(id)) ids.push(id); }
  else      { ids = ids.filter(x => x !== id); }
  setSavedIds(ids);
}

async function onSaveClick(e, el){
  e.preventDefault(); e.stopPropagation();
  const card = el.closest('.card');
  const id = card && card.dataset.id;
  if (!id) return;
  const willSave = !el.classList.contains('saved');
  el.classList.toggle('saved', willSave);
  el.querySelector('svg').setAttribute('fill', willSave?'currentColor':'none');
  toggleSavedId(id, willSave);
  try { await api.toggleSave(id, willSave); }
  catch (err){ console.warn('[/places/{id}/save] API failed, but cookie saved', err); }
}

/* ════════════════════════════════════════════════════════════
   TABS — category change → new API call (fetchAndRender)
   ════════════════════════════════════════════════════════════ */
document.querySelectorAll('#tabs .tab').forEach(t => t.addEventListener('click', ()=>{
  document.querySelectorAll('#tabs .tab').forEach(x=>x.classList.remove('on'));
  t.classList.add('on');
  state.category = t.dataset.cat || 'all';
  fetchAndRender();
}));

/* ════════════════════════════════════════════════════════════
   FILTER — sort/filters → client-side only (applyAndRender)
   ════════════════════════════════════════════════════════════ */
function toggleFilter(e){
  if(e) e.stopPropagation();
  const drop = document.getElementById('filterDrop');
  const btn  = document.getElementById('filterBtn');
  const open = drop.classList.toggle('on');
  btn.classList.toggle('open', open);
  if (open) setTimeout(()=> document.addEventListener('click', closeFilterOnce), 10);
}
function closeFilterOnce(e){
  if (e && e.target.closest('#filterDrop')){ document.addEventListener('click', closeFilterOnce, {once:true}); return; }
  document.getElementById('filterDrop').classList.remove('on');
  document.getElementById('filterBtn').classList.remove('open');
}

document.querySelectorAll('#filterDrop .drop-item[data-sort]').forEach(item=>{
  item.addEventListener('click', e => {
    e.stopPropagation();
    document.querySelectorAll('#filterDrop .drop-item[data-sort]').forEach(x=>x.classList.remove('on'));
    item.classList.add('on');
    state.sort = item.dataset.sort;
    syncApplied();
    applyAndRender();  // client-side, no API call
  });
});

document.querySelectorAll('#filterDrop .drop-item.filter-toggle').forEach(item=>{
  item.addEventListener('click', e => {
    e.stopPropagation();
    item.classList.toggle('on');
    state.filters = [...document.querySelectorAll('#filterDrop .drop-item.filter-toggle.on')].map(x=>x.dataset.filter);
    syncApplied();
    applyAndRender();  // client-side, no API call
  });
});

function syncApplied(){
  const sortItem = document.querySelector('#filterDrop .drop-item[data-sort].on');
  const filterItems = [...document.querySelectorAll('#filterDrop .drop-item.filter-toggle.on')];
  const pills = [];
  if (sortItem) pills.push({ key:'sort', label:sortItem.textContent.trim() });
  filterItems.forEach(f => pills.push({ key:f.dataset.filter, label:f.textContent.trim(), filter:true }));

  const container = document.getElementById('appliedPills');
  container.innerHTML = '';
  pills.forEach(p => {
    const el = document.createElement('span');
    el.className = 'pill'+(p.filter?' is-filter':'');
    el.innerHTML = `<span>${p.label}</span><button aria-label="Сбросить"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;
    el.querySelector('button').addEventListener('click', () => {
      if (p.filter){
        document.querySelector(`#filterDrop .drop-item[data-filter="${p.key}"]`).classList.remove('on');
        state.filters = state.filters.filter(f=>f!==p.key);
      } else {
        document.querySelectorAll('#filterDrop .drop-item[data-sort]').forEach(x=>x.classList.remove('on'));
        state.sort = null;
      }
      syncApplied();
      applyAndRender();
    });
    container.appendChild(el);
  });

  const count = pills.length;
  const badge = document.getElementById('filterBadge');
  badge.textContent = String(count);
  badge.style.display = count ? 'flex' : 'none';
}

syncApplied();

function syncBrandOffset(){
  const brand = document.querySelector('.header .brand-sm');
  const header = document.querySelector('.header');
  if (!brand||!header) return;
  const offset = (brand.getBoundingClientRect().right - header.getBoundingClientRect().left) + 10;
  header.style.setProperty('--brand-offset', offset+'px');
}
window.addEventListener('resize', syncBrandOffset);
if (document.fonts&&document.fonts.ready) document.fonts.ready.then(syncBrandOffset);
requestAnimationFrame(syncBrandOffset);

/* ════════════════════════════════════════════════════════════
   AI
   ════════════════════════════════════════════════════════════ */
const aiHistory = [];

function toggleAI(){ document.getElementById('aiPanel').classList.toggle('on'); }
function quickAsk(b){ document.getElementById('aiInput').value=b.textContent; sendAI(); }

function mdToHtml(s){
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
  s = s.replace(/\n{2,}/g, '\n');
  return s;
}

async function sendAI(){
  const inp = document.getElementById('aiInput');
  const q = inp.value.trim();
  if (!q) return;
  inp.value = '';

  const m = document.getElementById('aiMsgs');
  const u = document.createElement('div'); u.className='ai-bubble usr'; u.textContent=q; m.appendChild(u);
  const b = document.createElement('div'); b.className='ai-bubble bot'; b.textContent='…'; m.appendChild(b);
  m.scrollTop = m.scrollHeight;

  aiHistory.push({ role:'user', content:q });

  const payload = {
    message: q,
    history: aiHistory.slice(0,-1),
    context: {
      address: state.address||null,
      lat: state.lat, lng: state.lng,
      category: state.category,
      sort: state.sort,
      filters: state.filters,
      places: state.places.map(p=>({ name:p.name, address:p.address, category:p.category, distance_label:p.distance_label })),
    },
  };

  let reply;
  try {
    const data = await api.chat(payload);
    reply = data && data.reply ? data.reply : '…';
  } catch (err){
    console.warn('[/chat] failed', err);
    b.textContent = 'Не удалось получить ответ от ассистента. '+((err&&err.message)||'Попробуйте позже.');
    return;
  }

  b.innerHTML = mdToHtml(reply);
  aiHistory.push({ role:'assistant', content:reply });
  m.scrollTop = m.scrollHeight;
}