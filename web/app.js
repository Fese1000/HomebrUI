const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const key = i => i.kind + ':' + i.name;

// ---------- Sprache ----------
// Startwerte kommen vom Server schon im <html>-Tag; so springt beim Laden nichts um
const H0 = document.documentElement;
let config = {lang: H0.lang || 'en', theme: H0.dataset.theme || 'auto', ignore: [], stale_days: 180};
const t = (k, ...a) => {
  let s = (I18N[config.lang] || {})[k] ?? I18N.en[k] ?? k;
  a.forEach((v, i) => { s = s.split('{' + i + '}').join(v); });
  return s;
};
const loc = () => LOCALES[config.lang] || 'en-GB';
const num = n => Number(n).toLocaleString(loc());
const fmt = b => !b ? '0 KB' : b > 1e9 ? (b / 1e9).toFixed(2) + ' GB' : b > 1e6 ? (b / 1e6).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1e3)) + ' KB';
const day = ts => ts ? new Date(ts * 1e3).toLocaleDateString(loc()) : '–';
const kind = k => t('k_' + k);

const THEMES = [['auto', 's_auto'], ['light', 's_light'], ['dark', 's_dark'], ['solarized-light', 'Solarized Light'], ['solarized-dark', 'Solarized Dark'],
  ['gruvbox-light', 'Gruvbox Light'], ['gruvbox-dark', 'Gruvbox Dark'], ['nord', 'Nord'], ['dracula', 'Dracula'], ['monokai', 'Monokai'],
  ['tokyo-night', 'Tokyo Night'], ['one-dark', 'One Dark'], ['catppuccin-latte', 'Catppuccin Latte'], ['catppuccin-mocha', 'Catppuccin Mocha']];

function applyConfig() {
  const h = document.documentElement;
  h.dataset.theme = config.theme;
  h.lang = config.lang;
  h.dir = config.lang == 'ar' ? 'rtl' : 'ltr';
  for (const k of ['reload', 'settings', 'quit']) { $('#' + k).title = t(k); $('#' + k).setAttribute('aria-label', t(k)); }
  $('#clr').textContent = t('clear'); $('#mark').textContent = t('f_mark'); $('#ign').textContent = t('f_ign'); $('#del').textContent = t('f_del');
  $('#jobcancel').textContent = t('job_cancel');
  $('#jobtoggle').textContent = $('#jobs').classList.contains('open') ? t('shut') : t('open');
  if (!curJob) $('#jobtitle').textContent = t('jobs');
}

let data = null, view = 'packages', tab = 'candidates', sortK = 'name', sortD = 1, sel = new Set(), q = '', bfText = '', bfDiff = null;
let curJob = null, polling = false, seen = 0, lastStatus = {}, askShown = false;

async function api(path, body) {
  const opt = body === undefined ? {} : {method: 'POST', headers: {'X-BrewUI': '1'}, body: JSON.stringify(body)};
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 60000);
  let r;
  try { r = await fetch(path, {...opt, signal: ctl.signal}); }
  catch (e) { throw new Error(t('err_server')); }  // Server beendet, Netz weg oder Seite war im Ruhezustand
  finally { clearTimeout(timer); }
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
const act = body => api('/api/action', body).then(r => { watch(r.job); return r; }).catch(e => alert(e.message));

// ---------- Daten & Navigation ----------
async function load(refresh = true) {
  $('#view').innerHTML = `<div class="empty">${t('loading')}</div>`;
  try {
    data = await api('/api/data' + (refresh ? '?refresh=1' : ''));
    config = data.config; applyConfig(); sel.clear(); render();
  } catch (e) { $('#view').innerHTML = `<div class="empty">${esc(t('err', e.message))}</div>`; }
}

function render() {
  if (!data) return;
  const out = data.items.filter(i => i.outdated).length, cand = data.items.filter(i => i.reasons.length).length;
  const nav = [['packages', 'nav_pk', cand], ['updates', 'nav_up', out], ['search', 'nav_in'], ['services', 'nav_sv'], ['taps', 'nav_tp'],
    ['maintenance', 'nav_mt'], ['brewfile', 'nav_bf'], ['history', 'nav_hs']];
  $('#nav').innerHTML = nav.map(([k, l, n]) => `<button data-view="${k}" class="${k == view ? 'on' : ''}">${t(l)}${n ? `<span class="n">${n}</span>` : ''}</button>`).join('');
  ({packages: vPackages, updates: vUpdates, search: vSearch, services: vServices, taps: vTaps, maintenance: vMaintenance, brewfile: vBrewfile, history: vHistory})[view]();
  foot();
}

const rKey = r => ({'app-missing': 'app'}[r[0]] || r[0]);
const reasonText = r => t('y_' + rKey(r), r[1]);
const reasonLabel = r => t('rl_' + rKey(r));

