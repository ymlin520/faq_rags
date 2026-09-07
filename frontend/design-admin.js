/* 前台外觀後台 */
(function () {
  var $ = function (s) { return document.querySelector(s); };
  var TOKEN_KEY = 'faq-design-token';
  var token = sessionStorage.getItem(TOKEN_KEY) || '';
  var config = null, themeFields = [], textFields = [], previewTimer = null;

  function esc(v) {
    return String(v == null ? '' : v)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function headers() { return { 'Content-Type': 'application/json', 'X-Design-Token': token }; }

  function toast(msg, bad) {
    var el = $('#toast');
    el.textContent = msg;
    el.className = 'toast' + (bad ? ' bad' : '');
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.hidden = true; }, 2600);
  }

  /* ---------------- 登入 ---------------- */
  $('#login-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    var value = $('#login-token').value.trim();
    $('#login-error').textContent = '';
    try {
      var r = await fetch('/api/design/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: value })
      });
      if (!r.ok) { var d = await r.json().catch(function () { return {}; }); throw new Error(d.detail || '登入失敗'); }
      token = value;
      sessionStorage.setItem(TOKEN_KEY, token);
      start();
    } catch (err) { $('#login-error').textContent = err.message; }
  });

  async function start() {
    var r = await fetch('/api/design/config', { headers: headers() });
    if (!r.ok) { sessionStorage.removeItem(TOKEN_KEY); token = ''; $('#login-error').textContent = '密碼不正確或已失效'; return; }
    var data = await r.json();
    config = data.config;
    themeFields = data.theme_fields;
    textFields = data.text_fields;
    $('#login').hidden = true;
    $('#app').hidden = false;
    renderAll();
  }

  /* ---------------- 表單渲染 ---------------- */
  function groupBy(rows) {
    var order = [], map = {};
    rows.forEach(function (row) {
      if (!map[row.group]) { map[row.group] = []; order.push(row.group); }
      map[row.group].push(row);
    });
    return order.map(function (name) { return { name: name, rows: map[name] }; });
  }

  function renderTextFields() {
    var html = groupBy(textFields).map(function (g) {
      return '<div class="group"><h3>' + esc(g.name) + '</h3>' + g.rows.map(function (f) {
        var value = config.text[f.key] == null ? f.default : config.text[f.key];
        var input = f.long
          ? '<textarea data-text="' + f.key + '" rows="2">' + esc(value) + '</textarea>'
          : '<input type="text" data-text="' + f.key + '" value="' + esc(value) + '">';
        return '<div class="field"><label>' + esc(f.label) + '</label>' + input + '</div>';
      }).join('') + '</div>';
    }).join('');
    $('#text-fields').innerHTML = html;
  }

  function renderThemeFields() {
    var html = groupBy(themeFields).map(function (g) {
      return '<div class="group"><h3>' + esc(g.name) + '</h3>' + g.rows.map(function (f) {
        var value = config.theme[f.key] == null ? f.default : config.theme[f.key];
        var control;
        if (f.kind === 'color') {
          var hex = /^#[0-9a-fA-F]{6}$/.test(String(value)) ? value : '#ffffff';
          control = '<div class="color-field"><input type="color" data-color-for="' + f.key + '" value="' + esc(hex) + '">'
            + '<input type="text" data-theme="' + f.key + '" value="' + esc(value) + '" spellcheck="false"></div>';
        } else if (f.kind === 'num') {
          control = '<div class="num-field"><input type="range" min="0" max="60" data-range-for="' + f.key + '" value="' + esc(value) + '">'
            + '<input type="number" min="0" max="200" data-theme="' + f.key + '" value="' + esc(value) + '"></div>';
        } else {
          control = '<input type="text" data-theme="' + f.key + '" value="' + esc(value) + '" spellcheck="false">';
        }
        return '<div class="field"><label>' + esc(f.label) + '</label>' + control + '</div>';
      }).join('') + '</div>';
    }).join('');
    $('#theme-fields').innerHTML = html;
  }

  function rowHtml(kind, row) {
    var a = kind === 'category' ? '分類代碼' : '顯示文字';
    var b = kind === 'category' ? '顯示名稱' : '送出問題';
    return '<div class="row" data-kind="' + kind + '">'
      + '<input data-field="' + (kind === 'category' ? 'query' : 'label') + '" placeholder="' + a + '" value="'
      + esc(kind === 'category' ? (row.query || '') : (row.label || '')) + '">'
      + '<input data-field="' + (kind === 'category' ? 'label' : 'query') + '" placeholder="' + b + '" value="'
      + esc(kind === 'category' ? (row.label || '') : (row.query || '')) + '">'
      + '<button type="button" data-remove>刪除</button></div>';
  }

  function renderRows() {
    var cats = config.categories || [], sugs = config.suggestions || [];
    $('#category-rows').innerHTML = (cats.length
      ? '<div class="row-head"><span>分類代碼（知識庫名稱）</span><span>前台顯示名稱</span><span></span></div>'
        + cats.map(function (r) { return rowHtml('category', r); }).join('')
      : '<p class="rows-empty">目前未自訂，前台會自動使用知識庫產生的分類。</p>');
    $('#suggestion-rows').innerHTML = (sugs.length
      ? '<div class="row-head"><span>按鈕顯示文字</span><span>實際送出的問題</span><span></span></div>'
        + sugs.map(function (r) { return rowHtml('suggestion', r); }).join('')
      : '<p class="rows-empty">目前沒有快捷問題。</p>');
  }

  function renderAll() {
    renderTextFields();
    renderThemeFields();
    renderRows();
    $('#custom-css').value = config.custom_css || '';
    $('#saved-at').textContent = config.updated_at ? ('最後儲存：' + config.updated_at) : '尚未儲存過';
  }

  /* ---------------- 收集表單 ---------------- */
  function collectRows(container, kind) {
    return Array.prototype.map.call(container.querySelectorAll('.row'), function (row) {
      var out = { label: '', query: '' };
      row.querySelectorAll('input').forEach(function (i) { out[i.dataset.field] = i.value.trim(); });
      return out;
    }).filter(function (r) { return r.label || r.query; })
      .map(function (r) { return { label: r.label || r.query, query: r.query || r.label }; });
  }

  function collect() {
    var text = {}, theme = {};
    document.querySelectorAll('[data-text]').forEach(function (el) { text[el.dataset.text] = el.value; });
    document.querySelectorAll('[data-theme]').forEach(function (el) { theme[el.dataset.theme] = el.value; });
    return {
      text: text, theme: theme,
      categories: collectRows($('#category-rows'), 'category'),
      suggestions: collectRows($('#suggestion-rows'), 'suggestion'),
      custom_css: $('#custom-css').value
    };
  }

  /* ---------------- 即時預覽 ---------------- */
  async function refreshPreview() {
    var frame = $('#preview');
    var doc = frame.contentDocument;
    if (!doc || !doc.head) return;
    var payload = collect();
    try {
      var r = await fetch('/api/design/preview.css', {
        method: 'POST', headers: headers(),
        body: JSON.stringify({ theme: payload.theme, custom_css: payload.custom_css })
      });
      if (r.ok) {
        var css = await r.text();
        var style = doc.getElementById('sc-preview-style');
        if (!style) {
          style = doc.createElement('style');
          style.id = 'sc-preview-style';
          doc.head.appendChild(style);
        }
        style.textContent = css;
        var link = doc.getElementById('site-theme');
        if (link) link.disabled = true;
      }
    } catch (e) { /* 預覽失敗不影響編輯 */ }

    doc.querySelectorAll('[data-sc]').forEach(function (el) {
      var v = payload.text[el.dataset.sc];
      if (typeof v === 'string' && v !== '') el.textContent = v;
    });
    doc.querySelectorAll('[data-sc-placeholder]').forEach(function (el) {
      var v = payload.text[el.dataset.scPlaceholder];
      if (typeof v === 'string' && v !== '') el.placeholder = v;
    });
    var box = doc.getElementById('sc-suggestions');
    if (box) {
      box.innerHTML = payload.suggestions.map(function (row) {
        return '<button data-example="' + esc(row.query) + '">' + esc(row.label) + '</button>';
      }).join('');
    }
    var nav = doc.getElementById('category-list');
    if (nav && payload.categories.length) {
      nav.innerHTML = payload.categories.map(function (row, i) {
        return '<button class="category" data-category="' + esc(row.query) + '"><span>'
          + String(i + 1).padStart(2, '0') + '</span>' + esc(row.label) + '</button>';
      }).join('');
    }
    applyRawPreview();
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(refreshPreview, 350);
  }

  /* ---------------- 事件 ---------------- */
  document.addEventListener('input', function (e) {
    var el = e.target;
    if (el.dataset.colorFor) {
      var text = document.querySelector('[data-theme="' + el.dataset.colorFor + '"]');
      if (text) text.value = el.value;
    }
    if (el.dataset.rangeFor) {
      var num = document.querySelector('[data-theme="' + el.dataset.rangeFor + '"]');
      if (num) num.value = el.value;
    }
    if (el.dataset.theme) {
      var color = document.querySelector('[data-color-for="' + el.dataset.theme + '"]');
      if (color && /^#[0-9a-fA-F]{6}$/.test(el.value)) color.value = el.value;
      var range = document.querySelector('[data-range-for="' + el.dataset.theme + '"]');
      if (range) range.value = el.value;
    }
    if (el.dataset.theme || el.dataset.text || el.dataset.colorFor || el.dataset.rangeFor
        || el.id === 'custom-css' || el.dataset.field) schedulePreview();
  });

  document.addEventListener('click', function (e) {
    var tab = e.target.closest('.tab');
    if (tab) {
      document.querySelectorAll('.tab').forEach(function (t) { t.classList.toggle('active', t === tab); });
      document.querySelectorAll('.tab-panel').forEach(function (p) { p.hidden = p.dataset.panel !== tab.dataset.tab; });
    }
    if (e.target.matches('[data-remove]')) { e.target.closest('.row').remove(); schedulePreview(); }
    var view = e.target.closest('.chip[data-view]');
    if (view) {
      document.querySelectorAll('.chip[data-view]').forEach(function (c) { c.classList.toggle('active', c === view); });
      $('#preview-stage').classList.toggle('mobile', view.dataset.view === 'mobile');
    }
    var preset = e.target.closest('.preset');
    if (preset) applyPreset(preset.dataset.preset);
  });

  $('#add-category').addEventListener('click', function () {
    var box = $('#category-rows');
    if (!box.querySelector('.row')) box.innerHTML = '<div class="row-head"><span>分類代碼（知識庫名稱）</span><span>前台顯示名稱</span><span></span></div>';
    box.insertAdjacentHTML('beforeend', rowHtml('category', {}));
  });
  $('#add-suggestion').addEventListener('click', function () {
    var box = $('#suggestion-rows');
    if (!box.querySelector('.row')) box.innerHTML = '<div class="row-head"><span>按鈕顯示文字</span><span>實際送出的問題</span><span></span></div>';
    box.insertAdjacentHTML('beforeend', rowHtml('suggestion', {}));
  });
  $('#load-categories').addEventListener('click', async function () {
    try {
      var r = await fetch('/api/categories?limit=20');
      var d = await r.json();
      var rows = (d.categories || []).map(function (c) {
        return { query: c.category, label: String(c.category).replace(/^[一二三四五六七八九十百]+、/, '') };
      });
      if (!rows.length) return toast('知識庫目前沒有分類', true);
      config.categories = rows;
      renderRows();
      schedulePreview();
      toast('已帶入 ' + rows.length + ' 個分類');
    } catch (err) { toast('讀取分類失敗', true); }
  });

  $('#preview-reload').addEventListener('click', function () { $('#preview').contentWindow.location.reload(); });
  $('#preview').addEventListener('load', function () { schedulePreview(); });

  $('#btn-save').addEventListener('click', async function () {
    var btn = this;
    btn.disabled = true;
    try {
      var r = await fetch('/api/design/config', { method: 'PUT', headers: headers(), body: JSON.stringify(collect()) });
      var d = await r.json();
      if (!r.ok) throw new Error(d.detail || '儲存失敗');
      config = d.config;
      renderAll();
      $('#preview').contentWindow.location.reload();
      toast('已儲存並套用到前台');
    } catch (err) { toast(err.message, true); }
    finally { btn.disabled = false; }
  });

  $('#btn-reset').addEventListener('click', async function () {
    if (!confirm('確定把所有文案與樣式還原成預設值？此動作無法復原。')) return;
    try {
      var r = await fetch('/api/design/reset', { method: 'POST', headers: headers() });
      var d = await r.json();
      if (!r.ok) throw new Error(d.detail || '還原失敗');
      config = d.config;
      renderAll();
      $('#preview').contentWindow.location.reload();
      toast('已還原為預設值');
    } catch (err) { toast(err.message, true); }
  });

  /* ---------------- 快速配色 ---------------- */
  var PRESETS = {
    warm: {},
    blue: { page_bg_from: '#eaeef4', page_bg_to: '#d6dde8', paper: '#fbfcfe', composer_bg: '#eef2f8',
            ink: '#1f2a37', muted: '#6b7684', line: '#22303f', accent: '#1f5fa8', accent_soft: '#d9e6f6',
            title_color: '#1f2a37', subtitle_color: '#6b7684', brand_color: '#6b7684', beta_color: '#1f2a37',
            btn_bg: '#1f5fa8', btn_text: '#ffffff', newchat_bg: '#1f5fa8', newchat_text: '#ffffff',
            category_text: '#1f2a37', category_bg: '#fbfcfe', message_bg: '#ffffff', message_text: '#1f2a37',
            user_msg_bg: '#d9e6f6', disclaimer_color: '#8a94a1' },
    green: { page_bg_from: '#eaf1ea', page_bg_to: '#d7e2d7', paper: '#fbfdfa', composer_bg: '#eef4ee',
             ink: '#22302a', muted: '#6c7a71', line: '#26362e', accent: '#2f7d5b', accent_soft: '#d8ecdf',
             title_color: '#22302a', subtitle_color: '#6c7a71', brand_color: '#6c7a71', beta_color: '#22302a',
             btn_bg: '#2f7d5b', btn_text: '#ffffff', newchat_bg: '#2f7d5b', newchat_text: '#ffffff',
             category_text: '#22302a', category_bg: '#fbfdfa', message_bg: '#ffffff', message_text: '#22302a',
             user_msg_bg: '#d8ecdf', disclaimer_color: '#8a9891' },
    dark: { page_bg_from: '#1b1e24', page_bg_to: '#12151a', paper: '#20242b', composer_bg: '#1a1e24',
            ink: '#e8e6e2', muted: '#9aa0aa', line: '#39404a', accent: '#ff7a4d', accent_soft: '#3a2a22',
            title_color: '#f2f0ec', subtitle_color: '#9aa0aa', brand_color: '#9aa0aa', beta_color: '#e8e6e2',
            btn_bg: '#ff7a4d', btn_text: '#1b1e24', newchat_bg: '#ff7a4d', newchat_text: '#1b1e24',
            category_text: '#e8e6e2', category_bg: '#20242b', message_bg: '#272c34', message_text: '#e8e6e2',
            user_msg_bg: '#3a2a22', disclaimer_color: '#7f858e' }
  };

  function applyPreset(name) {
    var preset = PRESETS[name];
    if (!preset) return;
    if (name === 'warm') {
      themeFields.forEach(function (f) {
        if (f.kind === 'color') setThemeValue(f.key, f.default);
      });
    } else {
      Object.keys(preset).forEach(function (key) { setThemeValue(key, preset[key]); });
    }
    schedulePreview();
    toast('已套用配色，記得按「儲存並套用」');
  }

  function setThemeValue(key, value) {
    var text = document.querySelector('[data-theme="' + key + '"]');
    if (text) text.value = value;
    var color = document.querySelector('[data-color-for="' + key + '"]');
    if (color && /^#[0-9a-fA-F]{6}$/.test(String(value))) color.value = value;
  }

  /* ---------------- 原始 CSS 檔編輯 ---------------- */
  var cssFiles = [], cssLoaded = false, currentFile = '', savedContent = '', rawTimer = null;

  function fileDirty() {
    return !!currentFile && $('#file-editor').value !== savedContent;
  }

  function renderFileChips() {
    $('#file-picker').innerHTML = cssFiles.map(function (f) {
      var cls = 'file-chip' + (f.name === currentFile ? ' active' : '') + (f.modified ? ' changed' : '');
      return '<button type="button" class="' + cls + '" data-file="' + esc(f.name) + '" title="' + esc(f.label) + '">'
        + '<span class="dot"></span>' + esc(f.name) + ' <em>' + Math.round(f.bytes / 1024 * 10) / 10 + ' KB</em></button>';
    }).join('');
  }

  async function loadCssList() {
    try {
      var r = await fetch('/api/design/css', { headers: headers() });
      if (!r.ok) throw new Error('讀取失敗');
      cssFiles = (await r.json()).files || [];
      cssLoaded = true;
      renderFileChips();
      if (!currentFile && cssFiles.length) openFile(cssFiles[0].name);
    } catch (err) { toast('讀取 CSS 檔清單失敗', true); }
  }

  async function openFile(name) {
    if (fileDirty() && !confirm('「' + currentFile + '」有尚未儲存的修改，要放棄並切換嗎？')) return;
    try {
      var r = await fetch('/api/design/css/' + encodeURIComponent(name), { headers: headers() });
      var d = await r.json();
      if (!r.ok) throw new Error(d.detail || '讀取失敗');
      currentFile = name;
      savedContent = d.content;
      $('#file-editor').value = d.content;
      $('#file-name').textContent = d.name;
      $('#file-label').textContent = d.label + (d.modified ? '　·　已被修改過' : '');
      $('#file-save').disabled = false;
      $('#file-restore').disabled = !d.has_backup;
      renderFileChips();
      applyRawPreview();
    } catch (err) { toast(err.message, true); }
  }

  function applyRawPreview() {
    if (!currentFile) return;
    var doc = $('#preview').contentDocument;
    if (!doc || !doc.head) return;
    var target = null;
    doc.querySelectorAll('link[rel="stylesheet"]').forEach(function (link) {
      if ((link.getAttribute('href') || '').indexOf('/' + currentFile) >= 0) target = link;
    });
    var id = 'sc-raw-' + currentFile.replace(/[^a-z0-9]+/gi, '-');
    var style = doc.getElementById(id);
    if (!target) { if (style) style.remove(); return; }
    if (!style) {
      style = doc.createElement('style');
      style.id = id;
      target.parentNode.insertBefore(style, target.nextSibling);
    }
    target.disabled = true;
    style.textContent = $('#file-editor').value;
  }

  function scheduleRawPreview() {
    clearTimeout(rawTimer);
    rawTimer = setTimeout(applyRawPreview, 400);
  }

  $('#file-editor').addEventListener('input', scheduleRawPreview);

  $('#file-save').addEventListener('click', async function () {
    if (!currentFile) return;
    var btn = this;
    btn.disabled = true;
    try {
      var r = await fetch('/api/design/css/' + encodeURIComponent(currentFile), {
        method: 'PUT', headers: headers(),
        body: JSON.stringify({ content: $('#file-editor').value })
      });
      var d = await r.json();
      if (!r.ok) throw new Error(d.detail || '儲存失敗');
      savedContent = d.content;
      $('#file-label').textContent = d.label + (d.modified ? '　·　已被修改過' : '');
      $('#file-restore').disabled = !d.has_backup;
      await loadCssList();
      $('#preview').contentWindow.location.reload();
      toast(currentFile + ' 已儲存並套用');
    } catch (err) { toast(err.message, true); }
    finally { btn.disabled = false; }
  });

  $('#file-restore').addEventListener('click', async function () {
    if (!currentFile) return;
    if (!confirm('確定把 ' + currentFile + ' 還原成最初的原始版本？目前的修改會全部消失。')) return;
    try {
      var r = await fetch('/api/design/css/' + encodeURIComponent(currentFile) + '/restore',
        { method: 'POST', headers: headers() });
      var d = await r.json();
      if (!r.ok) throw new Error(d.detail || '還原失敗');
      savedContent = d.content;
      $('#file-editor').value = d.content;
      $('#file-label').textContent = d.label;
      await loadCssList();
      $('#preview').contentWindow.location.reload();
      toast(currentFile + ' 已還原成原始版本');
    } catch (err) { toast(err.message, true); }
  });

  document.addEventListener('click', function (e) {
    var chip = e.target.closest('.file-chip');
    if (chip) openFile(chip.dataset.file);
    var filesTab = e.target.closest('.tab[data-tab="files"]');
    if (filesTab && !cssLoaded) loadCssList();
  });

  window.addEventListener('beforeunload', function (e) {
    if (fileDirty()) { e.preventDefault(); e.returnValue = ''; }
  });

  if (token) start();
})();
