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
   BACKEND
   FastAPI is expected at API_BASE. See BACKEND.md for the
   full contract (endpoints, request/response schemas).
   Set window.RAZVLEKIS_API_BASE before the script loads to
   point at a non-default host (e.g. "http://localhost:8000/api").
   ════════════════════════════════════════════════════════════ */
const API_BASE = window.RAZVLEKIS_API_BASE || '/api';

const api = {
  // POST /api/geocode    body: { address }
  geocode: (address) =>
    apiFetch('/geocode', { method: 'POST', body: { address } }),

  // GET  /api/places?lat=&lng=&q=&category=&sort=&filters=open,wifi&limit=&offset=
  listPlaces: (params) =>
    apiFetch('/places' + buildQs(params)),

  // POST /api/places/{id}/save     DELETE /api/places/{id}/save
  toggleSave: (placeId, save) =>
    apiFetch(`/places/${encodeURIComponent(placeId)}/save`, {
      method: save ? 'POST' : 'DELETE',
    }),

  // POST /api/chat       body: { message, history, context }
  chat: (payload) =>
    apiFetch('/chat', { method: 'POST', body: payload }),
};

async function apiFetch(path, { method = 'GET', body } = {}){
  const headers = { Accept: 'application/json' };
  let initBody;
  if (body !== undefined){
    headers['Content-Type'] = 'application/json';
    initBody = JSON.stringify(body);
  }
  const res = await fetch(API_BASE + path, { method, headers, body: initBody, credentials: 'same-origin' });
  if (!res.ok){
    const text = await res.text().catch(()=> res.statusText);
    throw new Error(`API ${method} ${path} → ${res.status}: ${text}`);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
}

function buildQs(o){
  if (!o) return '';
  const parts = [];
  for (const k in o){
    const v = o[k];
    if (v === undefined || v === null || v === '') continue;
    if (Array.isArray(v)){
      if (!v.length) continue;
      parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v.join(',')));
    } else {
      parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    }
  }
  return parts.length ? '?' + parts.join('&') : '';
}

/* ════════════════════════════════════════════════════════════
   STATE
   ════════════════════════════════════════════════════════════ */
const state = {
  address: '',
  lat: null, lng: null,
  q: '',
  category: 'all',
  sort: 'near',
  filters: [],
  places: [],
};
let inFlight = null;   // AbortController for outstanding /places request

/* ════════════════════════════════════════════════════════════
   LANDING ⇄ RESULTS
   ════════════════════════════════════════════════════════════ */
const landingEl = document.getElementById('landing');
const resultsEl = document.getElementById('results');
const mainSearch = document.getElementById('mainSearch');
const inlineSearch = document.getElementById('inlineSearch');
const aiFab = document.getElementById('aiFab');

function doSearch(q){
  q = (q || '').trim();
  if (!q) q = 'Москва, центр';
  state.address = q;
  inlineSearch.value = q;

  landingEl.classList.add('dismissed');

  setTimeout(async ()=>{
    landingEl.style.display = 'none';
    resultsEl.classList.add('on');
    aiFab.style.display = 'flex';
    window.scrollTo({top:0});

    // 1) Geocode the address (failure is non-fatal — backend may accept text)
    try {
      const g = await api.geocode(q);
      if (g && typeof g.lat === 'number' && typeof g.lng === 'number'){
        state.lat = g.lat; state.lng = g.lng;
        if (g.label) state.address = g.label;
      }
    } catch (err){
      console.warn('[geocode] failed, will pass raw address to /places', err);
    }

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

mainSearch.addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch(e.target.value);
});
document.querySelectorAll('#suggests .chip').forEach(b =>
  b.addEventListener('click', ()=> { mainSearch.value = b.dataset.q; doSearch(b.dataset.q); })
);
inlineSearch.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    state.q = e.target.value.trim();
    fetchAndRender();
  }
});

/* ════════════════════════════════════════════════════════════
   FETCH + RENDER
   ════════════════════════════════════════════════════════════ */
