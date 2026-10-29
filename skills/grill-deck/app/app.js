'use strict';
// grill-deck page: renders /api/state, posts answers and chat, and cuts the mic stream into utterances.

const $ = (s, el = document) => el.querySelector(s);
const ui = { open: new Set(), lastOpen: null, focus: null, vtabs: {}, vseen: {}, drafts: {}, timers: {}, asking: {}, needReason: {} };
let S = null;
let version = -1;

function store(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem('grill-deck:' + key));
    localStorage.setItem('grill-deck:' + key, JSON.stringify(value));
  } catch { return null; }
}

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'text') el.textContent = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) el.append(kid);
  return el;
}

const SVG = {
  web: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  code: '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/>',
  probe: '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/>',
  visual: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 15l3-3 3 3 4-4"/>',
  review: '<path d="M9 11l3 3 8-8"/><path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9"/>',
  chev: '<path d="M6 9l6 6 6-6"/>',
};
function icon(name, size = 16) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('aria-hidden', 'true');
  s.setAttribute('width', size); s.setAttribute('height', size);
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('fill', 'none');
  s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2');
  s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round');
  s.innerHTML = SVG[name];
  return s;
}

async function post(path, body, raw) {
  const r = await fetch(path, raw ? { method: 'POST', body, headers: { 'Content-Type': 'audio/wav' } }
    : { method: 'POST', body: JSON.stringify(body || {}), headers: { 'Content-Type': 'application/json' } });
  const out = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(out.error || r.statusText);
  return out;
}

// ------------------------------------------------------------------ state

// read the state now, so a click shows at once instead of on the next poll
async function refresh() {
  try {
    const s = await (await fetch('/api/state', { cache: 'no-store' })).json();
    if (s.version !== version) { version = s.version; S = s; render(); }
  } catch { /* the poll loop reports a dead server */ }
}

async function poll() {
  try {
    const r = await fetch('/api/state', { cache: 'no-store' });
    const s = await r.json();
    if (s.version !== version) { version = s.version; S = s; render(); }
    else { S.server = s.server; tick(); }
  } catch {
    $('#chat-state').className = 'chip bad';
    $('#chat-state').textContent = 'server down';
  }
  setTimeout(poll, 900);
}

const settledIds = () => new Set(S.decisions.filter(d => d.status === 'settled').map(d => d.id));
function frontier() {
  const done = settledIds();
  return S.decisions.filter(d => d.status !== 'settled' && (d.prereqs || []).every(p => done.has(p)));
}
const waitingFor = id => S.processes.some(p => p.state === 'running' && p.for === id && !['visual', 'review'].includes(p.kind));

function render() {
  const open = frontier();
  document.title = S.title + ' · grill deck';
  $('#title').textContent = S.title;
  $('#round').textContent = `round ${S.round} · ${open.filter(d => d.status !== 'answered').length} open`;
  $('#round-chip').textContent = `round ${S.round}`;
  const openCount = open.filter(d => d.status !== 'answered').length;
  $('#open-chip').textContent = `${openCount} open`;
  $('#open-chip').className = 'chip' + (openCount ? ' warn' : ' ok');
  renderDepth();
  const working = S.claude === 'working';
  $('#chat-state').className = 'chip ' + (!S.server.session ? 'warn' : working ? 'acc' : 'ok');
  $('#chat-state').replaceChildren(...(!S.server.session ? ['no session'] : working
    ? [h('span', { class: 'dot running live', style: 'background:var(--accent);box-shadow:none' }), 'working'] : ['waiting for you']));
  renderVoice();
  renderLedger();
  renderProcs();
  renderChat();
  // open questions first, answered-but-unsent below them; sent ones wait in the Settled section
  const rank = d => (d.status === 'answered' ? 1 : 0);
  renderQuestions(open.filter(d => !(d.status === 'answered' && d.sent)).sort((a, b) => rank(a) - rank(b)));
  renderDefaults(open);
  renderVisuals();
  paintSend();
}

function renderDepth() {
  const chip = $('#depth-chip');
  const dp = S.depth;
  chip.hidden = !dp;
  if (!dp) return;
  const b = S.budget || {};
  const parts = [{ full: 'full depth', rfc: 'design only', park: 'parked' }[dp.level] || dp.level];
  if (b.maxRounds) parts.push(`round ${S.round}/${b.maxRounds}`);
  if (b.maxProbes) parts.push(`research ${b.probes}/${b.maxProbes}`);
  const over = (b.maxRounds && S.round > b.maxRounds) || (b.maxProbes && b.probes > b.maxProbes);
  chip.className = 'chip' + (over ? ' bad' : '');
  chip.textContent = parts.join(' · ');
}

function renderDefaults(open) {
  const box = $('#defaults');
  const ds = open.filter(d => d.default && d.stake !== 'high' && d.status === 'open' && d.recommendedOption != null);
  box.hidden = ds.length < 2;
  if (box.hidden) return;
  box.replaceChildren(
    h('span', { class: 'dtext' }, h('b', { text: `${ds.length} low-stake defaults` }), ` · ${ds.map(d => d.id).join(', ')}`),
    h('button', {
      type: 'button', class: 'btn', text: `Accept all ${ds.length} recommendations`,
      onclick: async () => {
        try { await post('/api/defaults', { ids: ds.map(d => d.id) }); await refresh(); } catch (e) { alertLine(`Not sent: ${e.message}`); }
      },
    }));
}

