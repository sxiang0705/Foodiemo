import {getJSON, errorMessage} from './api.js';
const $ = id => document.getElementById(id);
const state = {page: 1, q: '', category: ''};
let listRequest, detailRequest, currentId, reviewPage = 1;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function card(r) {
  const node = el('button', undefined, 'card');
  node.type = 'button';
  node.setAttribute('aria-label', `查看 ${r.name}`);
  const placeholder = el('div', undefined, 'placeholder');
  placeholder.append(el('span', '◌', 'symbol'), el('span', '尚無餐廳照片'));
  const content = el('div', undefined, 'card-content');
  const meta = el('div', undefined, 'meta');
  meta.append(el('span', `來源評論數 ${r.review_count}`), el('span', '查看詳情 ↗'));
  content.append(el('span', r.category || '分類未提供', 'chip'), el('h3', r.name),
    el('p', r.address || '地址未提供', 'address'), meta);
  node.append(placeholder, content);
  node.addEventListener('click', () => {
    const url = new URL(location.href); url.searchParams.set('restaurant', r.id);
    history.pushState({}, '', url); openDetail(r.id);
  });
  return node;
}
function syncURL() {
  const params = new URLSearchParams();
  if (state.q) params.set('q', state.q);
  if (state.category) params.set('category', state.category);
  if (state.page > 1) params.set('page', state.page);
  history.replaceState({}, '', `/${params.size ? '?' + params : ''}`);
}
async function loadList() {
  listRequest?.abort();
  const controller = new AbortController(); listRequest = controller;
  $('restaurants').replaceChildren(); $('result-count').textContent = '';
  $('list-status').textContent = '正在尋找好味道…'; $('retry').hidden = true;
  $('previous').disabled = true; $('next').disabled = true; $('page-label').textContent = '';
  try {
    const data = await getJSON(`/api/v1/restaurants?${new URLSearchParams({...state, page_size: 12})}`, controller.signal);
    if (controller.signal.aborted) return;
    $('restaurants').replaceChildren(...data.items.map(card));
    $('list-status').textContent = data.items.length ? '' : '沒有符合條件的餐廳。試試其他店名、地址或分類。';
    $('result-count').textContent = `共 ${data.total} 間餐廳`;
    $('page-label').textContent = `第 ${data.page} 頁`;
    $('previous').disabled = data.page <= 1;
    $('next').disabled = data.page * data.page_size >= data.total;
  } catch (error) {
    if (controller.signal.aborted) return;
    $('list-status').textContent = errorMessage(error); $('retry').hidden = false;
  }
}
function fact(dl, label, value) { dl.append(el('dt', label), el('dd', value || '未提供')); }
async function loadReviews(id, page, controller) {
  const target = $('reviews'); if (!target) return;
  target.textContent = '正在載入原始餐廳評論…';
  $('review-prev').disabled = true; $('review-next').disabled = true;
  try {
    const data = await getJSON(`/api/v1/restaurants/${id}/reviews?page=${page}&page_size=10`, controller.signal);
    if (controller.signal.aborted || id !== currentId) return;
    target.replaceChildren(...data.items.map(r => el('p', r.text, 'review')));
    if (!data.items.length) target.textContent = '尚無保存的原始評論';
    $('review-page').textContent = `第 ${page} 頁 · 已保存 ${data.total} 則`;
    $('review-prev').disabled = page <= 1;
    $('review-next').disabled = page * data.page_size >= data.total;
  } catch (error) {
    if (controller.signal.aborted) return;
    target.replaceChildren(el('p', errorMessage(error)));
    const retry = el('button', '重試評論', 'secondary');
    retry.onclick = () => loadReviews(id, page, controller); target.append(retry);
  }
}
async function openDetail(id) {
  detailRequest?.abort(); const controller = new AbortController(); detailRequest = controller;
  currentId = id; reviewPage = 1;
  $('detail-body').replaceChildren(el('h2', '正在載入…'));
  $('detail-body').firstChild.id = 'detail-title';
  if (!$('detail').open) $('detail').showModal();
  try {
    const r = await getJSON(`/api/v1/restaurants/${id}`, controller.signal);
    if (controller.signal.aborted) return;
    const title = el('h2', r.name); title.id = 'detail-title';
    const dl = el('dl');
    fact(dl, '分類', r.category); fact(dl, '地址', r.address); fact(dl, '電話', r.phone);
    fact(dl, '評分', '未提供'); fact(dl, '價位', '未提供');
    fact(dl, '網站', r.website);
    // Website values are untrusted. Only absolute http(s) becomes a link.
    try {
      const url = new URL(r.website);
      if (['https:', 'http:'].includes(url.protocol)) {
        const link = el('a', '前往餐廳網站 ↗'); link.href = url.href;
        link.target = '_blank'; link.rel = 'noopener noreferrer'; dl.lastChild.replaceChildren(link);
      }
    } catch { /* Keep missing/invalid URLs as safe text. */ }
    const hours = el('ul');
    // Inventory only establishes weekday range 0..6, not Sunday/Monday convention.
    for (const h of r.business_hours) hours.append(el('li',
      `星期資訊待確認：${h.is_closed ? '公休' : `${h.open_time || '未提供'} – ${h.close_time || '未提供'}`}`));
    if (!r.business_hours.length) hours.append(el('li', '營業時間未提供'));
    const reviews = el('div'); reviews.id = 'reviews';
    const controls = el('div', undefined, 'review-controls');
    const previous = el('button', '上一頁', 'secondary'); previous.id = 'review-prev';
    const next = el('button', '下一頁', 'secondary'); next.id = 'review-next';
    const label = el('span'); label.id = 'review-page';
    previous.onclick = () => loadReviews(id, --reviewPage, controller);
    next.onclick = () => loadReviews(id, ++reviewPage, controller);
    controls.append(previous, label, next);
    $('detail-body').replaceChildren(title, el('p', '尚無餐廳照片', 'detail-note'), dl,
      el('h3', '營業時間'), hours, el('h3', '原始餐廳評論'),
      el('p', `來源評論數 ${r.review_count}，與本平台保存筆數可能不同。原始評分與發布時間未提供。`, 'detail-note'), reviews, controls);
    await loadReviews(id, reviewPage, controller);
  } catch (error) {
    if (controller.signal.aborted) return;
    const title = el('h2', '無法載入餐廳'); title.id = 'detail-title';
    const retry = el('button', '重新載入', 'secondary'); retry.onclick = () => openDetail(id);
    $('detail-body').replaceChildren(title, el('p', errorMessage(error)), retry);
  }
}
function closeDetail() {
  detailRequest?.abort(); currentId = null; $('detail').close();
  const url = new URL(location.href); url.searchParams.delete('restaurant');
  history.replaceState({}, '', url);
}
$('close-detail').onclick = closeDetail;
$('detail').addEventListener('cancel', event => {event.preventDefault(); closeDetail();});
$('search-form').onsubmit = event => {
  event.preventDefault(); state.q = $('query').value.trim(); state.category = $('category').value.trim();
  state.page = 1; syncURL(); loadList();
};
$('previous').onclick = () => {state.page--; syncURL(); loadList();};
$('next').onclick = () => {state.page++; syncURL(); loadList();};
$('retry').onclick = loadList;
function restore() {
  const params = new URLSearchParams(location.search);
  state.q = params.get('q') || ''; state.category = params.get('category') || '';
  const page = Number(params.get('page') || 1);
  state.page = Number.isInteger(page) && page >= 1 && page <= 10000 ? page : 1;
  $('query').value = state.q; $('category').value = state.category;
  loadList();
  const id = params.get('restaurant');
  if (id) openDetail(encodeURIComponent(id));
  else {detailRequest?.abort(); $('detail').close();}
}
addEventListener('popstate', restore);
restore();