async function fetchAndRender(){
  // Cancel any in-flight request
  if (inFlight) inFlight.abort();
  inFlight = new AbortController();

  const grid = document.getElementById('grid');
  grid.setAttribute('aria-busy', 'true');

  const params = {
    lat: state.lat, lng: state.lng,
    address: state.lat == null ? state.address : undefined,
    q: state.q,
    category: state.category,
    sort: state.sort,
    filters: state.filters,
  };

  let data;
  try {
    data = await api.listPlaces(params);
  } catch (err){
    console.warn('[/places] failed', err);
    state.places = [];
    renderError(err);
    grid.removeAttribute('aria-busy');
    return;
  }

  const places = (data.places || []).map(p => ({
    ...p,
    category: p.category || p.address || '',
    image_url: p.image_url || null,
  }));
  state.places = places;
  renderGrid(places);
  if (data.categories) renderCategories(data.categories);
  document.getElementById('countNum').textContent = data.total != null ? data.total : places.length;
  grid.removeAttribute('aria-busy');
}

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
  places.forEach((p, i)=> grid.appendChild(buildCard(p, i)));
}

function renderCategories(cats){
  const tabs = document.getElementById('tabs');
  if (!cats || !cats.length) return;
  const previous = state.category;
  tabs.innerHTML = '';
  cats.forEach(cat => {
    const btn = document.createElement('button');
    btn.className = 'tab' + (cat.id === previous ? ' on' : '');
    btn.dataset.cat = cat.id;
    btn.innerHTML = `${cat.label}<span class="count">${cat.count ?? 0}</span>`;
    btn.addEventListener('click', () => {
      state.category = cat.id;
      tabs.querySelectorAll('.tab').forEach(x => x.classList.remove('on'));
      btn.classList.add('on');
      fetchAndRender();
    });
    tabs.appendChild(btn);
  });
}

function renderError(err){
  const grid = document.getElementById('grid');
  grid.innerHTML = `<div class="empty-state">Не удалось загрузить места. ${(err && err.message) || ''}</div>`;
}

/* ════════════════════════════════════════════════════════════
   CARD
   ════════════════════════════════════════════════════════════ */
function buildCard(p, i){
  const c = document.createElement('a');
  c.className = 'card' + (p.image_url ? '' : ' no-photo');
  c.dataset.id = p.id;
  c.href = `https://2gis.ru/moscow/firm/${encodeURIComponent(p.id)}`;
  c.target = '_blank';
  c.rel = 'noopener';
  c.style.textDecoration = 'none';
  c.style.color = 'inherit';

  const distance = p.distance_label || (p.distance_m != null ? formatDistance(p.distance_m) : '');
  const openLabel = 'is_open' in p ? (p.is_open ? 'Открыто' : 'Закрыто') : null;
  const ratingHtml = p.rating != null ? `<span class="rating"><span class="star">★</span>${(+p.rating).toFixed(1)}</span><span class="dot-sep"></span>` : '';
  const priceHtml  = p.price ? `<span class="dot-sep"></span><span class="price"><b>${esc(p.price)}</b></span>` : '';
  const saveBtn = `
    <button class="card-save${p.saved ? ' saved' : ''}" aria-label="Сохранить" onclick="onSaveClick(event, this)">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="${p.saved ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
      </svg>
    </button>`;

  if (p.image_url){
    c.innerHTML = `
      <img class="card-img" src="${esc(p.image_url)}" alt="${esc(p.name)}" loading="lazy"
           onerror="this.parentElement.classList.add('no-photo'); this.outerHTML = makeNoPhoto('${esc(p.name).replace(/'/g,'\\\'')}')">
      <div class="card-top">
        <span class="badge-glass">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 0-8 8c0 6 8 12 8 12s8-6 8-12a8 8 0 0 0-8-8z"/></svg>
          ${esc(distance)}
        </span>
        ${openLabel != null ? `<span class="badge-glass">${openLabel}</span>` : ''}
        ${saveBtn}
      </div>
      <div class="card-foot">
        <div class="card-name">${esc(p.name)}</div>
        <div class="card-meta">
          ${ratingHtml}
          <span class="cat">${esc(p.category || '')}</span>
          ${priceHtml}
        </div>
      </div>`;
  } else {
    c.innerHTML = noPhotoMarkup(p, distance, openLabel, saveBtn, ratingHtml, priceHtml);
  }

  setTimeout(()=> c.classList.add('show'), 70 + i*55);
  return c;
}