function answerSummary(d) {
  const opts = d.options || [];
  const picked = (d.choices || []).filter(i => i < opts.length)
    .map(i => opts[i] + (i === d.recommendedOption ? ' (recommended)' : ''));
  const text = d.text ? (d.text.length > 90 ? d.text.slice(0, 90) + '…' : d.text) : '';
  return [picked.join(' · '), text].filter(Boolean).join(' — ');
}

function tick() {
  renderVoice();
  for (const el of document.querySelectorAll('[data-started]')) el.textContent = elapsed(el.dataset.started, el.dataset.ended);
}

function elapsed(start, end) {
  const s = Math.max(0, Math.round(((end ? +end : Date.now() / 1000)) - +start));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// ------------------------------------------------------------------ header

function renderVoice() {
  if (!S) return;
  const talk = S.transcript.filter(t => !t.sent);
  const heard = $('#heard');
  heard.replaceChildren();
  // only speech shows here: the live preview while talking, then the final text for a few seconds
  if (mic.speaking) heard.append(mic.live ? `“${mic.live}”` : h('span', { class: 'muted live', text: '…' }));
  else if (mic.final && Date.now() < mic.final.until) heard.append(`“${mic.final.text}”`);
  else if (mic.error && !mic.on) heard.append(h('span', { style: 'color:var(--bad)', text: `Mic not available: ${mic.error}` }));
  else {
    const last = S.transcript.at(-1);
    if (last?.dropped && !last.sent && S.server.now - last.at < 20) {
      heard.append(h('span', { class: 'muted', text: `“${last.text}” · ignored as ${last.dropped} ` }),
        h('button', { type: 'button', class: 'linkbtn', text: 'Send anyway', onclick: () => post('/api/keep', { id: last.id }).then(refresh).catch(e => alertLine(`Not sent: ${e.message}`)) }));
    }
  }
  const j = $('#judge');
  const p = S.pending || { state: 'idle' };
  j.replaceChildren();
  if (p.state === 'judging') j.append(h('span', { class: 'chip', text: 'Haiku is listening…' }));
  else if (p.state === 'countdown') {
    const secs = Math.max(0, Math.ceil(p.until - Date.now() / 1000));
    j.append(h('span', { style: 'color:var(--accent)', text: `Sending in ${secs} s` }),
      h('button', { type: 'button', class: 'btn', text: 'Undo', onclick: () => post('/api/undo') }));
  } else if (p.state === 'sending') j.append(h('span', { class: 'chip acc', text: 'sending…' }));
  else if (p.state === 'sent' && Date.now() / 1000 - (p.at || 0) < 8) j.append(h('span', { class: 'chip ok', text: p.note || 'sent to Claude' }));
  else if (p.state === 'failed') j.append(h('span', { class: 'chip bad', text: 'send failed' }));
  else if (p.note === 'still talking' && talk.length) {
    j.append(h('span', { class: 'chip warn' }, h('span', { class: 'dot live', style: 'background:var(--warn)' }), 'still talking'));
  }
}

// ------------------------------------------------------------------ left column

function renderLedger() {
  const settled = S.decisions.filter(d => d.status === 'settled');
  const waiting = S.decisions.filter(d => d.status === 'answered' && d.sent);
  $('#settled-count').textContent = waiting.length ? `${settled.length} + ${waiting.length} sent` : String(settled.length);
  const row = (d, answer, chip) => h('button', {
    type: 'button', class: 'ledger-row divider', 'aria-current': String(ui.focus === d.id), title: 'Show its visuals',
    onclick: () => { focusQuestion(d.id); renderLedger(); },
  },
    h('span', { class: 'qid mono', text: d.id }),
    h('span', { style: 'min-width:0;display:block' }, h('span', { class: 't', text: d.title }),
      chip ? h('span', { class: 'chip acc', text: chip }) : null, h('span', { class: 'a', text: answer })));
  const followups = (S.followups || []).map(f => h('div', { class: 'ledger-row divider' },
    h('span', { class: 'qid mono', text: 'later' }),
    h('span', { style: 'min-width:0;display:block' }, h('span', { class: 't', text: f.title }),
      h('span', { class: 'chip warn', text: 'follow-up ticket' }), h('span', { class: 'a', text: (f.facts || []).join('; ') }))));
  const rows = [...waiting.map(d => row(d, answerSummary(d), 'waiting for Claude')), ...settled.map(d => row(d, d.answer || '')), ...followups];
  $('#ledger').replaceChildren(...(rows.length ? rows : [h('div', { class: 'empty', text: 'Nothing settled yet.' })]));
}

function renderProcs() {
  const procs = [...S.processes].sort((a, b) => (a.state === 'running' ? 0 : 1) - (b.state === 'running' ? 0 : 1) || b.started - a.started);
  const running = procs.filter(p => p.state === 'running').length;
  $('#run-count').textContent = String(running);
  $('#done-count').textContent = `${procs.length - running} done`;
  const box = $('#procs');
  if (!procs.length) { box.replaceChildren(h('div', { class: 'empty', text: 'No research, probe or visual running.' })); return; }
  box.replaceChildren(...procs.slice(0, 30).map(p => {
    const kind = { web: 'Web', code: 'Codebase', probe: 'Probe', visual: 'Visual', review: 'Reviewer', scan: 'Scan' }[p.kind] || p.kind;
    const VCHIP = { killed: 'bad', changed: 'acc', confirmed: 'ok', inconclusive: '' };
    const bar = p.progress && p.state === 'running' ? h('div', {
      class: 'bar', role: 'progressbar', 'aria-label': p.title, 'aria-valuemin': 0,
      'aria-valuemax': p.progress[1], 'aria-valuenow': p.progress[0],
    }, h('div', { style: `width:${Math.round(100 * p.progress[0] / Math.max(1, p.progress[1]))}%` })) : null;
    return h('div', { class: 'proc divider' },
      h('div', { class: `ptile ${p.kind}` }, icon(p.kind in SVG ? p.kind : 'code')),
      h('div', { style: 'flex:1 1 auto;min-width:0' },
        h('div', { class: 'meta' }, h('span', { class: 'eyebrow small', text: kind }), p.for ? h('span', { class: 'chip acc', text: p.for }) : null,
          p.verdict ? h('span', { class: `chip ${VCHIP[p.verdict] ?? ''}`, text: p.verdict }) : null),
        h('div', { class: 'ptitle', text: p.title }),
        h('div', { class: 'pstatus' }, h('span', { class: `dot ${p.state}${p.state === 'running' ? ' live' : ''}` }),
          h('span', { 'data-started': p.started, 'data-ended': p.ended || '', text: elapsed(p.started, p.ended) }),
          h('span', { text: `· ${p.status || ''}` })),
        bar));
  }));
}

let chatLen = -1;
function renderChat() {
  const log = $('#chatlog');
  const sig = S.chat.length + ':' + (S.chat.at(-1)?.text.length || 0);
  if (sig === chatLen) return;
  chatLen = sig;
  const atEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  log.replaceChildren(...(S.chat.length ? S.chat.map(m => m.from === 'me'
    ? h('div', { class: 'msg-me' }, ...linkify(m.text))
    : h('div', { class: 'msg-cl md' }, ...markdown(m.text))) :
    [h('div', { class: 'empty', text: 'Claude\'s replies show here. Links open in a new tab.' })]));
  if (atEnd) log.scrollTop = log.scrollHeight;
}

function linkify(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(/https?:\/\/[^\s<>"')\]]+/g)) {
    const url = m[0].replace(/[.,;:!?]+$/, '');
    out.push(text.slice(last, m.index));
    out.push(h('a', { href: url, target: '_blank', rel: 'noopener noreferrer', text: url }));
    last = m.index + url.length;
  }
  out.push(text.slice(last));
  return out;
}

// Claude's replies are markdown. Nodes are built with textContent only, so a reply can never inject HTML.
const INLINE = /(`[^`\n]+`)|(\*\*[^*\n]+?\*\*|__[^_\n]+?__)|(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))|(https?:\/\/[^\s<>"')\]]+)|(\*[^*\s][^*\n]*?\*|(?<![\w])_[^_\s][^_\n]*?_(?![\w]))/g;

function inline(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    out.push(text.slice(last, m.index));
    const t = m[0];
    if (m[1]) out.push(h('code', { text: t.slice(1, -1) }));
    else if (m[2]) out.push(h('strong', {}, ...inline(t.slice(2, -2))));
    else if (m[3]) {
      const [, label, href] = t.match(/^\[([^\]]+)\]\((.+)\)$/);
      out.push(h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, ...inline(label)));
    } else if (m[4]) {
      const url = t.replace(/[.,;:!?]+$/, '');
      out.push(h('a', { href: url, target: '_blank', rel: 'noopener noreferrer', text: url }));
      last = m.index + url.length;
      continue;
    } else out.push(h('em', {}, ...inline(t.slice(1, -1))));
    last = m.index + t.length;
  }
  out.push(text.slice(last));
  return out;
}

const cells = row => row.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
const LIST = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;

function markdown(text) {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = line.match(/^\s*(```|~~~)/);
    if (fence) {
      const body = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith(fence[1]); i++) body.push(lines[i]);
      i++;
      out.push(h('pre', {}, h('code', { text: body.join('\n') })));
      continue;
    }
    const head = line.match(/^\s*#{1,6}\s+(.*)$/);
    if (head) { out.push(h('p', { class: 'md-h' }, h('strong', {}, ...inline(head[1])))); i++; continue; }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { out.push(h('hr')); i++; continue; }
    if (line.trim().startsWith('|') && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1] || '')) {
      const rows = [];
      for (i += 2; i < lines.length && lines[i].trim().startsWith('|'); i++) rows.push(cells(lines[i]));
      out.push(h('div', { class: 'md-table' }, h('table', {},
        h('thead', {}, h('tr', {}, ...cells(line).map(c => h('th', {}, ...inline(c))))),
        h('tbody', {}, ...rows.map(r => h('tr', {}, ...r.map(c => h('td', {}, ...inline(c)))))))));
      continue;
    }
    if (/^\s*>/.test(line)) {
      const body = [];
      for (; i < lines.length && /^\s*>/.test(lines[i]); i++) body.push(lines[i].replace(/^\s*>\s?/, ''));
      out.push(h('blockquote', {}, ...markdown(body.join('\n'))));
      continue;
    }
    if (LIST.test(line)) {
      // one open list per indent level
      const stack = [];
      for (; i < lines.length; i++) {
        const m = lines[i].match(LIST);
        if (!m) {
          // an indented line continues the last item; anything else ends the list
          if (lines[i].trim() && /^\s+/.test(lines[i]) && stack.length) {
            stack.at(-1).list.lastChild.append(' ', ...inline(lines[i].trim()));
            continue;
          }
          break;
        }
        const indent = m[1].replace(/\t/g, '  ').length;
        while (stack.length && indent < stack.at(-1).indent) stack.pop();
        if (!stack.length || indent > stack.at(-1).indent) {
          const list = h(/\d/.test(m[2]) ? 'ol' : 'ul');
          if (stack.length) stack.at(-1).list.lastChild.append(list);
          else out.push(list);
          stack.push({ indent, list });
        }
        stack.at(-1).list.append(h('li', {}, ...inline(m[3])));
      }
      continue;
    }
    const para = [];
    for (; i < lines.length && lines[i].trim() && !LIST.test(lines[i]) && !/^\s*(```|~~~|#{1,6}\s|>|\|)/.test(lines[i]); i++) {
      if (para.length) para.push(h('br'));
      para.push(...inline(lines[i].trim()));
    }
    if (!para.length) { out.push(h('p', {}, ...inline(line))); i++; continue; }
    out.push(h('p', {}, ...para));
  }
  return out;
}

async function sendChat() {
  const box = $('#chat-input');
  const text = box.value.trim();
  if (!text) return;
  box.value = '';
  store('chatDraft', '');
  try { await post('/api/chat', { text }); } catch (e) { box.value = text; alertLine(`Not sent: ${e.message}`); }
}

function alertLine(msg) { $('#heard').replaceChildren(h('span', { style: 'color:var(--bad)', text: msg })); }

// ------------------------------------------------------------------ middle: visuals

// the middle panel shows the visuals of ONE question: the card opened last, or a Settled row clicked
function renderVisuals() {
  if (!ui.focus || !S.decisions.some(d => d.id === ui.focus)) {
    ui.focus = ui.lastOpen || $('#qcol .q')?.id.replace('card-', '') || null;
  }
  const q = S.decisions.find(d => d.id === ui.focus);
  const items = (q && S.visuals[q.id]) || [];
  const drawing = q ? S.processes.filter(p => p.kind === 'visual' && p.state === 'running' && p.for === q.id) : [];
  if (q) {
    // a visual that just arrived opens by itself; otherwise keep the tab the user chose
    const seen = ui.vseen[q.id] || 0;
    if (items.length > seen || !items.some(v => v.id === ui.vtabs[q.id])) ui.vtabs[q.id] = items.at(-1)?.id || null;
    ui.vseen[q.id] = items.length;
  }
  const cur = q && items.find(v => v.id === ui.vtabs[q.id]);
  $('#vhead').replaceChildren(...(q ? [h('span', { class: 'qid mono', text: q.id }), h('span', { class: 'vtitle', text: q.title })]
    : [h('span', { class: 'vtitle muted', text: 'Open a question to see its visuals' })]));
  $('#tabs').replaceChildren(...items.map(v => {
    const bad = v.lint && v.lint.file === v.file;
    return h('button', {
      type: 'button', class: 'tab', 'aria-current': String(cur && v.id === cur.id),
      title: bad ? `${v.title}: ${v.lint.problems.join('; ')}` : v.title,
      onclick: () => { ui.vtabs[q.id] = v.id; renderVisuals(); },
    }, v.title, bad ? h('span', { class: 'chip warn', text: 'fixing' }) : null);
  }), ...drawing.map(p => h('span', { class: 'tab drawing', title: p.title }, h('span', { class: 'dot running live' }), p.title)));
  const stage = $('#stage');
  if (cur) {
    const src = '/visuals/' + encodeURIComponent(cur.file);
    const frame = stage.querySelector('iframe');
    if (!frame || frame.getAttribute('src') !== src) {
      stage.replaceChildren(h('iframe', { src, title: `${q.id}: ${cur.title}`, sandbox: 'allow-scripts', 'data-qid': q.id, 'data-vid': cur.id }));
    }
  } else if (drawing.length) {
    stage.replaceChildren(h('div', { class: 'placeholder' }, h('div', { class: 'ptile visual live', style: 'width:48px;height:48px' }, icon('visual', 22)),
      h('strong', { text: `Drawing a visual for ${q.id}` }), h('span', { text: 'It opens here when it is ready.' })));
  } else if (q) {
    stage.replaceChildren(h('div', { class: 'placeholder' }, h('strong', { text: `No visual for ${q.id} yet` }),
      h('span', { text: 'Claude draws one when the question is about structure or time.' }),
      h('button', { type: 'button', class: 'btn', text: 'Ask for one', onclick: () => request(q.id, 'visual') })));
  } else {
    stage.replaceChildren(h('div', { class: 'placeholder' }, h('strong', { text: 'No question open' })));
  }
}

function focusQuestion(id) {
  ui.focus = id;
  renderVisuals();
}

// ------------------------------------------------------------------ right: questions

const cards = new Map();

function renderQuestions(list) {
  const col = $('#qcol');
  const spacer = col.querySelector('.spacer');
  const keep = new Set(list.map(d => d.id));
  for (const [id, el] of cards) if (!keep.has(id)) { el.remove(); cards.delete(id); ui.open.delete(id); }
  list.forEach((d, i) => {
    let el = cards.get(d.id);
    if (!el) {
      el = makeCard(d);
      cards.set(d.id, el);
      if (!ui.open.size && d.status === 'open' && !S.decisions.some(x => x.status === 'answered')) ui.open.add(d.id);
    }
    updateCard(el, d);
    const at = col.children[i];
    if (at !== el) col.insertBefore(el, at || spacer);
  });
  if (!list.length && !col.querySelector('.empty')) col.insertBefore(h('div', { class: 'empty', text: 'No open question. Claude sends the next round here.' }), spacer);
  if (list.length) col.querySelector('.empty')?.remove();
}

function makeCard(d) {
  const el = h('div', { class: 'panel q', id: 'card-' + d.id });
  const head = h('button', { type: 'button', class: 'q-head', 'aria-expanded': 'false', onclick: () => toggleCard(d.id) },
    h('span', { class: 'qid mono', text: d.id }),
    h('span', { style: 'flex:1 1 auto;min-width:0' }, h('span', { class: 'q-title' }), h('span', { class: 'q-answer' }), h('span', { class: 'q-chips' })),
    icon('chev'));
  head.lastChild.setAttribute('class', 'chev');
  const ta = h('textarea', {
    id: 'ans-' + d.id, class: 'field', rows: 2, placeholder: 'Your answer · Enter sends, Shift+Enter new line',
    oninput: e => { ui.drafts[d.id] = e.target.value; paintSend(); },
    onkeydown: e => {
      if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
      e.preventDefault();
      const text = e.target.value.trim();
      const card = S.decisions.find(x => x.id === d.id);
      if (ui.needReason[d.id] !== undefined) { if (text) chooseWithReason(card, text); return; }
      if (text || (card && card.status === 'answered' && !card.sent)) answerText(d.id, text);
    },
  });
  const body = h('div', { class: 'q-body divider' },
    h('p', { class: 'q-text' }),
    h('div', { class: 'opts', role: 'group', 'aria-label': 'Options' }),
    h('div', { class: 'rec' }),
    h('p', { class: 'why', role: 'status', hidden: true }),
    h('label', { for: 'ans-' + d.id, class: 'eyebrow small', text: 'Your own answer, or just talk' }),
    ta,
    h('div', { class: 'actions' },
      ...Object.entries(ACTIONS).map(([kind, a]) => h('button', {
        type: 'button', class: 'btn', 'data-kind': kind, text: a.label, onclick: () => request(d.id, kind),
      })),
      h('button', { type: 'button', class: 'btn', text: 'I don\'t know yet', onclick: () => answerText(d.id, 'I don\'t know yet.') })));
  el.append(head, body);
  el._sig = '';
  return el;
}

function updateCard(el, d) {
  const isOpen = ui.open.has(d.id);
  el.classList.toggle('open', isOpen);
  el.classList.toggle('answered', d.status === 'answered');
  el.querySelector('.q-head').setAttribute('aria-expanded', String(isOpen));
  el.querySelector('.q-title').textContent = d.title;
  el.querySelector('.q-answer').textContent = d.status === 'answered' ? '→ ' + answerSummary(d) : '';
  const chips = [];
  if (d.status === 'answered') chips.push(['chip acc', 'answered · not sent']);
  const asked = pendingRequests(d.id);
  for (const [kind, a] of Object.entries(ACTIONS)) {
    const r = asked[kind];
    const btn = el.querySelector(`.actions [data-kind="${kind}"]`);
    btn.disabled = !!r;
    btn.textContent = r ? a.busy : a.label;
    if (r && kind !== 'probe') chips.push(['chip acc live-chip', r.state === 'working' ? a.working : a.pending]);
    else if (r) chips.push(['chip warn live-chip', a.pending]);
  }
  if (!asked.visual && S.processes.some(p => p.kind === 'visual' && p.state === 'running' && p.for === d.id)) {
    chips.push(['chip acc live-chip', 'drawing visual…']);
  }
  if (waitingFor(d.id)) chips.push(['chip warn live-chip', 'waiting for research']);
  const nv = (S.visuals[d.id] || []).length;
  if (nv) chips.push(['chip', nv > 1 ? `${nv} visuals` : 'visual']);
  if (d.stake === 'high') chips.push(['chip', 'hard to undo']);
  if (d.confirms) chips.push(['chip warn', `confirms ${d.confirms}`]);
  if (d.default && d.stake !== 'high') chips.push(['chip', 'default']);
  el.querySelector('.q-chips').replaceChildren(...chips.map(([c, t]) => h('span', { class: c },
    c.includes('live-chip') ? h('span', { class: 'dot live', style: 'width:6px;height:6px;background:currentColor' }) : null, t)));
  el.querySelector('.q-text').textContent = d.body || '';
  const opts = d.options || [];
  const picks = new Set(d.choices || []);
  const sig = JSON.stringify([opts, d.recommendedOption, [...picks]]);
  if (sig !== el._sig) {
    el._sig = sig;
    el.querySelector('.opts').replaceChildren(...opts.map((label, i) => h('button', {
      type: 'button', class: 'opt', 'aria-pressed': String(picks.has(i)), onclick: () => choose(d, i),
    }, h('span', { class: 'key mono', text: String(i + 1) }), h('span', { class: 'label', text: label }),
      i === d.recommendedOption ? h('span', { class: 'chip ok', text: 'recommended' }) : null)));
  }
  el.querySelector('.opts').style.display = opts.length ? '' : 'none';
  const guarded = guardOn(d);
  el.querySelector('.rec').replaceChildren(
    h('div', {}, h('b', { text: 'Recommended' }), ` · ${d.recommendation || ''}`),
    d.flip ? h('div', { class: 'flip' }, h('b', { text: 'What would change this' }), ` · ${d.flip}`) : '',
    d.counter && guarded ? h('div', { class: 'flip counter' }, h('b', { text: 'Strongest case against' }), ` · ${d.counter}`) : '');
  const why = el.querySelector('.why');
  const asking = ui.needReason[d.id] !== undefined;
  why.hidden = !asking;
  why.textContent = asking ? `Why option ${ui.needReason[d.id] + 1}? ${d.stake === 'high' ? 'This one is hard to undo.' : `You accepted ${S.guard.streak} recommendations in a row.`} One line, then Enter.` : '';
  const ta = el.querySelector('textarea');
  if (document.activeElement !== ta) ta.value = ui.drafts[d.id] ?? d.text ?? '';
}

function toggleCard(id) {
  if (ui.open.has(id)) { ui.open.delete(id); if (ui.lastOpen === id) ui.lastOpen = null; }
  else {
    ui.open.add(id);
    ui.lastOpen = id;
    ui.focus = id;
  }
  render();
  if (ui.open.has(id)) requestAnimationFrame(() => {
    const col = $('#qcol');
    col.scrollTo({ top: $('#card-' + id).offsetTop - col.offsetTop, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  });
}

// a high-stake card, or a run of fast recommended picks, asks for one line of reason before it sends
const guardOn = d => d.stake === 'high' || (S.guard && S.guard.streak >= S.guard.limit);

async function choose(d, i) {
  const note = (ui.drafts[d.id] || '').trim();
  if (!d.multi && i === d.recommendedOption && guardOn(d) && !note) {
    ui.needReason[d.id] = i;
    ui.open.add(d.id);
    ui.lastOpen = d.id;
    render();
    $('#ans-' + d.id)?.focus();
    return;
  }
  delete ui.needReason[d.id];
  if (!d.multi) { ui.open.delete(d.id); if (ui.lastOpen === d.id) ui.lastOpen = null; }
  // a single choice is a complete answer: it goes to Claude at once (with a typed note, if any)
  try {
    await post('/api/answer', d.multi ? { id: d.id, choice: i } : { id: d.id, choice: i, text: note, send: true });
    if (!d.multi) delete ui.drafts[d.id];
    await refresh();
  } catch (e) { alertLine(`Not sent: ${e.message}`); }
}

async function chooseWithReason(d, text) {
  const i = ui.needReason[d.id];
  delete ui.needReason[d.id];
  ui.open.delete(d.id);
  if (ui.lastOpen === d.id) ui.lastOpen = null;
  try { await post('/api/answer', { id: d.id, choice: i, text, send: true }); delete ui.drafts[d.id]; await refresh(); }
  catch (e) { alertLine(`Not sent: ${e.message}`); }
}

async function answerText(id, text) {
  ui.open.delete(id);
  if (ui.lastOpen === id) ui.lastOpen = null;
  try { await post('/api/answer', { id, text, send: true }); delete ui.drafts[id]; await refresh(); }
  catch (e) { alertLine(`Not sent: ${e.message}`); }
}

const drafted = () => Object.entries(ui.drafts).filter(([id, t]) => t.trim() && cards.has(id));

function pendingCount() {
  if (!S) return 0;
  return S.transcript.filter(t => !t.sent).length
    + S.decisions.filter(d => d.status === 'answered' && !d.sent).length + drafted().length;
}

function paintSend() {
  const n = pendingCount();
  $('#send-count').textContent = String(n);
  $('#send').disabled = n === 0;
}

// the header Send: what you said (the judge may be wrong), plus multi-select picks and typed card drafts
async function sendAnswers() {
  try {
    for (const [id, text] of drafted()) { await post('/api/answer', { id, text: text.trim() }); delete ui.drafts[id]; }
    await post('/api/send');
    await refresh();
  } catch (e) { alertLine(`Not sent: ${e.message}`); }
}

const ACTIONS = {
  visual: { label: 'Show visual', busy: 'Asking…', pending: 'visual requested', working: 'drawing visual…' },
  explain: { label: 'Explain more', busy: 'Asking…', pending: 'explaining…', working: 'explaining…' },
  probe: { label: 'Run a probe', busy: 'Asking…', pending: 'probe requested', working: 'probe requested' },
  park: { label: 'Park branch', busy: 'Asking…', pending: 'parking…', working: 'parking…' },
};

function pendingRequests(qid) {
  const out = {};
  for (const r of S.requests || []) if (r.qid === qid && r.state !== 'done') out[r.kind] = r;
  for (const [key, at] of Object.entries(ui.asking)) {
    const [q, kind] = key.split(':');
    if (q === qid && !out[kind] && Date.now() - at < 5000) out[kind] = { state: 'pending' };
  }
  return out;
}

async function request(id, kind) {
  ui.asking[`${id}:${kind}`] = Date.now();  // feedback before the server answers
  const el = cards.get(id);
  if (el) updateCard(el, S.decisions.find(x => x.id === id));
  try { await post('/api/request', { id, kind }); await refresh(); } catch (e) { alertLine(`Not sent: ${e.message}`); }
  delete ui.asking[`${id}:${kind}`];
}

// ------------------------------------------------------------------ mic: browser VAD → 16 kHz WAV utterances

const mic = { on: false, speaking: false, ctx: null, stream: null, node: null, live: '', final: null, previewing: false };
const VAD = { block: 0.02, preroll: 0.4, hangover: 0.85, minSpeech: 0.6, maxSpeech: 30, minRms: 0.012, factor: 3.2,
  previewEvery: 1.2, previewWindow: 10, finalShown: 4 };

async function micStart() {
  try {
    mic.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    mic.ctx = new AudioContext();
    const code = 'class P extends AudioWorkletProcessor{process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor("tap",P)';
    await mic.ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([code], { type: 'application/javascript' })));
    const src = mic.ctx.createMediaStreamSource(mic.stream);
    mic.node = new AudioWorkletNode(mic.ctx, 'tap');
    const mute = mic.ctx.createGain();
    mute.gain.value = 0;
    src.connect(mic.node).connect(mute).connect(mic.ctx.destination);
    const vad = makeVad(mic.ctx.sampleRate);
    mic.node.port.onmessage = e => vad(e.data);
    mic.on = true;
    mic.error = '';
  } catch (e) {
    mic.on = false;
    mic.error = e.message || String(e);
  }
  if (mic.on) store('mic', true);
  paintMic();
}

function micStop() {
  mic.stream?.getTracks().forEach(t => t.stop());
  mic.ctx?.close();
  Object.assign(mic, { on: false, speaking: false, ctx: null, stream: null, node: null });
  store('mic', false);
  paintMic();
}

function paintMic() {
  const b = $('#mic');
  b.className = 'mic ' + (mic.on ? 'on' : 'off') + (mic.speaking ? ' speaking' : '');
  b.setAttribute('aria-pressed', String(mic.on));
  b.setAttribute('aria-label', mic.on ? 'Microphone on' : 'Microphone off');
  b.title = (mic.on ? 'Microphone on' : 'Microphone off') + ' (M)';
  renderVoice();
}

function makeVad(rate) {
  const blockLen = Math.round(rate * VAD.block);
  let block = new Float32Array(blockLen), fill = 0;
  let floor = 0.005, loud = 0, quiet = 0;
  const pre = [];
  let speech = null;
  return frame => {
    for (let i = 0; i < frame.length; i++) {
      block[fill++] = frame[i];
      if (fill < blockLen) continue;
      fill = 0;
      let sum = 0;
      for (let k = 0; k < blockLen; k++) sum += block[k] * block[k];
      const rms = Math.sqrt(sum / blockLen);
      const chunk = block;
      block = new Float32Array(blockLen);
      const thr = Math.max(VAD.minRms, floor * VAD.factor);
      if (!speech) {
        floor = 0.97 * floor + 0.03 * Math.min(rms, thr);
        pre.push(chunk);
        if (pre.length > VAD.preroll / VAD.block) pre.shift();
        loud = rms > thr ? loud + 1 : 0;
        if (loud >= 3) { speech = [...pre]; pre.length = 0; quiet = 0; mic.speaking = true; mic.live = ''; mic.final = null; paintMic(); }
      } else {
        speech.push(chunk);
        quiet = rms > thr ? 0 : quiet + 1;
        const secs = speech.length * VAD.block;
        if (speech.length % Math.round(VAD.previewEvery / VAD.block) === 0 && !mic.previewing) {
          preview(speech.slice(-Math.round(VAD.previewWindow / VAD.block)), rate);
        }
        if (quiet * VAD.block >= VAD.hangover || secs >= VAD.maxSpeech) {
          const parts = speech;
          speech = null; loud = 0;
          mic.speaking = false; paintMic();
          if (secs - quiet * VAD.block >= VAD.minSpeech) upload(parts, rate);
        }
      }
    }
  };
}

async function preview(parts, rate) {
  mic.previewing = true;
  try {
    const r = await post('/api/partial', wav(to16k(parts, rate), 16000), true);
    if (mic.speaking && r.text) { mic.live = r.text; renderVoice(); }
  } catch { /* a preview is best effort */ }
  mic.previewing = false;
}

async function upload(parts, rate) {
  try {
    const r = await post('/api/utterance', wav(to16k(parts, rate), 16000), true);
    mic.live = '';
    mic.final = r.text ? { text: r.text, until: Date.now() + VAD.finalShown * 1000 } : null;
    renderVoice();
    if (mic.final) setTimeout(renderVoice, VAD.finalShown * 1000 + 50);
  } catch (e) { alertLine(`Transcription failed: ${e.message}`); }
}

function to16k(parts, rate) {
  const n = parts.reduce((a, p) => a + p.length, 0);
  const all = new Float32Array(n);
  let o = 0;
  for (const p of parts) { all.set(p, o); o += p.length; }
  const ratio = rate / 16000;
  const out = new Float32Array(Math.floor(n / ratio));
  for (let i = 0; i < out.length; i++) {
    const a = Math.floor(i * ratio), b = Math.min(n, Math.floor((i + 1) * ratio));
    let s = 0;
    for (let k = a; k < b; k++) s += all[k];
    out[i] = s / Math.max(1, b - a);
  }
  return out;
}

function wav(samples, rate) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data');
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, samples[i])) * 0x7fff, true);
  return new Blob([buf], { type: 'audio/wav' });
}

// ------------------------------------------------------------------ resize: column splitters and list grips

const LAYOUT = { left: 300, right: 400, minLeft: 220, minRight: 300, minMiddle: 360, minList: 60 };
const layout = Object.assign({ left: LAYOUT.left, right: LAYOUT.right, lists: {} }, store('layout') || {});

function applyLayout() {
  const cols = $('.cols');
  const room = cols.clientWidth - 40 - 2 * 16;
  layout.left = Math.max(LAYOUT.minLeft, Math.min(layout.left, room - LAYOUT.minMiddle - LAYOUT.minRight));
  const leftUsed = $('.app').classList.contains('left-hidden') ? 0 : layout.left;
  layout.right = Math.max(LAYOUT.minRight, Math.min(layout.right, room - LAYOUT.minMiddle - leftUsed));
  cols.style.setProperty('--left-w', layout.left + 'px');
  cols.style.setProperty('--right-w', layout.right + 'px');
  for (const sp of document.querySelectorAll('.splitter')) {
    const v = layout[sp.dataset.side];
    sp.setAttribute('aria-valuenow', String(Math.round(v)));
    sp.setAttribute('aria-valuemin', String(sp.dataset.side === 'left' ? LAYOUT.minLeft : LAYOUT.minRight));
  }
  for (const g of document.querySelectorAll('.vgrip')) {
    const el = $(g.dataset.target);
    const hgt = layout.lists[g.dataset.key];
    el.classList.toggle('sized', !!hgt);
    el.style.height = hgt ? hgt + 'px' : '';
    el.style.maxHeight = hgt ? 'none' : '';
    if (hgt) g.setAttribute('aria-valuenow', String(Math.round(hgt)));
  }
}

function saveLayout() { applyLayout(); store('layout', layout); }

function drag(handle, onMove) {
  handle.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    e.preventDefault();
    handle.setPointerCapture(e.pointerId);
    handle.classList.add('dragging');
    document.body.classList.add('resizing');
    const start = { x: e.clientX, y: e.clientY };
    const begin = onMove(null);
    const move = ev => { onMove({ dx: ev.clientX - start.x, dy: ev.clientY - start.y, begin }); applyLayout(); };
    const up = () => {
      handle.removeEventListener('pointermove', move);
      handle.classList.remove('dragging');
      document.body.classList.remove('resizing');
      saveLayout();
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', up, { once: true });
    handle.addEventListener('pointercancel', up, { once: true });
  });
}

for (const sp of document.querySelectorAll('.splitter')) {
  const side = sp.dataset.side;
  // left grows when dragged right; the questions panel grows when dragged left
  drag(sp, m => (m ? (layout[side] = m.begin + (side === 'left' ? m.dx : -m.dx)) : layout[side]));
  sp.addEventListener('dblclick', () => { layout[side] = LAYOUT[side]; saveLayout(); });
  sp.addEventListener('keydown', e => {
    const step = e.shiftKey ? 64 : 16;
    const dir = { ArrowLeft: -1, ArrowRight: 1 }[e.key];
    if (!dir) return;
    e.preventDefault();
    layout[side] += side === 'left' ? dir * step : -dir * step;
    saveLayout();
  });
}

for (const g of document.querySelectorAll('.vgrip')) {
  const key = g.dataset.key;
  const target = () => $(g.dataset.target);
  drag(g, m => (m ? (layout.lists[key] = Math.max(LAYOUT.minList, m.begin + m.dy)) : target().getBoundingClientRect().height));
  g.addEventListener('dblclick', () => { delete layout.lists[key]; saveLayout(); });
  g.addEventListener('keydown', e => {
    const dir = { ArrowUp: -1, ArrowDown: 1 }[e.key];
    if (!dir) return;
    e.preventDefault();
    const cur = layout.lists[key] || target().getBoundingClientRect().height;
    layout.lists[key] = Math.max(LAYOUT.minList, cur + dir * (e.shiftKey ? 64 : 16));
    saveLayout();
  });
}

window.addEventListener('resize', applyLayout);
applyLayout();

// ------------------------------------------------------------------ left panel: hide and show

function setLeft(shown) {
  $('.app').classList.toggle('left-hidden', !shown);
  const b = $('#side-toggle');
  b.setAttribute('aria-expanded', String(shown));
  const label = shown ? 'Hide the left panel' : 'Show the left panel';
  b.setAttribute('aria-label', label);
  b.title = label + ' (B)';
  store('leftShown', shown);
  applyLayout();
}

$('#side-toggle').addEventListener('click', () => setLeft($('.app').classList.contains('left-hidden')));
setLeft(store('leftShown') !== false);

// ------------------------------------------------------------------ wiring

// only the frame on the stage may report
window.addEventListener('message', e => {
  const frame = $('#stage iframe');
  if (!frame || e.source !== frame.contentWindow || e.data?.type !== 'grill-deck-lint') return;
  const problems = (e.data.problems || []).map(String).slice(0, 5);
  if (problems.length) post('/api/visual-lint', { for: frame.dataset.qid, vid: frame.dataset.vid, problems }).catch(() => {});
});

$('#mic').addEventListener('click', () => (mic.on ? micStop() : micStart()));
$('#send').addEventListener('click', sendAnswers);
$('#chat-send').addEventListener('click', sendChat);
$('#chat-input').value = store('chatDraft') || '';
$('#chat-input').addEventListener('input', e => store('chatDraft', e.target.value));
$('#chat-input').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendChat(); } });

for (const sec of document.querySelectorAll('.sec')) {
  const btn = sec.querySelector('.sec-toggle');
  const saved = store('sec:' + sec.dataset.sec);
  if (saved !== null) btn.setAttribute('aria-expanded', String(saved));
  btn.addEventListener('click', () => {
    const next = btn.getAttribute('aria-expanded') !== 'true';
    btn.setAttribute('aria-expanded', String(next));
    store('sec:' + sec.dataset.sec, next);
  });
}

document.addEventListener('keydown', e => {
  if (e.target.closest('textarea, input') || e.altKey) return;
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); $('#send').click(); return; }
  if (e.ctrlKey || e.metaKey) return;
  if (e.key === 'm' || e.key === 'M') { $('#mic').click(); return; }
  if (e.key === 'b' || e.key === 'B') { $('#side-toggle').click(); return; }
  const id = ui.lastOpen;
  const d = id && S?.decisions.find(x => x.id === id);
  if (!d) return;
  if (e.key === 'Escape') { toggleCard(id); return; }
  const i = Number(e.key) - 1;
  if (i >= 0 && i < (d.options || []).length) { e.preventDefault(); choose(d, i); }
});

poll();
if (store('mic') !== false) micStart();
