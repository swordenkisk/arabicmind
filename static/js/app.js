/**
 * ArabicMind — app.js
 * Dual-pane Arabic/English UI with SSE streaming
 */
'use strict';

// ── State ──────────────────────────────────────────────────────
const state = {
  running    : false,
  config     : {},
  domain     : "",
  eventSource: null,
};

// ── DOM refs ───────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const els = {
  queryInput  : $('query-input'),
  btnSend     : $('btn-send'),
  sendLabel   : $('send-label'),
  statusText  : $('status-text'),
  timerText   : $('timer-text'),
  paneArabic  : $('pane-arabic'),
  paneEnglish : $('pane-english'),
  qtText      : $('qt-text'),
  qtContainer : $('query-translated'),
  cotPanel    : $('cot-panel'),
  cotSteps    : $('cot-steps'),
  timingBar   : $('timing-bar'),
  badgeDomAr  : $('badge-domain-ar'),
  badgeModelEn: $('badge-model-en'),
};

// ── Simple Markdown renderer ────────────────────────────────────
function renderMD(text) {
  const blocks = [];
  const code   = [];

  // Extract code blocks
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, c) => {
    const i = code.length;
    code.push(`<pre><code class="lang-${lang}">${escHtml(c.trim())}</code></pre>`);
    return `\x00CODE${i}\x00`;
  });

  text = escHtml(text);

  text = text
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^#{3} (.+)$/gm, '<h3>$1</h3>')
    .replace(/^#{2} (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm,    '<h1>$1</h1>')
    .replace(/^---+$/gm, '<hr/>')
    .replace(/^\s*[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]+?<\/li>)+/g, m => `<ul>${m}</ul>`)
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    .split('\n\n').map(p => {
      p = p.trim();
      if (!p) return '';
      if (/^<(h[1-3]|ul|ol|hr|pre|blockquote)/.test(p)) return p;
      return `<p>${p.replace(/\n/g,'<br/>')}</p>`;
    }).join('\n');

  text = text.replace(/\x00CODE(\d+)\x00/g, (_, i) => code[+i]);
  return text;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Config management ───────────────────────────────────────────
function loadConfig() {
  try {
    state.config = JSON.parse(localStorage.getItem('arabicmind_config') || '{}');
    if (state.config.tr_provider) $('tr-provider').value = state.config.tr_provider;
    if (state.config.tr_key)      $('tr-key').value      = state.config.tr_key;
    if (state.config.tr_model)    $('tr-model').value    = state.config.tr_model;
    if (state.config.rs_provider) $('rs-provider').value = state.config.rs_provider;
    if (state.config.rs_key)      $('rs-key').value      = state.config.rs_key;
    if (state.config.rs_model)    $('rs-model').value    = state.config.rs_model;
    if (state.config.show_cot !== undefined)
      $('show-cot').checked = state.config.show_cot;
    updateModelList('tr');
    updateModelList('rs');
  } catch {}
}

function saveConfig() {
  state.config = {
    tr_provider: $('tr-provider').value,
    tr_key     : $('tr-key').value,
    tr_model   : $('tr-model').value,
    rs_provider: $('rs-provider').value,
    rs_key     : $('rs-key').value,
    rs_model   : $('rs-model').value,
    show_cot   : $('show-cot').checked,
  };
  localStorage.setItem('arabicmind_config', JSON.stringify(state.config));
  showToast('✓ تم حفظ الإعدادات | Config saved');
  closeDrawer();
}

function updateModelList(prefix) {
  const provider = $(prefix + '-provider').value;
  const select   = $(prefix + '-model');
  const pdata    = window.PROVIDERS_DATA[provider];
  select.innerHTML = '';
  if (pdata && pdata.models) {
    pdata.models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = m;
      if (m === pdata.default) opt.selected = true;
      select.appendChild(opt);
    });
  }
}