// ---------- Pakete ----------
const staleDays = i => i.last_used ? (Date.now() / 1e3 - i.last_used) / 86400 : null;
function vPackages() {
  const items = data.items, cand = items.filter(i => i.reasons.length);
  const stale = items.filter(i => i.on_request && staleDays(i) > data.stale_days);
  const top = [...items].sort((a, b) => b.size - a.size).slice(0, 12), max = top[0]?.size || 1;
  const tabs = [['all', t('tab_all', items.length)], ['mine', t('tab_mine', items.filter(i => i.on_request).length)], ['stale', t('tab_stale', stale.length)], ['candidates', t('tab_cand', cand.length)]];
  let rows = items.filter(i => tab == 'candidates' ? i.reasons.length : tab == 'stale' ? stale.includes(i) : tab == 'mine' ? i.on_request : true)
    .filter(i => !q || (i.name + ' ' + i.desc).toLowerCase().includes(q));
  rows.sort((a, b) => { let x = a[sortK], y = b[sortK]; return (typeof x == 'string' ? x.localeCompare(y) : (x || 0) - (y || 0)) * sortD; });
  const th = (k, l, c = '') => `<th data-k="${k}" class="${c}">${l}${sortK == k ? (sortD > 0 ? ' ▲' : ' ▼') : ''}</th>`;
  $('#view').innerHTML = `
  <div class="numbers">${[[num(items.length), t('st_total')], [num(items.filter(i => i.kind == 'formula').length), t('st_formulae')], [num(items.filter(i => i.kind == 'cask').length), t('st_casks')],
    [num(cand.length), t('st_cand'), 1], [fmt(cand.reduce((a, i) => a + i.size, 0)), t('st_space'), 1], [fmt(items.reduce((a, i) => a + i.size, 0)), t('st_size')]]
    .map(([n, l, h]) => `<div class="${h && cand.length ? 'hl' : ''}"><b>${n}</b><span>${l}</span></div>`).join('')}</div>
  <details class="card"><summary>${t('space')}</summary><div class="bars">${top.map(i =>
    `<div class="b"><span class="lbl">${esc(i.name)}</span><span class="fill" style="width:${Math.max(2, i.size / max * 55)}%"></span><span class="sub">${fmt(i.size)}</span></div>`).join('')}</div></details>
  <div class="bar"><input type="search" id="q" placeholder="${t('search_ph')}" value="${esc(q)}">
   <div class="seg">${tabs.map(([k, l]) => `<button class="${k == tab ? 'on' : ''}" data-tab="${k}">${l}</button>`).join('')}</div></div>
  ${tab == 'stale' ? `<p class="sub">${t('stale_note', data.stale_days)}</p>` : ''}
  ${rows.length ? `<table><thead><tr><th></th>${th('name', t('c_name'))}${th('kind', t('c_type'))}${th('version', t('c_version'))}${th('size', t('c_size'), 'num')}${th('last_used', t('c_last'))}${th('installed_at', t('c_inst'))}<th>${t('c_status')}</th></tr></thead><tbody>
  ${rows.map(i => `<tr class="${i.reasons.length ? 'flag' : ''}"><td><input type="checkbox" data-sel="${esc(key(i))}" ${sel.has(key(i)) ? 'checked' : ''}></td>
   <td><div class="name" data-detail="${esc(key(i))}">${esc(i.name)}</div><div class="desc">${esc(i.desc)}</div>${i.reasons.map(r => `<div class="why">${esc(reasonText(r))}</div>`).join('')}</td>
   <td>${kind(i.kind)}</td><td>${esc(i.version)}</td><td class="num">${fmt(i.size)}</td><td>${day(i.last_used)}</td><td>${day(i.installed_at)}</td>
   <td>${i.reasons.map(r => `<span class="tag r">${reasonLabel(r)}</span>`).join('')}<span class="tag">${i.on_request ? t('t_byme') : t('t_dep')}</span>
   ${i.used_by.length ? `<span class="tag link" data-usedby="${esc(key(i))}" title="${esc(i.used_by.join(', '))}">${t('t_usedby', i.used_by.length)}</span>` : ''}${i.outdated ? `<span class="tag ok">${t('t_update')}</span>` : ''}${i.pinned ? `<span class="tag">${t('t_pinned')}</span>` : ''}${i.ignored ? `<span class="tag">${t('t_ignored')}</span>` : ''}</td></tr>`).join('')}
  </tbody></table>` : `<div class="empty">${tab == 'candidates' ? t('e_cand') : t('e_none')}</div>`}`;
}

function foot() {
  const s = data ? data.items.filter(i => sel.has(key(i))) : [];
  $('#foot').classList.toggle('show', s.length > 0 && view == 'packages');
  $('#cnt').textContent = t('f_sel', s.length);
  $('#sz').textContent = t('f_free', fmt(s.reduce((a, i) => a + i.size, 0)));
}

