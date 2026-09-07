const $ = s => document.querySelector(s);
const ADMIN_TOKEN_KEY = 'school-faq-admin-token';
const PAGE_SIZE = 50;
const FIELDS = ['id', 'category', 'question', 'answer', 'url', 'keywords', 'office', 'email'];
let token = localStorage.getItem(ADMIN_TOKEN_KEY) || '';
let faqs = [], summary = {}, preview = null, source = 'url', page = 1, editingId = null;

const esc = v => { const n = document.createElement('div'); n.textContent = v ?? ''; return n.innerHTML };
const headers = () => ({ 'X-Admin-Token': token });
const jsonHeaders = () => ({ ...headers(), 'Content-Type': 'application/json' });
const msg = (el, text, ok) => { const n = $(el); n.textContent = text; n.className = text ? (ok ? 'ok' : 'err') : '' };
const cut = (v, n) => { const t = String(v || '').replace(/\s+/g, ' '); return t.length > n ? t.slice(0, n) + '…' : t };
async function detail(response) { const d = await response.json().catch(() => ({})); return d.detail || `操作失敗（${response.status}）` }

/* ----------------------------------------------------------------- 讀取與統計 */

async function load() {
  const response = await fetch('/api/admin/faqs', { headers: headers() });
  if (!response.ok) throw new Error(response.status === 401 ? '管理密碼不正確' : await detail(response));
  const data = await response.json();
  faqs = data.faqs; summary = data.summary;
  renderSummary(); renderFilters(); renderList();
}

function renderSummary() {
  $('#stats').className = 'stats stats-4';
  $('#stats').innerHTML = `<article><span>常見問題總數</span><strong>${summary.total.toLocaleString()}</strong><small>已建立向量，前台可搜尋</small></article>
<article><span>分類數</span><strong>${summary.categories.length}</strong><small>${esc(summary.categories.slice(0, 2).map(x => `${x.name}（${x.total}）`).join('、')) || '尚未分類'}</small></article>
<article><span>主責單位</span><strong>${summary.offices.length}</strong><small>${esc(summary.offices.slice(0, 2).map(x => `${x.name}（${x.total}）`).join('、')) || '尚未填寫'}</small></article>
<article class="accent"><span>最後更新</span><strong style="font-size:20px">${esc(summary.updated_at || '—')}</strong><small>data/faq.csv（台灣時間）</small></article>`;
}

function fillOptions(select, values, keep) {
  const current = keep ? select.value : '';
  select.innerHTML = `<option value="">${select.dataset.all}</option>` + values.map(v => `<option>${esc(v)}</option>`).join('');
  select.value = values.includes(current) ? current : '';
}

function renderFilters() {
  const categories = summary.categories.map(x => x.name), offices = summary.offices.map(x => x.name);
  fillOptions($('#category-filter'), categories, true);
  fillOptions($('#office-filter'), offices, true);
  $('#category-list').innerHTML = categories.map(v => `<option value="${esc(v)}">`).join('');
  $('#office-list').innerHTML = offices.map(v => `<option value="${esc(v)}">`).join('');
}

/* ----------------------------------------------------------------- FAQ 清單 */

function filtered() {
  const keyword = $('#search').value.trim().toLowerCase();
  const category = $('#category-filter').value, office = $('#office-filter').value;
  return faqs.filter(x =>
    (!category || (x.category || '未分類') === category) && (!office || x.office === office) &&
    (!keyword || FIELDS.some(f => String(x[f] || '').toLowerCase().includes(keyword))));
}