function noPhotoMarkup(p, distance, openLabel, saveBtn, ratingHtml, priceHtml){
  const letter = (p.name.match(/«([^»]+)»/)?.[1] || p.name).trim().charAt(0).toUpperCase();
  return `
    <div class="card-bg"></div>
    <div class="card-top">
      <span class="badge-glass">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 0 0-8 8c0 6 8 12 8 12s8-6 8-12a8 8 0 0 0-8-8z"/></svg>
        ${esc(distance)}
      </span>
      ${openLabel != null ? `<span class="badge-glass">${openLabel}</span>` : ''}
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
        <span class="cat">${esc(p.category || '')}</span>
        ${priceHtml}
      </div>
    </div>`;
}
window.makeNoPhoto = (name)=> `<div class="card-bg"></div><div class="monogram"><span class="letter">${(name||'').charAt(0)}</span><span class="strap">Без фото</span></div>`;

function esc(s){
  return String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function formatDistance(m){
  if (m == null) return '';
  return m < 1000 ? `${Math.round(m)} м` : `${(m/1000).toFixed(1)} км`;
}

async function onSaveClick(e, el){
  e.preventDefault();
  e.stopPropagation();
  const card = el.closest('.card');
  const id = card && card.dataset.id;
  if (!id) return;
  const willSave = !el.classList.contains('saved');
  // optimistic UI
  el.classList.toggle('saved', willSave);
  el.querySelector('svg').setAttribute('fill', willSave ? 'currentColor' : 'none');
  try {
    await api.toggleSave(id, willSave);
  } catch (err){
    console.warn('[/places/{id}/save] failed', err);
    // revert if the backend rejected
    el.classList.toggle('saved', !willSave);
    el.querySelector('svg').setAttribute('fill', !willSave ? 'currentColor' : 'none');
  }
}

/* ════════════════════════════════════════════════════════════
   TABS
   ════════════════════════════════════════════════════════════ */
// Static tabs in HTML — wire them up; will be re-rendered (and re-bound) when /places returns categories.
document.querySelectorAll('#tabs .tab').forEach(t => t.addEventListener('click', ()=>{
  document.querySelectorAll('#tabs .tab').forEach(x => x.classList.remove('on'));
  t.classList.add('on');
  state.category = t.dataset.cat || 'all';
  fetchAndRender();
}));

/* ════════════════════════════════════════════════════════════
   FILTER
   ════════════════════════════════════════════════════════════ */
function toggleFilter(e){
  if(e) e.stopPropagation();
  const drop = document.getElementById('filterDrop');
  const btn  = document.getElementById('filterBtn');
  const open = drop.classList.toggle('on');
  btn.classList.toggle('open', open);
  if (open){
    setTimeout(()=> document.addEventListener('click', closeFilterOnce), 10);
  }
}
function closeFilterOnce(e){
  if (e && e.target.closest('#filterDrop')) {
    document.addEventListener('click', closeFilterOnce, { once:true });
    return;
  }
  document.getElementById('filterDrop').classList.remove('on');
  document.getElementById('filterBtn').classList.remove('open');
}

/* Single-select sort items */
document.querySelectorAll('#filterDrop .drop-item[data-sort]').forEach(item=>{
  item.addEventListener('click', e => {
    e.stopPropagation();
    document.querySelectorAll('#filterDrop .drop-item[data-sort]').forEach(x => x.classList.remove('on'));
    item.classList.add('on');
    state.sort = item.dataset.sort;
    syncApplied();
    fetchAndRender();
  });
});
/* Multi-select filter toggles */
document.querySelectorAll('#filterDrop .drop-item.filter-toggle').forEach(item=>{
  item.addEventListener('click', e => {
    e.stopPropagation();
    item.classList.toggle('on');
    state.filters = [...document.querySelectorAll('#filterDrop .drop-item.filter-toggle.on')].map(x => x.dataset.filter);
    syncApplied();
    fetchAndRender();
  });
});

function syncApplied(){
  const row = document.getElementById('appliedRow');
  const sortItem = document.querySelector('#filterDrop .drop-item[data-sort].on');
  const filterItems = [...document.querySelectorAll('#filterDrop .drop-item.filter-toggle.on')];
  const pills = [];
  if (sortItem){
    pills.push({ key: 'sort', label: sortItem.textContent.trim() });
  }
  filterItems.forEach(f => pills.push({ key: f.dataset.filter, label: f.textContent.trim(), filter: true }));

  // Render pills
  const container = document.getElementById('appliedPills');
  container.innerHTML = '';
  pills.forEach(p => {
    const el = document.createElement('span');
    el.className = 'pill' + (p.filter ? ' is-filter' : '');
    el.innerHTML = `<span>${p.label}</span><button aria-label="Сбросить"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;
    el.querySelector('button').addEventListener('click', () => {
      if (p.filter){
        document.querySelector(`#filterDrop .drop-item[data-filter="${p.key}"]`).classList.remove('on');
        state.filters = state.filters.filter(f => f !== p.key);
      } else {
        document.querySelectorAll('#filterDrop .drop-item[data-sort]').forEach(x => x.classList.remove('on'));
        state.sort = null;
      }
      syncApplied();
      fetchAndRender();
    });
    container.appendChild(el);
  });

  // Badge count
  const count = pills.length;
  const badge = document.getElementById('filterBadge');
  badge.textContent = String(count);
  badge.style.display = count ? 'flex' : 'none';
}