async function uninstallDialog(items) {
  const formulae = items.filter(i => i.kind == 'formula');
  const pre = formulae.length ? await api('/api/preview-uninstall', {items: formulae}) : {also: [], blocked: {}};
  const ok = items.filter(i => !pre.blocked[i.name]);
  const dlg = $('#dlg');
  dlg.innerHTML = `<h3>${t('u_title')}</h3><ul>${ok.map(i => `<li>${esc(i.name)} <span class="sub">(${kind(i.kind)})</span></li>`).join('')}</ul>
   ${Object.keys(pre.blocked).length ? `<p class="why">${t('u_blocked')}</p><ul>${Object.entries(pre.blocked).map(([n, u]) => `<li>${esc(n)} <span class="sub">← ${esc(u.join(', '))}</span></li>`).join('')}</ul>` : ''}
   ${pre.also.length ? `<label><input type="checkbox" id="alsoChk" checked> ${t('u_also')}</label><ul>${pre.also.map(n => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}
   <p class="sub">${t('u_hint')}</p>
   <div class="actions"><button class="btn" value="x">${t('cancel')}</button><button class="btn danger" id="go" ${ok.length ? '' : 'disabled'}>${t('u_go')}</button></div>`;
  dlg.onclick = null; dlg.showModal();
  dlg.querySelector('[value=x]').onclick = () => dlg.close();
  $('#go').onclick = () => { act({action: 'uninstall', items: ok.map(i => ({kind: i.kind, name: i.name})), also: $('#alsoChk')?.checked ? pre.also : []}); dlg.close(); sel.clear(); };
}

// Liste der Pakete, die dieses Paket brauchen; ein Klick auf einen Namen öffnet dessen Details
function usedByDialog(k) {
  const i = data.items.find(x => key(x) == k), dlg = $('#dlg');
  const byName = Object.fromEntries(data.items.filter(x => x.kind == 'formula').map(x => [x.name, x]));
  dlg.innerHTML = `<h3>${esc(i.name)} <span class="sub">${t('d_neededby')} (${i.used_by.length})</span></h3>
   <table><tbody>${i.used_by.map(n => `<tr><td><div class="name" data-open="${esc(n)}">${esc(n)}</div><div class="desc">${esc(byName[n]?.desc || '')}</div></td>
    <td><span class="tag">${byName[n]?.on_request ? t('t_byme') : t('t_dep')}</span></td></tr>`).join('')}</tbody></table>
   <div class="actions"><button class="btn" data-a="x">${t('close')}</button></div>`;
  dlg.showModal();
  dlg.onclick = e => {
    const n = e.target.dataset.open;
    if (n && byName[n]) { dlg.close(); detailDialog(key(byName[n])); }
    else if (e.target.dataset.a == 'x') dlg.close();
  };
}

function detailDialog(k) {
  const i = data.items.find(x => key(x) == k), dlg = $('#dlg');
  const list = a => a.length ? a.map(n => `<code>${esc(n)}</code>`).join(' ') : `<span class="sub">${t('d_none')}</span>`;
  dlg.innerHTML = `<h3>${esc(i.name)} <span class="sub">${kind(i.kind)} ${esc(i.version)}</span></h3><p>${esc(i.desc)}</p>
   ${i.homepage ? `<p><a href="${esc(i.homepage)}" target="_blank" rel="noopener">${esc(i.homepage)}</a></p>` : ''}
   <p><b>${t('c_size')}:</b> ${fmt(i.size)} · <b>${t('c_last')}:</b> ${day(i.last_used)} · <b>${t('c_inst')}:</b> ${day(i.installed_at)}</p>
   <p><b>${t('d_needs')}:</b> ${list(i.deps)}</p><p><b>${t('d_neededby')}:</b> ${list(i.used_by)}</p>
   ${i.reasons.map(r => `<p class="why">${esc(reasonText(r))}</p>`).join('')}
   <div class="actions">${i.kind == 'formula' && !i.on_request ? `<button class="btn" data-a="mark">${t('f_mark')}</button>` : ''}
    ${i.kind == 'formula' ? `<button class="btn" data-a="pin">${i.pinned ? t('d_unpin') : t('d_pin')}</button>` : ''}
    <button class="btn" data-a="ign">${i.ignored ? t('d_unign') : t('f_ign')}</button>
    <button class="btn danger" data-a="del">${t('f_del')}</button><button class="btn" data-a="x">${t('close')}</button></div>`;
  dlg.showModal();
  dlg.onclick = e => {
    const a = e.target.dataset.a; if (!a) return;
    dlg.close();
    if (a == 'mark') act({action: 'mark_request', name: i.name});
    if (a == 'pin') act({action: i.pinned ? 'unpin' : 'pin', name: i.name});
    if (a == 'ign') toggleIgnore([i.name]);
    if (a == 'del') uninstallDialog([i]);
  };
}

async function toggleIgnore(names) {
  const ig = new Set(config.ignore);
  names.forEach(n => ig.has(n) ? ig.delete(n) : ig.add(n));
  await api('/api/config', {ignore: [...ig]});
  load();
}

// ---------- Updates ----------
function vUpdates() {
  const out = data.items.filter(i => i.outdated);
  $('#view').innerHTML = `<div class="bar"><button class="btn" data-a="update">${t('up_update')}</button>
   <button class="btn" data-a="upgrade-dry">${t('up_dry')}</button><button class="btn on" data-a="upgrade-all" ${out.length ? '' : 'disabled'}>${t('up_all')}</button></div>
   <p class="sub">${t('up_note')}</p>
   ${out.length ? `<table><thead><tr><th></th><th>${t('c_name')}</th><th>${t('c_type')}</th><th>${t('c_inst')}</th><th>${t('c_new')}</th><th></th></tr></thead><tbody>${out.map(i => `<tr><td></td><td><div class="name" data-detail="${esc(key(i))}">${esc(i.name)}</div></td><td>${kind(i.kind)}</td><td>${esc(i.version)}</td><td>${esc(i.new_version)}</td>
   <td>${i.pinned ? `<span class="tag">${t('t_pinned')}</span>` : `<button class="btn small" data-up="${esc(key(i))}">${t('up_upgrade')}</button>`}</td></tr>`).join('')}</tbody></table>` : `<div class="empty">${t('up_ok')}</div>`}`;
}

// ---------- Installieren: Katalog zum Stöbern ----------
let br = {kind: 'all', cat: '', q: '', sort: 'pop', newOnly: false, items: [], total: 0, cats: null, page: 0, err: ''}, brSeq = 0, brTimer;
async function fetchCatalog(append = false) {
  const id = ++brSeq;
  const p = new URLSearchParams({kind: br.kind, cat: br.cat, q: br.q, sort: br.sort, page: append ? br.page + 1 : 0, new: br.newOnly ? 1 : 0});
  try {
    const r = await api('/api/catalog?' + p);
    if (id !== brSeq) return;
    if (r.loading) { br.cats = null; if (view == 'search') $('#blist').innerHTML = `<div class="empty">${t('in_loading')}</div>`; setTimeout(() => { if (id === brSeq && view == 'search') fetchCatalog(append); }, 1500); return; }
    if (r.error) throw new Error(r.error);
    br.items = append ? br.items.concat(r.items) : r.items; br.total = r.total; br.cats = r.cats; br.page = r.page; br.err = ''; br.retried = false;
  } catch (e) {
    if (id !== brSeq) return;
    br.err = e.message == 'offline' ? t('err_offline') : e.message;
    if (!append && view == 'search' && !br.retried) { br.retried = true; setTimeout(() => { if (id === brSeq && view == 'search') fetchCatalog(); }, 2000); }
  }
  if (view == 'search') drawBrowse();
}
function vSearch() {
  $('#view').innerHTML = `<div class="bar"><input type="search" id="bq" placeholder="${t('in_ph')}" value="${esc(br.q)}">
   <div class="seg">${[['all', t('in_all')], ['formula', t('in_formulae')], ['cask', t('in_apps')]].map(([k, l]) => `<button data-bk="${k}" class="${br.kind == k ? 'on' : ''}">${l}</button>`).join('')}</div>
   <select id="bs"><option value="pop" ${br.sort == 'pop' ? 'selected' : ''}>${t('in_pop')}</option><option value="name" ${br.sort == 'name' ? 'selected' : ''}>${t('in_name')}</option></select>
   <label><input type="checkbox" id="bn" ${br.newOnly ? 'checked' : ''}> ${t('in_new')}</label></div>
   <div class="cats" id="bcats"></div><div id="blist"></div>`;
  $('#bq').oninput = e => { br.q = e.target.value; br.cat = ''; clearTimeout(brTimer); brTimer = setTimeout(() => fetchCatalog(), 300); };
  $('#bs').onchange = e => { br.sort = e.target.value; fetchCatalog(); };
  $('#bn').onchange = e => { br.newOnly = e.target.checked; fetchCatalog(); };
  document.querySelectorAll('[data-bk]').forEach(b => b.onclick = () => { br.kind = b.dataset.bk; br.cat = ''; vSearch(); fetchCatalog(); });
  if (br.cats) drawBrowse(); else { $('#blist').innerHTML = `<div class="empty">${t('in_loading')}</div>`; fetchCatalog(); }
}
function drawBrowse() {
  if (br.err) { $('#blist').innerHTML = `<div class="empty">${esc(br.err)}<br><br><button class="btn" id="bretry">${t('in_retry')}</button></div>`; $('#bretry').onclick = () => { br.err = ''; $('#blist').innerHTML = `<div class="empty">${t('loading')}</div>`; fetchCatalog(); }; return; }
  const all = Object.values(br.cats).reduce((a, n) => a + n, 0);
  $('#bcats').innerHTML = `<button data-bc="" class="${br.cat == '' ? 'on' : ''}">${t('cat_all')}<span class="c">${num(all)}</span></button>` +
    Object.entries(br.cats).sort((a, b) => (a[0] == 'other') - (b[0] == 'other') || b[1] - a[1]).map(([c, n]) => `<button data-bc="${esc(c)}" class="${br.cat == c ? 'on' : ''}">${t('cat_' + c)}<span class="c">${num(n)}</span></button>`).join('');
  document.querySelectorAll('[data-bc]').forEach(b => b.onclick = () => { br.cat = b.dataset.bc; fetchCatalog(); });
  $('#blist').innerHTML = br.items.length ? `<table><tbody>${br.items.map(r => `<tr><td></td><td><div class="name"><a href="${esc(r.homepage || '#')}" target="_blank" rel="noopener">${esc(r.name)}</a>${r.title && r.title != r.name ? ` <span class="sub" style="font:13px -apple-system,sans-serif">${esc(r.title)}</span>` : ''}</div>
    <div class="desc">${esc(r.desc) || `<i>${t('in_nodesc')}</i>`}</div></td>
    <td><span class="tag">${r.kind == 'cask' ? t('in_app') : kind('formula')}</span>${r.deprecated ? `<span class="tag r">${t('in_deprecated')}</span>` : ''}<div class="sub" style="font-size:11.5px">${esc(r.version)}</div></td>
    <td class="num sub">${r.pop ? t('in_installs', num(r.pop)) : ''}</td>
    <td class="num">${r.installed ? `<span class="tag ok">${t('in_installed')}</span>` : `<button class="btn small on" data-inst="${r.kind}:${esc(r.name)}">${t('in_install')}</button>`}</td></tr>`).join('')}</tbody></table>
    <p class="sub" style="text-align:center">${t('in_count', num(br.items.length), num(br.total))}</p>
    ${br.items.length < br.total ? `<button class="btn more" id="bmore">${t('in_more')}</button>` : ''}` : `<div class="empty">${t('in_none')}</div>`;
  const m = $('#bmore'); if (m) m.onclick = () => { m.disabled = true; fetchCatalog(true); };
}

// ---------- Dienste, Taps, Wartung ----------
async function vServices() {
  $('#view').innerHTML = `<div class="empty">${t('loading')}</div>`;
  const s = (await api('/api/services')).services;
  if (view != 'services') return;
  $('#view').innerHTML = s.length ? `<table><thead><tr><th></th><th>${t('sv_service')}</th><th>${t('c_status')}</th><th>${t('sv_user')}</th><th></th></tr></thead><tbody>${s.map(x => `<tr><td></td><td class="name">${esc(x.name)}</td>
   <td><span class="tag ${x.status == 'started' ? 'ok' : x.status == 'error' ? 'bad' : ''}">${esc(x.status)}</span></td><td>${esc(x.user || '')}</td>
   <td class="row">${['start', 'stop', 'restart'].map(o => `<button class="btn small" data-svc="${o}:${esc(x.name)}">${t('sv_' + o)}</button>`).join('')}</td></tr>`).join('')}</tbody></table>`
    : `<div class="empty">${t('sv_none')}</div>`;
}
async function vTaps() {
  $('#view').innerHTML = `<div class="empty">${t('loading')}</div>`;
  const tp = (await api('/api/taps')).taps;
  if (view != 'taps') return;
  $('#view').innerHTML = `<form class="bar" id="tf"><input type="text" id="tq" placeholder="${t('tp_ph')}"><button class="btn on">${t('tp_add')}</button></form>
   <table><tbody>${tp.map(x => `<tr><td></td><td class="name">${esc(x)}</td><td class="num">${x.startsWith('homebrew/') ? `<span class="sub">${t('tp_official')}</span>` : `<button class="btn small" data-untap="${esc(x)}">${t('tp_remove')}</button>`}</td></tr>`).join('')}</tbody></table>`;
  $('#tf').onsubmit = e => { e.preventDefault(); const v = $('#tq').value.trim(); if (v) act({action: 'tap', name: v}); };
}
async function vMaintenance() {
  $('#view').innerHTML = `<div class="empty">${t('loading')}</div>`;
  const m = await api('/api/maintenance');
  if (view != 'maintenance') return;
  const b = (a, l, cls = '') => `<button class="btn ${cls}" data-m="${a}">${l}</button>`;
  $('#view').innerHTML = `<div class="numbers"><div><b>${fmt(m.cache_bytes)}</b><span>${t('m_cache')}</span></div><div><b>${esc(m.brew_version.replace('Homebrew ', ''))}</b><span>${t('m_version')}</span></div></div>
   <div class="card"><h2>${t('m_cleanup')}</h2><p class="sub">${t('m_cleanup_d')}</p><div class="row">${b('cleanup-dry', t('m_preview'))}${b('cleanup', t('m_cleanup'))}${b('cleanup-all', t('m_cleanup_all'))}</div></div>
   <div class="card"><h2>${t('m_auto')}</h2><div class="row">${b('autoremove-dry', t('m_preview'))}${b('autoremove', 'autoremove')}</div></div>
   <div class="card"><h2>${t('m_health')}</h2><div class="row">${b('doctor', 'brew doctor')}${b('update', 'brew update')}</div></div>`;
}

// ---------- Brewfile & Verlauf ----------
function vBrewfile() {
  const d = bfDiff;
  const lst = (title, o) => Object.entries(o).filter(([, v]) => v.length).map(([k, v]) => `<p><b>${title} (${k}):</b> ${v.map(n => `<code>${esc(n)}</code>`).join(' ')}</p>`).join('') || `<p class="sub">${t('b_nothing', title)}</p>`;
  $('#view').innerHTML = `<div class="card"><h2>${t('b_export')}</h2><p class="sub">${t('b_export_d')}</p><a class="btn" href="/api/brewfile" download="Brewfile">${t('b_dl')}</a></div>
   <div class="card"><h2>${t('b_import')}</h2><textarea id="bf" placeholder="${t('b_ph')}">${esc(bfText)}</textarea>
   <div class="row" style="margin-top:8px"><input type="file" id="bff"><button class="btn on" data-a="bfdiff">${t('b_compare')}</button></div>
   ${d ? `<div style="margin-top:12px">${lst(t('b_missing'), d.missing)}${lst(t('b_extra'), d.extra)}${d.unsupported ? `<p class="sub">${t('b_unsup', d.unsupported)}</p>` : ''}
   <button class="btn on" data-a="bfinstall">${t('b_install')}</button></div>` : ''}</div>`;
  $('#bff').onchange = async e => { bfText = await e.target.files[0].text(); $('#bf').value = bfText; };
}
async function vHistory() {
  $('#view').innerHTML = `<div class="empty">${t('loading')}</div>`;
  const h = (await api('/api/history')).history;
  if (view != 'history') return;
  $('#view').innerHTML = h.length ? `<table><thead><tr><th></th><th>${t('c_name')}</th><th>${t('c_type')}</th><th>${t('c_version')}</th><th>${t('h_when')}</th><th></th></tr></thead><tbody>${h.map(x => `<tr><td></td><td class="name">${esc(x.name)}</td><td>${kind(x.kind)}</td><td>${esc(x.version)}</td><td>${new Date(x.time * 1e3).toLocaleString(loc())}</td>
   <td class="num"><button class="btn small" data-inst="${x.kind}:${esc(x.name)}">${t('h_reinstall')}</button></td></tr>`).join('')}</tbody></table><p class="sub">${t('h_note')}</p>` : `<div class="empty">${t('h_none')}</div>`;
}

// ---------- Einstellungen ----------
function settingsDialog() {
  const dlg = $('#dlg');
  const opt = (v, l, cur) => `<option value="${v}" ${cur == v ? 'selected' : ''}>${esc(l)}</option>`;
  dlg.innerHTML = `<h3>${t('s_title')}</h3>
   <p><label>${t('s_lang')} <select id="sLang">${Object.entries(LANGS).map(([v, l]) => opt(v, l, config.lang)).join('')}</select></label></p>
   <p><label>${t('s_theme')} <select id="sTheme">${THEMES.map(([v, l]) => opt(v, l.startsWith('s_') ? t(l) : l, config.theme)).join('')}</select></label></p>
   <p><label>${t('s_stale1')} <input type="number" id="sStale" min="1" max="3650" value="${config.stale_days}" style="width:80px"> ${t('s_stale2')}</label></p>
   <p><b id="updVer"></b> <button class="btn" id="updCheck">${t('u_check')}</button> <button class="btn on" id="updGo" hidden>${t('u_install')}</button></p>
   <p class="sub" id="updMsg"></p>
    <p><b>${t('s_ignored')}</b></p>
   <div>${config.ignore.length ? config.ignore.map(n => `<span class="tag">${esc(n)} <a href="#" data-unign="${esc(n)}">×</a></span>`).join('') : `<span class="sub">${t('d_none')}</span>`}</div>
   <div class="actions"><button class="btn" data-a="x">${t('cancel')}</button><button class="btn on" data-a="save">${t('save')}</button></div>`;
  setupUpdate();
  $('#sTheme').onchange = e => { document.documentElement.dataset.theme = e.target.value; };  // Live-Vorschau
  dlg.showModal();
  dlg.onclick = async e => {
    if (e.target.dataset.unign) { e.preventDefault(); config.ignore = config.ignore.filter(n => n != e.target.dataset.unign); settingsDialog(); return; }
    const a = e.target.dataset.a; if (!a) return;
    dlg.close(); dlg.onclick = null;
    if (a == 'save') {
      config = await api('/api/config', {theme: $('#sTheme').value, lang: $('#sLang').value, stale_days: +$('#sStale').value, ignore: config.ignore});
      applyConfig(); await load();
    } else applyConfig();
  };
}

// Update-Bereich in den Einstellungen
async function setupUpdate() {
  const msg = $('#updMsg'), go = $('#updGo'), chk = $('#updCheck');
  let st = await api('/api/update/status').catch(() => null);
  if (!st) return;
  $('#updVer').textContent = st.current ? t('u_ver', st.current) : 'HomebrUI';
  if (!st.can_install) { chk.hidden = true; msg.textContent = t(st.reason == 'permission' ? 'u_perm' : 'u_src'); return; }
  const show = st => {
    if (st.stage == 'download') msg.textContent = t('u_dl', st.pct);
    else if (st.stage == 'install') msg.textContent = t('u_inst');
    else if (st.stage == 'restart') msg.textContent = t('u_restart');
    else if (st.stage == 'error') { msg.textContent = t('u_err', st.error); chk.disabled = false; go.disabled = false; return false; }
    return true;
  };
  const follow = async () => {
    chk.disabled = go.disabled = true;
    for (;;) {
      const s = await api('/api/update/status').catch(() => ({stage: 'restart'}));  // Server weg = Neustart läuft
      if (!show(s)) return;
      await new Promise(r => setTimeout(r, 500));
    }
  };
  if (['download', 'install', 'restart'].includes(st.stage)) return follow();
  chk.onclick = async () => {
    chk.disabled = true; msg.textContent = '…';
    try {
      const r = await api('/api/update/check', {});
      if (r.available) { msg.textContent = t('u_avail', r.latest); go.hidden = false; chk.hidden = true; }
      else msg.textContent = t('u_none');
    } catch (e) { msg.textContent = t('u_fail', e.message); }
    chk.disabled = false;
  };
  go.onclick = async () => {
    if (!confirm(t('u_install') + '?')) return;
    try { await api('/api/update/install', {}); follow(); } catch (e) { msg.textContent = t('u_err', e.message); }
  };
}

// ---------- Aufgaben (Live-Log, sudo-Passwort) ----------
function watch(id) { curJob = id; seen = 0; $('#joblog').textContent = ''; $('#jobs').classList.add('show', 'open'); $('#jobtoggle').textContent = t('shut'); poll(); }
async function poll() {
  if (polling) return; polling = true;
  try {
    for (;;) {
      const l = await api('/api/jobs');
      $('#joblist').innerHTML = l.jobs.slice(0, 8).map(j => `<button class="btn small ${j.id == curJob ? 'on' : ''}" data-job="${j.id}">#${j.id} ${esc(j.title.slice(0, 28))}</button>`).join('');
      const active = l.jobs.some(j => j.status == 'queued' || j.status == 'running');
      if (curJob) {
        const j = await api(`/api/jobs/${curJob}?since=${seen}`);
        seen += j.log.length;
        if (j.log.length) { const p = $('#joblog'); p.textContent += j.log.join('\n') + '\n'; p.scrollTop = p.scrollHeight; }
        $('#jobtitle').textContent = j.title;
        const st = $('#jobstate'); st.textContent = t('js_' + j.status);
        st.className = 'tag ' + (j.status == 'done' ? 'ok' : j.status == 'error' ? 'bad' : '');
        $('#jobcancel').hidden = !(j.status == 'queued' || j.status == 'running');
      }
      for (const j of l.jobs) {
        if (lastStatus[j.id] && lastStatus[j.id] != j.status && ['done', 'error', 'cancelled'].includes(j.status)) refreshAfterJob();
        lastStatus[j.id] = j.status;
      }
      if (l.prompt && !askShown) askPassword(l.prompt);
      if (!active && !l.prompt) break;
      await new Promise(r => setTimeout(r, 700));
    }
  } catch (e) { /* Server weg */ }
  polling = false;
}
let refreshTimer;
function refreshAfterJob() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => {
    data = await api('/api/data?refresh=1'); config = data.config; sel.clear();
    if (['packages', 'updates', 'services', 'taps', 'maintenance', 'history'].includes(view)) render();
  }, 400);
}
function askPassword(prompt) {
  askShown = true;
  const dlg = document.createElement('dialog');
  dlg.innerHTML = `<h3>${t('pw_title')}</h3><p>${t('pw_text')}<br><span class="sub">${esc(prompt)}</span></p>
   <form method="dialog"><input type="password" id="pw" autocomplete="off" style="width:100%" autofocus><p class="sub">${t('pw_note')}</p>
   <div class="actions"><button class="btn" value="cancel">${t('cancel')}</button><button class="btn on" value="ok">${t('ok')}</button></div></form>`;
  document.body.appendChild(dlg); dlg.showModal();
  dlg.addEventListener('close', async () => {
    const ok = dlg.returnValue == 'ok', pw = dlg.querySelector('#pw').value;
    dlg.remove();
    await api('/api/askpass/answer', ok ? {password: pw} : {cancel: true}).catch(() => {});
    askShown = false; poll();
  });
}