function renderList() {
  const rows = filtered(), pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  page = Math.min(Math.max(1, page), pages);
  const slice = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  $('#count').textContent = rows.length === faqs.length ? `共 ${faqs.length} 筆` : `符合 ${rows.length} 筆／共 ${faqs.length} 筆`;
  $('#rows').innerHTML = slice.length ? slice.map(x => `<tr><td class="id">${esc(x.id)}</td><td>${esc(x.category) || '<span class="muted">未分類</span>'}</td>
<td><span class="q">${esc(x.question)}</span><small class="a">${esc(cut(x.answer, 90))}</small></td><td>${esc(x.office) || '—'}</td>
<td>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">開啟 ↗</a>` : '—'}</td>
<td><button class="edit" data-edit="${esc(x.id)}" type="button">編輯 →</button></td></tr>`).join('')
    : '<tr><td colspan="6">沒有符合條件的常見問題</td></tr>';
  $('#page-info').textContent = `第 ${page} / ${pages} 頁`;
  $('#prev').disabled = page <= 1; $('#next').disabled = page >= pages;
}

/* ----------------------------------------------------------------- 匯入 */

async function runPreview() {
  const body = new FormData();
  if (source === 'file') {
    const file = $('#src-file').files[0];
    if (!file) return msg('#import-msg', '請先選擇檔案。', false);
    body.append('file', file);
  } else if (source === 'url') {
    if (!$('#src-url').value.trim()) return msg('#import-msg', '請先輸入試算表網址。', false);
    body.append('url', $('#src-url').value.trim());
  } else {
    if (!$('#src-text').value.trim()) return msg('#import-msg', '請先貼上資料。', false);
    body.append('text', $('#src-text').value);
  }
  const button = $('#preview'); button.disabled = true; button.textContent = '讀取中…';
  msg('#import-msg', '正在讀取來源資料…', true);
  try {
    const response = await fetch('/api/admin/faqs/preview', { method: 'POST', headers: headers(), body });
    if (!response.ok) throw new Error(await detail(response));
    preview = await response.json();
    renderPreview();
    msg('#import-msg', `已讀取「${preview.source}」共 ${preview.rows.length} 列，確認下方內容後再按「確認匯入」。`, true);
  } catch (error) {
    preview = null; $('#preview-box').hidden = true;
    msg('#import-msg', error.message, false);
  } finally { button.disabled = false; button.textContent = '讀取並預覽' }
}

function renderPreview() {
  const { counts, rows, header, existing_total: existing } = preview;
  $('#preview-box').hidden = false;
  $('#counts').innerHTML = `<span class="create">新增 ${counts.create}</span><span class="update">更新既有 ${counts.update}</span><span class="skip">略過 ${counts.skip}</span><span>目前知識庫 ${existing} 筆</span>`;
  $('#mapping').innerHTML = '對應到的欄位：' + FIELDS.filter(f => header[f]).map(f => `<code>${esc(header[f])}</code> → ${f}`).join('　') +
    (FIELDS.some(f => !header[f]) ? `　（未提供：${FIELDS.filter(f => !header[f]).join('、')}）` : '');
  $('#preview-rows').innerHTML = rows.map((x, index) => `<tr class="${x.action}">
<td class="pick">${x.action === 'skip' ? '' : `<input type="checkbox" data-row="${index}" checked>`}</td><td>${x.row}</td>
<td class="id">${esc(x.id)}</td><td>${esc(cut(x.category, 14))}</td><td><span class="cell">${esc(x.question)}</span></td>
<td><span class="cell">${esc(cut(x.answer, 120))}</span></td><td>${esc(x.office)}</td>
<td><b class="act ${x.action}">${x.action === 'create' ? '新增' : x.action === 'update' ? '更新' : '略過'}</b><small class="a">${esc(x.note)}</small></td></tr>`).join('');
  $('#pick-all').checked = true;
  msg('#commit-msg', '', true);
}

function pickedRows() {
  return [...document.querySelectorAll('#preview-rows [data-row]:checked')]
    .map(input => Object.fromEntries(FIELDS.map(f => [f, preview.rows[Number(input.dataset.row)][f]])));
}

async function commitImport() {
  const rows = pickedRows();
  if (!rows.length) return msg('#commit-msg', '請至少勾選一列。', false);
  const mode = document.querySelector('input[name=mode]:checked').value;
  const warning = mode === 'replace'
    ? `「完全取代」會刪掉目前知識庫的 ${preview.existing_total} 筆資料，只留下勾選的 ${rows.length} 筆。確定要繼續嗎？`
    : `確定匯入 ${rows.length} 筆？同編號的內容會被覆蓋。`;
  if (!confirm(warning)) return;
  const button = $('#commit'); button.disabled = true; button.textContent = '匯入中…';
  msg('#commit-msg', '正在寫入 CSV 並重新產生向量，資料量大時需要幾十秒，請不要關閉視窗。', true);
  try {
    const response = await fetch('/api/admin/faqs/import', { method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ rows, mode }) });
    if (!response.ok) throw new Error(await detail(response));
    const result = await response.json();
    await load();
    $('#preview-box').hidden = true; preview = null;
    msg('#import-msg', `匯入完成：新增 ${result.created} 筆、更新 ${result.updated} 筆，知識庫現有 ${result.total} 筆。${result.backup ? `舊檔已備份為 data/faq-backups/${result.backup}。` : ''}`, true);
  } catch (error) {
    msg('#commit-msg', error.message, false);
  } finally { button.disabled = false; button.textContent = '確認匯入' }
}

/* ----------------------------------------------------------------- 單筆編輯 */

function openEditor(faq) {
  editingId = faq ? faq.id : null;
  const value = field => (faq ? faq[field] || '' : '');
  $('#edit-mode').textContent = faq ? `問題編號 ${faq.id}` : '新增';
  $('#edit-title').textContent = faq ? '編輯常見問題' : '新增常見問題';
  FIELDS.forEach(field => { $(`#f-${field}`).value = value(field) });
  $('#delete').hidden = !faq;
  msg('#edit-msg', '', true);
  $('#editor').showModal();
  $('#f-question').focus();
}

