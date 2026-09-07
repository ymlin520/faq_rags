/* 前台文案套用：由 /api/site-config 讀取「外觀後台」設定並覆寫頁面文字。 */
(function () {
  window.SITE_CONFIG = null;

  function applyText(cfg) {
    var text = (cfg && cfg.text) || {};
    document.querySelectorAll('[data-sc]').forEach(function (el) {
      var value = text[el.dataset.sc];
      if (typeof value === 'string' && value !== '') el.textContent = value;
    });
    document.querySelectorAll('[data-sc-placeholder]').forEach(function (el) {
      var value = text[el.dataset.scPlaceholder];
      if (typeof value === 'string' && value !== '') el.placeholder = value;
    });
    if (text.page_title) document.title = text.page_title;
  }

  function applySuggestions(cfg) {
    var box = document.getElementById('sc-suggestions');
    var rows = (cfg && cfg.suggestions) || [];
    if (!box || !rows.length) return;
    box.innerHTML = rows.map(function (row) {
      var label = String(row.label || '');
      var query = String(row.query || row.label || '');
      var d = document.createElement('div');
      d.textContent = query;
      var q = d.innerHTML;
      d.textContent = label;
      return '<button data-example="' + q + '">' + d.innerHTML + '</button>';
    }).join('');
  }

  /* 分類顯示名稱覆寫（key = 知識庫分類名稱，label = 前台顯示文字）。 */
  window.scCategoryOverride = function () {
    var rows = (window.SITE_CONFIG && window.SITE_CONFIG.categories) || [];
    return rows.filter(function (r) { return r && r.label; });
  };
  window.scCategoryLabel = function (key) {
    var rows = window.scCategoryOverride();
    for (var i = 0; i < rows.length; i++) {
      if ((rows[i].query || rows[i].label) === key) return rows[i].label;
    }
    return null;
  };

  window.SITE_CONFIG_READY = fetch('/api/site-config', { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () { return null; })
    .then(function (cfg) {
      if (!cfg) return null;
      window.SITE_CONFIG = cfg;
      applyText(cfg);
      applySuggestions(cfg);
      return cfg;
    });
})();