// ---------- Events ----------
document.addEventListener('click', async e => {
  const d = e.target.dataset;
  if (d.view) { view = d.view; render(); }
  else if (d.tab) { tab = d.tab; render(); }
  else if (d.detail) detailDialog(d.detail);
  else if (d.usedby) usedByDialog(d.usedby);
  else if (d.job) { curJob = +d.job; seen = 0; $('#joblog').textContent = ''; poll(); }
  else if (d.inst) { const [k, n] = d.inst.split(/:(.*)/s); act({action: 'install', kind: k, name: n}); }
  else if (d.svc) { const [o, n] = d.svc.split(/:(.*)/s); act({action: 'services', op: o, name: n}); }
  else if (d.untap) { if (confirm(t('tp_confirm', d.untap))) act({action: 'untap', name: d.untap}); }
  else if (d.up) { const [k, n] = d.up.split(/:(.*)/s); act({action: 'upgrade', items: [{kind: k, name: n}]}); }
  else if (d.a == 'update') act({action: 'update'});
  else if (d.a == 'upgrade-dry') act({action: 'upgrade', dry_run: true});
  else if (d.a == 'upgrade-all') { if (confirm(t('up_confirm'))) act({action: 'upgrade'}); }
  else if (d.a == 'bfdiff') { bfText = $('#bf').value; bfDiff = await api('/api/brewfile/diff', {text: bfText}); vBrewfile(); }
  else if (d.a == 'bfinstall') { if (confirm(t('b_confirm'))) act({action: 'bundle_install', text: bfText}); }
  else if (d.m) {
    const m = d.m;
    if (m == 'cleanup' && !confirm(t('m_c1'))) return;
    if (m == 'cleanup-all' && !confirm(t('m_c2'))) return;
    if (m == 'autoremove' && !confirm(t('m_c3'))) return;
    act({'cleanup-dry': {action: 'cleanup', dry_run: true}, cleanup: {action: 'cleanup'}, 'cleanup-all': {action: 'cleanup', prune_all: true},
      'autoremove-dry': {action: 'autoremove', dry_run: true}, autoremove: {action: 'autoremove'}, doctor: {action: 'doctor'}, update: {action: 'update'}}[m]);
  }
  const h = e.target.closest('th[data-k]');
  if (h) { sortD = sortK == h.dataset.k ? -sortD : 1; sortK = h.dataset.k; vPackages(); }
});
document.addEventListener('change', e => {
  const k = e.target.dataset.sel;
  if (k) { e.target.checked ? sel.add(k) : sel.delete(k); foot(); }
});
document.addEventListener('input', e => { if (e.target.id == 'q') { q = e.target.value.toLowerCase(); const p = e.target.selectionStart; vPackages(); const n = $('#q'); n.focus(); n.setSelectionRange(p, p); } });
$('#reload').onclick = () => load();
$('#settings').onclick = settingsDialog;
$('#quit').onclick = async () => { if (confirm(t('q_confirm'))) { await api('/api/quit', {}).catch(() => {}); document.body.innerHTML = `<div class="empty" style="grid-column:1/-1">${t('q_done')}</div>`; } };
$('#clr').onclick = () => { sel.clear(); render(); };
const selItems = () => data.items.filter(i => sel.has(key(i)));
$('#del').onclick = () => uninstallDialog(selItems());
$('#mark').onclick = () => selItems().filter(i => i.kind == 'formula' && !i.on_request).forEach(i => act({action: 'mark_request', name: i.name}));
$('#ign').onclick = () => toggleIgnore(selItems().map(i => i.name));
$('#jobhead').onclick = e => { if (e.target.id == 'jobcancel') return; const j = $('#jobs'); j.classList.toggle('open'); $('#jobtoggle').textContent = j.classList.contains('open') ? t('shut') : t('open'); };
$('#jobcancel').onclick = () => api('/api/cancel', {id: curJob});
// Beim Zurückkehren in den Tab/das Fenster: leere oder fehlgeschlagene Ansichten neu laden
const comeback = () => {
  if (document.visibilityState == 'hidden' || !data) return;
  if (view == 'search' && (br.err || !br.cats || !br.items.length)) { br.retried = false; vSearch(); fetchCatalog(); }
  else if (view == 'search' && br.cats) drawBrowse();
};
document.addEventListener('visibilitychange', comeback);
window.addEventListener('focus', comeback);
window.addEventListener('pageshow', comeback);
applyConfig();
load(false);