async function saveEditor(event) {
  event.preventDefault();
  const payload = Object.fromEntries(FIELDS.map(field => [field, $(`#f-${field}`).value.trim()]));
  if (!payload.question || !payload.answer) return msg('#edit-msg', '問題與建議答案不可空白。', false);
  const button = $('#edit-form .save'); button.disabled = true;
  msg('#edit-msg', '儲存中，正在更新向量…', true);
  try {
    const url = editingId ? `/api/admin/faqs/${encodeURIComponent(editingId)}` : '/api/admin/faqs';
    const response = await fetch(url, { method: editingId ? 'PUT' : 'POST', headers: jsonHeaders(), body: JSON.stringify(payload) });
    if (!response.ok) throw new Error(await detail(response));
    await load();
    $('#editor').close();
  } catch (error) { msg('#edit-msg', error.message, false) } finally { button.disabled = false }
}

async function removeFaq() {
  if (!editingId || !confirm(`確定刪除「${$('#f-question').value}」？此動作會同時移除向量資料。`)) return;
  msg('#edit-msg', '刪除中…', true);
  const response = await fetch(`/api/admin/faqs/${encodeURIComponent(editingId)}`, { method: 'DELETE', headers: headers() });
  if (!response.ok) return msg('#edit-msg', await detail(response), false);
  await load();
  $('#editor').close();
}

/* ----------------------------------------------------------------- 登入與事件 */

async function enterAdmin() {
  await load();
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
  $('#login').hidden = true; $('#app').hidden = false; $('#logout').hidden = false; $('#login-error').textContent = '';
}

async function download(path, filename) {
  if (!token) return alert('請先登入');
  const response = await fetch(path, { headers: headers() });
  if (!response.ok) return alert(await detail(response));
  const anchor = document.createElement('a');
  anchor.href = URL.createObjectURL(await response.blob());
  anchor.download = filename; anchor.click();
  URL.revokeObjectURL(anchor.href);
}

$('#login-form').onsubmit = async event => {
  event.preventDefault(); token = $('#token').value;
  try { await enterAdmin() } catch (error) { localStorage.removeItem(ADMIN_TOKEN_KEY); $('#login-error').textContent = error.message }
};
$('#logout').onclick = () => { localStorage.removeItem(ADMIN_TOKEN_KEY); token = ''; location.reload() };

document.querySelectorAll('.tab').forEach(tab => tab.onclick = () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x === tab));
  source = tab.dataset.source;
  document.querySelectorAll('.source').forEach(panel => { panel.hidden = panel.dataset.panel !== source });
  msg('#import-msg', '', true);
});

$('#preview').onclick = runPreview;
$('#commit').onclick = commitImport;
$('#cancel').onclick = () => { $('#preview-box').hidden = true; preview = null; msg('#import-msg', '', true) };
$('#pick-all').onchange = event => document.querySelectorAll('#preview-rows [data-row]').forEach(input => { input.checked = event.target.checked });
$('#template').onclick = () => download('/api/admin/faqs/template.csv', 'faq-template.csv');
$('#export').onclick = () => download('/api/admin/faqs.csv', 'faq.csv');

$('#search').oninput = () => { page = 1; renderList() };
$('#category-filter').onchange = () => { page = 1; renderList() };
$('#office-filter').onchange = () => { page = 1; renderList() };
$('#prev').onclick = () => { page -= 1; renderList() };
$('#next').onclick = () => { page += 1; renderList() };
$('#add').onclick = () => openEditor(null);
$('#reindex').onclick = async () => {
  if (!confirm('重新計算所有常見問題的向量？資料多時需要一到數分鐘。')) return;
  const button = $('#reindex'); button.disabled = true; button.textContent = '重建中…';
  const response = await fetch('/api/admin/faqs/reindex', { method: 'POST', headers: headers() });
  button.disabled = false; button.textContent = '重建向量';
  alert(response.ok ? `已重建 ${(await response.json()).indexed} 筆向量。` : await detail(response));
};

$('#rows').onclick = event => {
  const button = event.target.closest('[data-edit]');
  if (button) openEditor(faqs.find(x => x.id === button.dataset.edit));
};
$('#edit-form').onsubmit = saveEditor;
$('#edit-close').onclick = () => $('#editor').close();
$('#delete').onclick = removeFaq;

$('#category-filter').dataset.all = '所有分類';
$('#office-filter').dataset.all = '所有主責單位';
if (token) enterAdmin().catch(() => {
  localStorage.removeItem(ADMIN_TOKEN_KEY); token = '';
  $('#login').hidden = false; $('#app').hidden = true;
  $('#login-error').textContent = '已儲存的管理密碼失效，請重新登入。';
});