async function testKeys() {
  const div = $('test-result');
  div.textContent = 'جاري الاختبار...';
  div.className = 'test-result';
  div.classList.remove('hidden');
  try {
    const r = await fetch('/api/validate_key', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        provider: $('rs-provider').value,
        api_key : $('rs-key').value,
        model   : $('rs-model').value,
      }),
    });
    const d = await r.json();
    div.textContent = d.valid
      ? `✓ المفتاح صالح | Key valid — ${d.model}`
      : `✗ ${d.error}`;
    div.className = 'test-result ' + (d.valid ? 'ok' : 'err');
  } catch (e) {
    div.textContent = `✗ ${e.message}`;
    div.className = 'test-result err';
  }
}

// ── Drawer ─────────────────────────────────────────────────────
function openDrawer() {
  $('config-drawer').classList.add('open');
  $('drawer-overlay').classList.add('active');
}
function closeDrawer() {
  $('config-drawer').classList.remove('open');
  $('drawer-overlay').classList.remove('active');
}

// ── Domain selection ────────────────────────────────────────────
document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    state.domain = chip.dataset.domain || '';
  });
});

// ── Status helpers ──────────────────────────────────────────────
function setStatus(msg, cls='working') {
  els.statusText.textContent = msg;
  els.statusText.className   = 'status-' + cls;
}

let timerInterval = null;
function startTimer() {
  const t0 = Date.now();
  els.timerText.classList.remove('hidden');
  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    els.timerText.textContent = ((Date.now() - t0) / 1000).toFixed(1) + 's';
  }, 100);
}
function stopTimer() { clearInterval(timerInterval); }

// ── Toast ───────────────────────────────────────────────────────
function showToast(msg, dur=2000) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), dur);
}

// ── Clear panes ─────────────────────────────────────────────────
function clearPanes() {
  els.paneArabic.innerHTML  = '';
  els.paneEnglish.innerHTML = '';
  els.qtContainer.classList.add('hidden');
  els.cotPanel.classList.add('hidden');
  els.cotSteps.innerHTML = '';
  els.timingBar.classList.add('hidden');
  els.badgeDomAr.textContent  = '';
  els.badgeModelEn.textContent = '';
}

// ── Copy pane ───────────────────────────────────────────────────
function copyPane(which) {
  const el   = which === 'arabic' ? els.paneArabic : els.paneEnglish;
  const text = el.innerText || el.textContent;
  navigator.clipboard.writeText(text).then(() =>
    showToast(which === 'arabic' ? '✓ تم نسخ الإجابة العربية' : '✓ Copied English text')
  );
}