function clearSort(){
  document.querySelectorAll('#filterDrop .drop-item').forEach(x => x.classList.remove('on'));
  state.sort = null;
  state.filters = [];
  syncApplied();
  fetchAndRender();
}
// initial sync of applied pills
syncApplied();
/* Dynamically align tabs/filter rows to where the search bar starts */
function syncBrandOffset(){
  const brand = document.querySelector('.header .brand-sm');
  const header = document.querySelector('.header');
  if (!brand || !header) return;
  const headerLeft = header.getBoundingClientRect().left;
  const brandRight = brand.getBoundingClientRect().right;
  // Add the 10px gap defined in .header-row
  const offset = (brandRight - headerLeft) + 10;
  header.style.setProperty('--brand-offset', offset + 'px');
}
window.addEventListener('resize', syncBrandOffset);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(syncBrandOffset);
requestAnimationFrame(syncBrandOffset);

/* ════════════════════════════════════════════════════════════
   AI
   ════════════════════════════════════════════════════════════ */
const aiHistory = [];   // [{ role: 'user'|'assistant', content: '...' }, ...]

function toggleAI(){
  document.getElementById('aiPanel').classList.toggle('on');
}
function quickAsk(b){
  document.getElementById('aiInput').value = b.textContent;
  sendAI();
}
async function sendAI(){
  const inp = document.getElementById('aiInput');
  const q = inp.value.trim();
  if (!q) return;
  inp.value = '';

  const m = document.getElementById('aiMsgs');
  const u = document.createElement('div'); u.className = 'ai-bubble usr'; u.textContent = q; m.appendChild(u);
  const b = document.createElement('div'); b.className = 'ai-bubble bot'; b.textContent = '…'; m.appendChild(b);
  m.scrollTop = m.scrollHeight;

  aiHistory.push({ role: 'user', content: q });

  const payload = {
    message: q,
    history: aiHistory.slice(0, -1),         // everything before the just-pushed user message
    context: {
      address: state.address || null,
      lat: state.lat, lng: state.lng,
      category: state.category,
      sort: state.sort,
      filters: state.filters,
      places: state.places.map(p => ({
        name: p.name,
        address: p.address,
        category: p.category,
        distance_label: p.distance_label,
      })),
    },
  };

  let reply;
  try {
    const data = await api.chat(payload);
    reply = data && data.reply ? data.reply : '…';
  } catch (err){
    console.warn('[/chat] failed', err);
    b.textContent = 'Не удалось получить ответ от ассистента. ' + ((err && err.message) || 'Попробуйте позже.');
    return;
  }

  b.textContent = reply;
  aiHistory.push({ role: 'assistant', content: reply });
  m.scrollTop = m.scrollHeight;
}