// ── Main send ───────────────────────────────────────────────────
function sendQuery() {
  const query = els.queryInput.value.trim();
  if (!query || state.running) return;

  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
    state.running = false;
    els.btnSend.disabled = false;
    els.sendLabel.textContent = 'إرسال ▶';
    return;
  }

  state.running = true;
  els.btnSend.disabled = false;
  els.sendLabel.textContent = '⏹ إيقاف';
  clearPanes();
  startTimer();
  setStatus('جاري معالجة سؤالك... | Processing...', 'working');

  const cfg = state.config;
  const params = new URLSearchParams({
    query      : query,
    tr_provider: cfg.tr_provider || 'mock',
    tr_key     : cfg.tr_key      || '',
    tr_model   : cfg.tr_model    || '',
    rs_provider: cfg.rs_provider || 'mock',
    rs_key     : cfg.rs_key      || '',
    rs_model   : cfg.rs_model    || '',
    show_cot   : cfg.show_cot !== false ? 'true' : 'false',
    domain     : state.domain || '',
  });

  const es = new EventSource('/api/stream?' + params);
  state.eventSource = es;

  let arabicContent = '';
  let englishContent = '';
  let arCursor, enCursor;

  // Add streaming cursor
  function addCursor(container) {
    const cur = document.createElement('span');
    cur.className = 'cursor';
    container.appendChild(cur);
    return cur;
  }

  es.onmessage = e => {
    const data = JSON.parse(e.data);
    const evt  = data.event;

    if (evt === 'translating_query') {
      setStatus('① ترجمة السؤال للإنجليزية... | Translating query...', 'working');
    }

    else if (evt === 'query_translated') {
      els.qtText.textContent = data.english_query;
      els.qtContainer.classList.remove('hidden');
    }

    else if (evt === 'domain_detected') {
      const domainInfo = window.DOMAINS_DATA.find(d => d.key === data.domain) || {};
      const label = (domainInfo.icon || '') + ' ' + (domainInfo.name_ar || data.domain);
      els.badgeDomAr.textContent = label;
      setStatus('② استدلال عميق بالإنجليزية... | Deep reasoning...', 'working');
    }

    else if (evt === 'reasoning_chunk') {
      if (!enCursor) {
        enCursor = addCursor(els.paneEnglish);
      }
      englishContent += data.text;
      // Re-render with cursor
      const cur = els.paneEnglish.querySelector('.cursor');
      els.paneEnglish.innerHTML = renderMD(englishContent);
      if (!data.text.includes('```')) {
        const newCur = document.createElement('span');
        newCur.className = 'cursor';
        els.paneEnglish.appendChild(newCur);
        enCursor = newCur;
      }
      els.paneEnglish.scrollTop = els.paneEnglish.scrollHeight;
    }

    else if (evt === 'reasoning_done') {
      englishContent = data.english_response;
      els.paneEnglish.innerHTML = renderMD(englishContent);
      els.paneEnglish.scrollTop = els.paneEnglish.scrollHeight;
      setStatus('③ ترجمة الإجابة للعربية... | Back-translating...', 'working');
    }

    else if (evt === 'cot_extracted') {
      if (data.steps && data.steps.length > 0) {
        els.cotPanel.classList.remove('hidden');
        els.cotSteps.innerHTML = data.steps.slice(0, 12).map(
          s => `<div class="cot-step">${escHtml(s.slice(0, 150))}</div>`
        ).join('');
      }
    }

    else if (evt === 'translating_response') {
      setStatus('③ ترجمة الإجابة للعربية... | Translating response...', 'working');
    }

    else if (evt === 'done') {
      const result = data.result;
      els.paneArabic.innerHTML  = renderMD(result.arabic_response || '');
      els.paneEnglish.innerHTML = renderMD(result.english_response || '');

      // Timing
      els.timingBar.classList.remove('hidden');
      $('t-translate').textContent = `⏱ ترجمة: ${result.translation_ms}ms`;
      $('t-reason').textContent    = `🧠 استدلال: ${result.reasoning_ms}ms`;
      $('t-back').textContent      = `⏱ عودة: ${result.back_translation_ms}ms`;
      $('t-total').textContent     = `⏱ الإجمالي: ${result.total_ms || result.translation_ms + result.reasoning_ms + result.back_translation_ms}ms`;

      stopTimer();
      setStatus('✓ اكتملت المعالجة | Processing complete', 'done');
      state.running = false;
      els.sendLabel.textContent = 'إرسال ▶';
      es.close();
      state.eventSource = null;
    }

    else if (evt === 'error') {
      setStatus('✗ خطأ | Error: ' + (data.message || ''), 'error');
      stopTimer();
      state.running = false;
      els.sendLabel.textContent = 'إرسال ▶';
      es.close();
    }
  };

  es.onerror = () => {
    setStatus('✗ انقطع الاتصال | Connection error', 'error');
    stopTimer();
    state.running = false;
    els.sendLabel.textContent = 'إرسال ▶';
    es.close();
    state.eventSource = null;
  };
}

// ── Auto-resize textarea ────────────────────────────────────────
els.queryInput.addEventListener('input', () => {
  els.queryInput.style.height = 'auto';
  els.queryInput.style.height = Math.min(els.queryInput.scrollHeight, 200) + 'px';
  els.btnSend.disabled = !els.queryInput.value.trim();
});

els.queryInput.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    sendQuery();
  }
});

// ── Bind buttons ────────────────────────────────────────────────
els.btnSend.addEventListener('click', sendQuery);
$('btn-config').addEventListener('click', openDrawer);

// ── Init ────────────────────────────────────────────────────────
loadConfig();
// Init model lists
updateModelList('tr');
updateModelList('rs');
els.btnSend.disabled = true;
