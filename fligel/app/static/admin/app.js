// Флигель — интерфейс администратора. Без сборки и зависимостей.

import { plural, count, humanDay, dateRange, moneyize, holidayName, skeleton, SOURCE_ABBR } from './ui.js';

// ---------- утилиты ----------
const $app = document.getElementById('app');

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  let money = false;
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'money') { money = true; continue; }
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') el.innerHTML = v;
    else if (k in el && typeof v !== 'string') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  if (money) moneyize(el);
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const ICONS = {
  board: '<path d="M3 5h18v14H3z M3 10h18 M8 5v14 M13 5v14" fill="none" stroke="currentColor" stroke-width="1.7"/>',
  today: '<circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" stroke="currentColor" stroke-width="1.7"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
  rates: '<path d="M3 12V4h8l10 10-8 8L3 12z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><circle cx="7.5" cy="8" r="1.5" fill="currentColor"/>',
  channels: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  stats: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  settings: '<circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" fill="none" stroke="currentColor" stroke-width="1.5"/>',
  plus: '<path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  left: '<path d="M15 6l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  right: '<path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  close: '<path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  sync: '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5 15V5a1 1 0 0 1 1-1h10" fill="none" stroke="currentColor" stroke-width="1.8"/>',
  expenses: '<rect x="2.5" y="6" width="19" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M2.5 10h19" stroke="currentColor" stroke-width="1.7"/><circle cx="7" cy="14.5" r="1.4" fill="currentColor"/>',
  trash: '<path d="M4 7h16M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7M6 7l1 13h10l1-13" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4 20h16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  download: '<path d="M12 3v13M7 11l5 5 5-5M4 20h16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  search: '<circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M20 20l-4.3-4.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  print: '<path d="M6 9V3h12v6M6 18H4a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-2M6 14h12v7H6z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
  bell: '<path d="M6 10a6 6 0 0 1 12 0c0 4 1.5 5.5 2 6.5H4c.5-1 2-2.5 2-6.5Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M10 19a2 2 0 0 0 4 0" fill="none" stroke="currentColor" stroke-width="1.7"/>',
  more: '<path d="M5 12h.01M12 12h.01M19 12h.01" stroke="currentColor" stroke-width="3.4" stroke-linecap="round"/>',
  help: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.1.9-1.1 1.8M12 17h.01" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  users: '<circle cx="9" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M3.5 19c.9-3.2 3-4.8 5.5-4.8s4.6 1.6 5.5 4.8M16 5.5a3 3 0 0 1 0 5.4M17.5 14.5c1.7.6 2.9 2.1 3.5 4.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  phone: '<path d="M6.5 3.5h3l1.5 4-2 1.3a11 11 0 0 0 5.2 5.2l1.3-2 4 1.5v3a2 2 0 0 1-2.2 2A15.5 15.5 0 0 1 4.5 5.7 2 2 0 0 1 6.5 3.5z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
  clean: '<path d="M12 3v3M12 18v3M5 12H2M22 12h-3M6.3 6.3 4.2 4.2M19.8 19.8l-2.1-2.1M17.7 6.3l2.1-2.1M4.2 19.8l2.1-2.1" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><path d="M12 8.5l1.2 2.3 2.3 1.2-2.3 1.2L12 15.5l-1.2-2.3L8.5 12l2.3-1.2z" fill="currentColor"/>',
  user: '<circle cx="12" cy="8" r="3.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M4.5 20c1.2-4 4-6 7.5-6s6.3 2 7.5 6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
};
const icon = (name) => { const s = h('span'); s.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`; return s.firstChild; };

const WD = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
const MONTHS_NOM = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const SOURCE = {
  manual: 'Вручную', direct: 'Сайт', avito: 'Авито', yandex: 'Яндекс', sutochno: 'Суточно', ostrovok: 'Островок', other: 'Другое',
};
const STATUS = { confirmed: 'Подтверждена', pending: 'Заявка', blocked: 'Даты закрыты', cancelled: 'Отменена' };
const ROLE = { owner: 'Владелец', manager: 'Администратор', housekeeper: 'Горничная', landlord: 'Собственник' };

const pad = (n) => String(n).padStart(2, '0');
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseISO = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
const addDays = (s, n) => { const d = parseISO(s); d.setDate(d.getDate() + n); return iso(d); };
const diffDays = (a, b) => Math.round((parseISO(b) - parseISO(a)) / 86400000);
const todayISO = () => iso(new Date());
const fmtDate = (s) => { const d = parseISO(s); return `${d.getDate()} ${MONTHS[d.getMonth()]}`; };
const fmtShort = (s) => { const d = parseISO(s); return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}`; };
const fmtMoney = (v) => `${Math.round(Number(v || 0)).toLocaleString('ru-RU')} ₽`;
const fmtPriceCell = (v) => { const n = Math.round(Number(v || 0)); return n >= 10000 ? `${(n / 1000).toFixed(n % 1000 ? 1 : 0).replace('.', ',')}к` : n.toLocaleString('ru-RU'); };
const nightsWord = (n) => { const m10 = n % 10, m100 = n % 100; if (m10 === 1 && m100 !== 11) return 'ночь'; if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return 'ночи'; return 'ночей'; };
const fmtDateTime = (s) => { if (!s) return '—'; const d = new Date(s); return `${pad(d.getDate())}.${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const ago = (s) => {
  if (!s) return 'ещё не было';
  const min = Math.round((Date.now() - new Date(s)) / 60000);
  if (min < 1) return 'только что'; if (min < 60) return `${min} мин назад`;
  const hr = Math.round(min / 60); if (hr < 24) return `${hr} ч назад`;
  return fmtDateTime(s);
};

const loadingBox = () => h('div', { class: 'card' }, skeleton(5));

function toast(msg, bad = false) {
  const t = h('div', { class: 'toast' + (bad ? ' bad' : '') }, msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), bad ? 5000 : 2800);
}

// Уведомление с кнопкой «Отменить»: действие уже выполнено, но его можно вернуть в течение нескольких секунд
function toastUndo(msg, undo, after, seconds = 8) {
  const t = h('div', { class: 'toast with-undo' }, h('span', {}, msg),
    h('button', { class: 'toast-undo', type: 'button', onclick: async () => {
      t.remove();
      try { await undo(); toast('Возвращено'); after?.(); } catch (ex) { toast(ex.message, true); }
    } }, 'Отменить'));
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), seconds * 1000);
}

// Тема оформления: «как в системе» / светлая / тёмная (хранится в браузере)
function applyTheme() {
  const t = (() => { try { return localStorage.getItem('theme') || 'auto'; } catch { return 'auto'; } })();
  if (t === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', t);
}
applyTheme();

const store = {
  get(k, def = null) { try { return localStorage.getItem(k) ?? def; } catch { return def; } },
  set(k, v) { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* приватный режим */ } },
};

// ---------- API ----------
class ApiError extends Error { constructor(msg, status, data) { super(msg); this.status = status; this.data = data; } }

async function api(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const token = store.get('token');
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError('Нет связи с сервером. Проверьте интернет', 0, {});
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && token) { store.set('token', null); state.me = null; render(); }
  if (!res.ok) throw new ApiError(data.error || `Ошибка ${res.status}`, res.status, data);
  return data;
}
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString();

// ---------- состояние и маршруты ----------
const state = {
  me: null,
  propertyId: store.get('propertyId'),
  boardFrom: null,
  boardDays: parseInt(store.get('board_days', ''), 10) || (window.innerWidth < 860 ? 14 : 31),
  conflicts: 0,
  requests: 0,
  financeKind: store.get('finance_kind', 'expense'),
};

const ROUTES = {
  board: { title: 'Шахматка', icon: 'board', view: viewBoard, landlord: true },
  today: { title: 'Сегодня', icon: 'today', view: viewToday },
  cleaning: { title: 'Уборка', icon: 'clean', view: viewCleaning },
  bookings: { title: 'Брони', icon: 'list', view: viewBookings, role: 'manager' },
  guests: { title: 'Гости', icon: 'users', view: viewGuests, role: 'manager' },
  rates: { title: 'Цены', icon: 'rates', view: viewRates, role: 'manager' },
  channels: { title: 'Площадки', icon: 'channels', view: viewChannels, role: 'manager' },
  expenses: { title: 'Финансы', icon: 'expenses', view: viewExpenses, role: 'manager' },
  stats: { title: 'Отчёты', icon: 'stats', view: viewStats, role: 'manager' },
  notifications: { title: 'Уведомления', icon: 'bell', view: viewNotifications, role: 'manager' },
  settings: { title: 'Настройки', icon: 'settings', view: viewSettings, role: 'owner' },
  profile: { title: 'Профиль', icon: 'user', view: viewProfile, landlord: true },
  ownerreport: { title: 'Отчёт собственнику', icon: 'stats', view: viewOwnerReport, roles: ['landlord', 'manager', 'owner'] },
  help: { title: 'Справка', icon: 'help', view: viewHelp, landlord: true },
};
// Собственник видит только шахматку (чтение), свой отчёт, справку и профиль; остальные — по ролям
const routeVisible = (d) => (d.roles ? d.roles.includes(state.me.role) : (state.me.role === 'landlord' ? !!d.landlord : (!d.role || can(d.role))));
const RANK = { landlord: -1, housekeeper: 0, manager: 1, owner: 2 };
const MOBILE_ORDER = ['board', 'today', 'cleaning', 'bookings', 'guests', 'expenses', 'channels', 'notifications', 'settings', 'rates', 'stats', 'ownerreport', 'help', 'profile'];
const LANDLORD_ORDER = ['ownerreport', 'board', 'help', 'profile'];
const can = (role) => state.me && RANK[state.me.role] >= RANK[role];
const currentRoute = () => { const home = { housekeeper: 'cleaning', landlord: 'ownerreport' }[state.me?.role] || (window.innerWidth < 860 && can('manager') ? 'today' : 'board'); const r = location.hash.replace(/^#\/?/, '').split('?')[0] || home; return ROUTES[r] ? r : home; };

window.addEventListener('hashchange', () => render());

// Горячие клавиши: работают, когда курсор не в поле ввода и не открыто окно
const HOTKEYS = [['← →', 'Шахматка: неделя назад / вперёд'], ['T', 'Шахматка: перейти к сегодняшнему дню'], ['N', 'Новая бронь'],
  ['/', 'Поиск гостя'], ['G, затем Ш / С / Б / У', 'Перейти: шахматка / сегодня / брони / уборка'], ['?', 'Показать эту подсказку'], ['Esc', 'Закрыть окно']];
function hotkeysDialog() {
  openModal('Горячие клавиши', h('table', { class: 'list' }, h('tbody', {}, HOTKEYS.map(([k, t]) => h('tr', {}, h('td', {}, h('kbd', {}, k)), h('td', {}, t))))),
    [h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: () => closeModal(true) }, 'Понятно')]);
}
let goPending = false;
document.addEventListener('keydown', (e) => {
  if (!state.me || e.ctrlKey || e.metaKey || e.altKey) return;
  const t = e.target;
  if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
  if (modalEl || drawerEl) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (goPending) {
    goPending = false;
    const to = { 'ш': 'board', 'п': 'today', 'с': 'today', 'б': 'bookings', 'у': 'cleaning', b: 'board', t: 'today', k: 'bookings', c: 'cleaning' }[k];
    if (to && ROUTES[to] && routeVisible(ROUTES[to])) { e.preventDefault(); location.hash = `#/${to}`; }
    return;
  }
  if (k === '?' ) { e.preventDefault(); hotkeysDialog(); }
  else if (k === 'g' || k === 'п') goPending = true, setTimeout(() => { goPending = false; }, 1500);
  else if (boardActions && k === 'ArrowLeft') { e.preventDefault(); boardActions.shift(-7); }
  else if (boardActions && k === 'ArrowRight') { e.preventDefault(); boardActions.shift(7); }
  else if (boardActions && (k === 't' || k === 'е')) boardActions.today();
  else if (can('manager') && (k === 'n' || k === 'т')) { e.preventDefault(); bookingDrawer({}, () => render()); }
  else if (can('manager') && (k === '/' || k === '.')) { e.preventDefault(); guestSearchDrawer(); }
});

async function boot() {
  if (store.get('token')) {
    try { state.me = await api('GET', '/api/me'); } catch { state.me = null; }
  }
  render();
}

// Счётчики в меню (заявки с сайта, конфликты площадок) и автообновление экранов: два сотрудника
// работают одновременно, и новая бронь/заявка должна появиться у другого без перезагрузки страницы.
async function refreshBadges() {
  if (!state.me || !can('manager')) return;
  try {
    const b = await api('GET', '/api/badges');
    state.requests = b.requests; state.conflicts = b.conflicts; updateTitle();
    document.querySelectorAll('[data-badge]').forEach((el) => {
      const n = state[el.dataset.badge] || 0;
      el.textContent = n; el.style.display = n ? '' : 'none';
    });
  } catch { /* сеть пропала — попробуем в следующий раз */ }
}
let autoTimer = null;
let autoFn = null;
function autoRefresh(fn, seconds = 45) {
  clearInterval(autoTimer);
  autoFn = fn;
  autoTimer = setInterval(() => {
    // не мешаем, пока человек что-то делает: открыто окно/панель, идёт перетаскивание, вкладка скрыта
    if (document.hidden || drawerEl || modalEl || document.querySelector('.bar.dragging, .bar.lifted')) return;
    fn();
  }, seconds * 1000);
}
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && state.me) { refreshBadges(); if (autoFn && !drawerEl && !modalEl) autoFn(); }
});
setInterval(() => { if (!document.hidden) refreshBadges(); }, 60000);

let baseTitle = 'Флигель';
// Число новых заявок видно прямо во вкладке браузера: «(3) Брони — Флигель»
function updateTitle() { document.title = (state.requests ? `(${state.requests}) ` : '') + baseTitle; }

function render() {
  closeDrawer();
  closeModal();
  clearInterval(autoTimer); autoFn = null; boardActions = null;
  $app.innerHTML = '';
  if (location.hash.startsWith('#/reset-password')) return $app.append(viewResetPassword());
  if (!state.me) return $app.append(viewAuth());
  if (!state.me.properties.length) return $app.append(viewWizard());
  if (!state.me.properties.find((p) => p.id === state.propertyId)) state.propertyId = state.me.properties[0].id;
  const route = currentRoute();
  const def = ROUTES[route];
  baseTitle = `${def.title} — Флигель`;
  updateTitle();
  const main = h('main', { class: 'main' });
  $app.append(layout(route, main));
  if (!routeVisible(def)) {
    main.append(h('div', { class: 'card empty' }, h('h3', {}, 'Раздел недоступен'), 'Попросите владельца расширить ваши права.'));
    return;
  }
  def.view(main);
  refreshBadges();
}

// Переход к брони из поиска: переключаемся на её объект, открываем шахматку на нужных датах
// и сразу показываем карточку брони.
async function jumpToBooking(b) {
  closeDrawer();
  state.propertyId = b.property_id; store.set('propertyId', b.property_id);
  state.boardFrom = addDays(b.check_in, -2);
  location.hash = '#/board';
  render();
  boardData = null;
  try { await ensureBoardData(); } catch { /* карточка всё равно откроется */ }
  bookingDrawer(b, () => render());
}

function guestSearchDrawer() {
  const input = h('input', { class: 'input', placeholder: 'Имя, телефон или email гостя', autocomplete: 'off' });
  const results = h('div', { style: { marginTop: '12px' } });
  let timer;
  const search = async () => {
    const q = input.value.trim();
    if (q.length < 2) { results.innerHTML = ''; return; }
    results.innerHTML = '';
    results.append(h('div', { class: 'muted small' }, 'Ищу…'));
    try {
      const rows = await api('GET', '/api/bookings?' + qs({
        q, from: addDays(todayISO(), -365), to: addDays(todayISO(), 35),
      }));
      results.innerHTML = '';
      if (!rows.length) { results.append(h('div', { class: 'empty' }, 'Ничего не найдено')); return; }
      results.append(...rows.slice(0, 30).map((b) => h('div', {
        class: 'item', style: { cursor: 'pointer', padding: '10px 2px', borderBottom: '1px solid var(--line)' },
        onclick: () => jumpToBooking(b),
      }, h('div', { style: { fontWeight: 600 } }, b.guest_name || `Гость с площадки ${SOURCE[b.source]}`),
        h('div', { class: 'muted small' }, `${b.property_name} · ${b.room_name} · ${fmtShort(b.check_in)} — ${fmtShort(b.check_out)}`,
          b.guest_phone ? ` · ${b.guest_phone}` : ''))));
    } catch (ex) { results.innerHTML = ''; results.append(h('div', { class: 'empty' }, ex.message)); }
  };
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, 250); });
  openDrawer('Поиск гостя', h('div', {}, input, results));
  setTimeout(() => input.focus(), 60);
}

function layout(route, main) {
  const visible = Object.entries(ROUTES).filter(([, d]) => routeVisible(d));
  if (state.me.role === 'landlord') visible.sort((a, b2) => LANDLORD_ORDER.indexOf(a[0]) - LANDLORD_ORDER.indexOf(b2[0]));
  const BADGE = { bookings: 'requests', channels: 'conflicts' };
  const link = ([key, d]) => h('a', { href: `#/${key}`, class: key === route ? 'active' : '' }, icon(d.icon), h('span', {}, d.title),
    BADGE[key] ? h('span', { class: 'badge', 'data-badge': BADGE[key], style: { display: state[BADGE[key]] ? '' : 'none' } }, state[BADGE[key]] || 0) : null);
  const prop = state.me.properties.find((p) => p.id === state.propertyId);
  const sideSearchBtn = can('manager') ? h('button', { class: 'btn icon ghost', title: 'Поиск гостя', 'aria-label': 'Поиск гостя', style: { color: '#C3CCC0' }, onclick: guestSearchDrawer }, icon('search')) : null;
  const mobileSearchBtn = can('manager') ? h('button', { class: 'btn icon ghost', title: 'Поиск гостя', 'aria-label': 'Поиск гостя', style: { marginLeft: 'auto', color: '#fff' }, onclick: guestSearchDrawer }, icon('search')) : null;
  // На телефоне в нижней панели помещается 5 пунктов: четыре главных и «Ещё» со всеми остальными разделами.
  const ordered = (state.me.role === 'landlord' ? LANDLORD_ORDER : MOBILE_ORDER).map((k) => visible.find(([v]) => v === k)).filter(Boolean);
  const mainItems = ordered.length <= 5 ? ordered : ordered.slice(0, 4);
  const rest = ordered.slice(mainItems.length);
  const moreBtn = rest.length ? h('button', { class: 'more-btn' + (rest.some(([k]) => k === route) ? ' active' : ''), onclick: () => moreSheet(rest, route) },
    icon('more'), h('span', {}, 'Ещё')) : null;
  return h('div', { class: 'shell' },
    h('aside', { class: 'side' },
      h('div', { class: 'brand' }, h('div', { class: 'brand-mark' }),
        h('div', { style: { flex: 1, minWidth: 0 } }, h('div', { class: 'brand-name' }, 'Флигель'),
        propertySwitcher('prop-switch') || h('div', { class: 'brand-sub' }, prop ? prop.name : '')),
        sideSearchBtn),
      h('nav', { class: 'nav' }, visible.map(link)),
      h('div', { class: 'side-foot' }, h('b', {}, state.me.name), ROLE[state.me.role],
        h('br'), h('button', { onclick: logout }, 'Выйти'), ' · ', h('button', { class: 'desk-only', title: 'Горячие клавиши', onclick: hotkeysDialog }, '⌨'), ' · ', h('button', { title: 'Светлая / тёмная тема', onclick: () => { const dark = getComputedStyle(document.documentElement).colorScheme === 'dark'; store.set('theme', dark ? 'light' : 'dark'); applyTheme(); } }, 'Тема'))),
    h('div', {},
      h('div', { class: 'mobile-top' }, h('div', { class: 'brand-mark' }),
        propertySwitcher('prop-switch') || h('div', { class: 'brand-name' }, prop ? prop.name : 'Флигель'),
        mobileSearchBtn,
        h('button', { class: 'btn small ghost', style: { color: '#fff' }, onclick: logout }, 'Выйти')),
      main),
    h('nav', { class: 'mobile-nav', 'aria-label': 'Разделы' }, mainItems.map(link), moreBtn));
}

// Все разделы, не поместившиеся в нижнюю панель телефона
function moreSheet(items, route) {
  openModal('Разделы', h('div', { class: 'more-grid' },
    items.map(([key, d]) => h('a', { href: `#/${key}`, class: key === route ? 'active' : '', onclick: () => closeModal() }, icon(d.icon), d.title))),
  [h('button', { class: 'btn', onclick: () => closeModal() }, 'Закрыть'), h('span', { class: 'spacer' }),
    h('span', { class: 'muted small' }, `${state.me.name} · ${ROLE[state.me.role]}`)]);
}

function logout() { store.set('token', null); state.me = null; location.hash = ''; render(); }

function switchProperty(id) {
  if (id === state.propertyId) return;
  state.propertyId = id; store.set('propertyId', id);
  boardData = null;
  render();
}

function propertySwitcher(cls) {
  if (state.me.properties.length < 2) return null;
  return h('select', { class: cls, onchange: (e) => switchProperty(e.target.value), 'aria-label': 'Объект' },
    state.me.properties.map((p) => h('option', { value: p.id, selected: p.id === state.propertyId }, p.name)));
}

// Список объектов для выбора «Этот объект / Все объекты» на страницах, где это уместно.
function scopeSeg(scope, onChange) {
  if (state.me.properties.length < 2) return null;
  // «Этот объект / Все объекты» запоминается и одинаков на всех экранах
  if (store.get('scope') === 'all') scope.value = 'all';
  const btnCurrent = h('button', {
    type: 'button', class: scope.value === 'current' ? 'on' : '',
    onclick: () => { scope.value = 'current'; store.set('scope', 'current'); btnCurrent.classList.add('on'); btnAll.classList.remove('on'); onChange(); },
  }, 'Этот объект');
  const btnAll = h('button', {
    type: 'button', class: scope.value === 'all' ? 'on' : '',
    onclick: () => { scope.value = 'all'; store.set('scope', 'all'); btnAll.classList.add('on'); btnCurrent.classList.remove('on'); onChange(); },
  }, 'Все объекты');
  return h('div', { class: 'seg' }, btnCurrent, btnAll);
}

// ---------- вход и регистрация ----------
function viewAuth() {
  let mode = location.hash === '#register' ? 'register' : 'login';
  const wrap = h('div', { class: 'auth' });
  const colors = ['#2F5D50', '#6E4A93', '#B7791F', '#23767E', '#4A5A6A'];
  const mini = h('div', { class: 'mini-board' });
  for (let r = 0; r < 8; r++) {
    let c = 0;
    while (c < 14) {
      if (Math.random() < 0.45) {
        const len = Math.min(14 - c, 2 + Math.floor(Math.random() * 4));
        const color = colors[(r + c) % colors.length];
        mini.append(h('i', { style: { gridColumn: `span ${len}`, background: color, opacity: 0.85 } }));
        c += len;
      } else { mini.append(h('i')); c += 1; }
    }
  }
  const art = h('div', { class: 'auth-art' },
    h('div', { class: 'brand' }, h('div', { class: 'brand-mark' }), h('div', { class: 'brand-name' }, 'Флигель')),
    h('div', {}, mini,
      h('h2', {}, 'Все брони с Авито, Яндекса и сайта в одной шахматке'),
      h('p', {}, 'Календари площадок синхронизируются сами, а занять номер дважды система не даст.')),
    h('div', { class: 'small', style: { color: '#7F8E7B' } }, 'Данные хранятся на серверах в России'));
  const formBox = h('div', { class: 'auth-form' });

  const draw = () => {
    formBox.innerHTML = '';
    const err = h('div', { class: 'note bad', style: { display: 'none' } });
    const f = {};
    const field = (key, label, type = 'text', auto) => h('label', { class: 'field' }, h('span', {}, label),
      f[key] = h('input', { class: 'input', type, name: key, autocomplete: auto, required: true }));
    const submit = h('button', { class: 'btn primary', type: 'submit', style: { width: '100%', height: '40px' } },
      mode === 'login' ? 'Войти' : 'Создать аккаунт');
    const form = h('form', {
      onsubmit: async (e) => {
        e.preventDefault();
        submit.disabled = true; err.style.display = 'none';
        try {
          const payload = Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.value]));
          const res = await api('POST', mode === 'login' ? '/api/auth/login' : '/api/auth/register', payload);
          store.set('token', res.token);
          state.me = await api('GET', '/api/me');
          location.hash = '#/' + currentRoute();
          render();
        } catch (ex) {
          err.textContent = ex.message; err.style.display = 'block';
          if (ex.data?.field && f[ex.data.field]) f[ex.data.field].classList.add('invalid');
        } finally { submit.disabled = false; }
      },
    },
    h('h1', {}, mode === 'login' ? 'Вход' : 'Регистрация'),
    h('p', { class: 'muted', style: { marginTop: 0, marginBottom: '20px' } },
      mode === 'login' ? 'Войдите, чтобы открыть шахматку.' : 'Займёт минуту. Потом добавим номера.'),
    err,
    mode === 'register' ? [field('account_name', 'Название гостиницы или компании'), field('name', 'Ваше имя', 'text', 'name')] : null,
    field('email', 'Email', 'email', 'email'),
    field('password', mode === 'login' ? 'Пароль' : 'Пароль (не короче 8 символов)', 'password', mode === 'login' ? 'current-password' : 'new-password'),
    submit,
    mode === 'register' ? h('p', { class: 'small muted', style: { marginTop: '10px' } },
      'Регистрируясь, вы принимаете ', h('a', { href: '/legal/terms', target: '_blank', rel: 'noopener' }, 'условия использования'),
      ', ', h('a', { href: '/legal/privacy', target: '_blank', rel: 'noopener' }, 'политику конфиденциальности'),
      ' и даёте ', h('a', { href: '/legal/pdn-consent', target: '_blank', rel: 'noopener' }, 'согласие на обработку персональных данных'), '.') : null,
    mode === 'login' ? h('div', { class: 'switch' },
      h('button', { type: 'button', onclick: () => forgotPasswordDrawer(f.email?.value) }, 'Забыли пароль?')) : null,
    h('div', { class: 'switch' }, mode === 'login' ? 'Ещё нет аккаунта? ' : 'Уже есть аккаунт? ',
      h('button', { type: 'button', onclick: () => { mode = mode === 'login' ? 'register' : 'login'; draw(); } },
        mode === 'login' ? 'Зарегистрироваться' : 'Войти')));
    formBox.append(h('div', {}, h('div', { class: 'brand auth-mobile-brand' }, h('div', { class: 'brand-mark' }), h('div', { class: 'brand-name' }, 'Флигель')), form));
  };
  draw();
  wrap.append(art, formBox);
  return wrap;
}

function forgotPasswordDrawer(prefillEmail) {
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const ok = h('div', { class: 'note ok', style: { display: 'none' } });
  const email = h('input', { class: 'input', type: 'email', required: true, value: prefillEmail || '' });
  const submit = h('button', { class: 'btn primary', onclick: async () => {
    submit.disabled = true; err.style.display = 'none';
    try {
      const r = await api('POST', '/api/auth/forgot-password', { email: email.value });
      ok.textContent = r.message; ok.style.display = 'block'; email.disabled = true; submit.disabled = true;
    } catch (ex) { err.textContent = ex.message; err.style.display = 'block'; submit.disabled = false; }
  } }, 'Отправить ссылку');
  openDrawer('Восстановление пароля', h('div', {}, err, ok,
    h('label', { class: 'field' }, h('span', {}, 'Email'), email)), [h('span', { class: 'spacer' }), submit]);
}

function viewResetPassword() {
  const token = new URLSearchParams(location.hash.split('?')[1] || '').get('token') || '';
  const wrap = h('div', { class: 'auth' });
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const ok = h('div', { class: 'note ok', style: { display: 'none' } });
  const password = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', required: true });
  const form = h('form', { class: 'auth-form', onsubmit: async (e) => {
    e.preventDefault(); err.style.display = 'none';
    try {
      const r = await api('POST', '/api/auth/reset-password', { token, password: password.value });
      ok.textContent = r.message; ok.style.display = 'block'; form.style.display = 'none';
      setTimeout(() => { location.hash = ''; render(); }, 2500);
    } catch (ex) { err.textContent = ex.message; err.style.display = 'block'; }
  } },
  h('h1', {}, 'Новый пароль'),
  h('p', { class: 'muted', style: { marginTop: 0, marginBottom: '20px' } }, 'Придумайте новый пароль для входа.'),
  err, ok,
  h('label', { class: 'field' }, h('span', {}, 'Новый пароль (не короче 8 символов)'), password),
  h('button', { class: 'btn primary', type: 'submit', style: { width: '100%', height: '40px', marginTop: '14px' } }, 'Сохранить'));
  wrap.append(h('div', {}, h('div', { class: 'brand auth-mobile-brand' }, h('div', { class: 'brand-mark' }), h('div', { class: 'brand-name' }, 'Флигель')), form));
  if (!token) { err.textContent = 'Ссылка неверна: не хватает кода. Запросите восстановление пароля заново.'; err.style.display = 'block'; form.querySelector('button').disabled = true; }
  return wrap;
}

// ---------- мастер первого запуска ----------
function viewWizard() {
  const types = [{ name: 'Стандарт', count: 8, capacity: 2, base_price: 3500 }, { name: 'Делюкс', count: 4, capacity: 3, base_price: 5500 }];
  const f = {};
  const list = h('div');
  const total = h('span', { class: 'muted' });
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const drawTypes = () => {
    list.innerHTML = '';
    types.forEach((t, i) => {
      const inp = (key, label, type = 'text') => h('label', { class: 'field' }, h('span', {}, label),
        h('input', { class: 'input', type, value: t[key], min: type === 'number' ? 0 : null, oninput: (e) => { t[key] = e.target.value; recount(); } }));
      list.append(h('div', { class: 'type-row' }, inp('name', 'Категория'), inp('count', 'Номеров', 'number'),
        inp('capacity', 'Гостей', 'number'), inp('base_price', 'Цена за ночь', 'number'),
        h('button', { class: 'btn icon ghost del', type: 'button', title: 'Убрать категорию', 'aria-label': 'Убрать категорию', style: { marginBottom: '10px' }, disabled: types.length === 1,
          onclick: () => { types.splice(i, 1); drawTypes(); } }, icon('close'))));
    });
    recount();
  };
  const recount = () => { const n = types.reduce((s, t) => s + (Number(t.count) || 0), 0); total.textContent = `Всего номеров: ${n}. Нумерация с ${f.first?.value || 101}.`; };
  const submit = h('button', { class: 'btn primary', type: 'submit' }, 'Создать шахматку');
  const form = h('form', {
    class: 'card card-pad',
    onsubmit: async (e) => {
      e.preventDefault(); submit.disabled = true; err.style.display = 'none';
      try {
        const prop = await api('POST', '/api/setup', {
          name: f.name.value, address: f.address.value, phone: f.phone.value, first_number: f.first.value, room_types: types,
        });
        state.me = await api('GET', '/api/me');
        state.propertyId = prop.id; store.set('propertyId', prop.id);
        location.hash = '#/board'; render();
        toast('Готово: номера созданы');
      } catch (ex) { err.textContent = ex.message; err.style.display = 'block'; } finally { submit.disabled = false; }
    },
  },
  h('h2', { style: { marginBottom: '14px' } }, 'Объект'),
  err,
  h('label', { class: 'field' }, h('span', {}, 'Название'), f.name = h('input', { class: 'input', required: true, value: state.me.account_name })),
  h('div', { class: 'row2' },
    h('label', { class: 'field' }, h('span', {}, 'Адрес'), f.address = h('input', { class: 'input' })),
    h('label', { class: 'field' }, h('span', {}, 'Телефон для гостей'), f.phone = h('input', { class: 'input', type: 'tel' }))),
  h('h2', { style: { margin: '10px 0 14px' } }, 'Номера'),
  list,
  h('div', { style: { display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', margin: '4px 0 18px' } },
    h('button', { class: 'btn small', type: 'button', onclick: () => { types.push({ name: '', count: 1, capacity: 2, base_price: 3000 }); drawTypes(); } }, icon('plus'), 'Категория'),
    h('label', { class: 'check small' }, 'Первый номер', f.first = h('input', { class: 'input', type: 'number', value: 101, style: { width: '90px', height: '32px' }, oninput: recount })),
    total),
  submit);
  drawTypes();
  return h('div', { class: 'wizard' },
    h('div', { class: 'brand', style: { marginBottom: '18px', padding: 0 } }, h('div', { class: 'brand-mark' }), h('div', { class: 'brand-name', style: { color: 'var(--ink)' } }, 'Флигель')),
    h('h1', { style: { marginBottom: '6px' } }, 'Добавим ваш объект'),
    h('p', { class: 'muted', style: { marginTop: 0, marginBottom: '20px' } }, 'Категории номеров и цены можно поменять потом в настройках.'),
    form);
}

// ---------- боковая панель ----------
let drawerEl = null;
let drawerDirty = false;
let drawerOnDismiss = null;
function closeDrawer() { if (drawerEl) { drawerEl.remove(); drawerEl = null; drawerDirty = false; drawerOnDismiss = null; document.removeEventListener('keydown', escClose); } }
// Закрытие по желанию человека (крестик, фон, Esc, «Закрыть»): если в форме есть несохранённые правки — переспросить
function requestCloseDrawer() {
  if (drawerDirty && !(drawerOnDismiss ? drawerOnDismiss() : confirm('У вас есть несохранённые изменения. Закрыть без сохранения?'))) return false;
  closeDrawer();
  return true;
}
function escClose(e) { if (e.key === 'Escape') requestCloseDrawer(); }
// opts.guard — следить за несохранёнными правками; opts.onDismiss — свой вопрос при закрытии (true = закрывать)
function openDrawer(title, body, foot, opts = {}) {
  closeDrawer();
  drawerDirty = false;
  drawerOnDismiss = opts.onDismiss || null;
  drawerEl = h('div', {},
    h('div', { class: 'drawer-back', onclick: requestCloseDrawer }),
    h('div', { class: 'drawer', role: 'dialog', 'aria-label': title },
      h('div', { class: 'drawer-head' }, h('h2', {}, title), h('button', { class: 'btn icon ghost', onclick: requestCloseDrawer, 'aria-label': 'Закрыть' }, icon('close'))),
      h('div', { class: 'drawer-body' }, body),
      foot ? h('div', { class: 'drawer-foot' }, foot) : null));
  if (opts.guard) {
    const mark = (e) => { if (!e.target.closest?.('.money-box')) drawerDirty = true; };
    drawerEl.addEventListener('input', mark);
    drawerEl.addEventListener('change', mark);
  }
  document.body.append(drawerEl);
  document.addEventListener('keydown', escClose);
  setTimeout(() => drawerEl?.querySelector('input:not([type=hidden]):not([readonly]), select')?.focus(), 50);
}

// ---------- шахматка ----------
let boardData = null;
let boardActions = null; // действия шахматки для горячих клавиш

// «Быстрый старт»: чек-лист для нового аккаунта на шахматке, пока не всё настроено
async function drawOnboarding(box) {
  let o;
  try { o = await api('GET', '/api/onboarding'); } catch { return; }
  if (o.done >= o.total) return;
  const bookingUrl = o.booking_page_slug ? `${location.origin}/book/${o.booking_page_slug}` : null;
  const next = o.steps.find((st) => !st.done);
  box.append(h('div', { class: 'card card-pad onboard' },
    h('div', { class: 'onboard-head' }, h('div', {}, h('h3', {}, 'Быстрый старт'), h('div', { class: 'muted small' }, `Настроено ${o.done} из ${o.total} — так сервис начнёт приносить пользу сразу`)),
      h('button', { class: 'btn small ghost', onclick: () => { store.set('onboardHidden', '1'); box.innerHTML = ''; } }, 'Скрыть')),
    h('div', { class: 'bar-h', style: { margin: '10px 0 12px' } }, h('i', { style: { width: `${(o.done / o.total) * 100}%`, background: 'var(--pine)' } })),
    next ? h('a', { class: 'btn primary onboard-next', href: `#/${next.route}` }, `Дальше: ${next.title}`, icon('right')) : null,
    h('button', { class: 'btn small onboard-toggle', onclick: (e) => { const el = e.target.parentNode.querySelector('.onboard-steps'); el.classList.toggle('open'); e.target.textContent = el.classList.contains('open') ? 'Свернуть шаги' : 'Все шаги'; } }, o.done <= 2 ? 'Свернуть шаги' : 'Все шаги'),
    h('div', { class: 'onboard-steps' + (o.done <= 2 ? ' open' : '') }, o.steps.map((st) => h('a', { class: 'onboard-step' + (st.done ? ' done' : ''), href: `#/${st.route}` },
      h('span', { class: 'chk' }, st.done ? '✓' : ''), h('span', {}, st.title)))),
    bookingUrl ? h('div', { class: 'muted small', style: { marginTop: '10px' } }, 'Ваша страница бронирования для гостей: ', h('a', { href: bookingUrl, target: '_blank', rel: 'noopener' }, bookingUrl)) : null));
}

// Ширина клетки шахматки зависит от масштаба: 2 недели — крупно, 3 месяца — мелко
function applyZoom() {
  const narrow = window.innerWidth < 860;
  const w = { 14: narrow ? 46 : 60, 31: narrow ? 38 : 44, 92: narrow ? 20 : 26 }[state.boardDays] || 44;
  document.documentElement.style.setProperty('--cell', `${w}px`);
}
const hiddenTypes = () => { try { return new Set(JSON.parse(store.get('board_hidden', '[]'))); } catch { return new Set(); } };

async function viewBoard(main) {
  if (!state.boardFrom) state.boardFrom = addDays(todayISO(), -2);
  applyZoom();
  const head = h('div', { class: 'page-head' }, h('h1', {}, 'Шахматка'));
  let dateIn;
  const tools = h('div', { class: 'board-tools' },
    h('button', { class: 'btn icon', title: 'Раньше (←)', 'aria-label': 'Неделю назад', onclick: () => shift(-7) }, icon('left')),
    h('button', { class: 'btn', onclick: () => { state.boardFrom = addDays(todayISO(), -2); load(); } }, 'Сегодня'),
    h('button', { class: 'btn icon', title: 'Позже (→)', 'aria-label': 'Неделю вперёд', onclick: () => shift(7) }, icon('right')),
    dateIn = h('input', { class: 'input', type: 'date', style: { width: '150px' }, value: state.boardFrom, onchange: (e) => { if (e.target.value) { state.boardFrom = e.target.value; load(); } } }),
    h('div', { class: 'seg zoom-seg', role: 'group', 'aria-label': 'Масштаб' }, [[14, '2 нед', 'Две недели'], [31, 'Месяц', 'Месяц'], [92, '3 мес', 'Три месяца']].map(([n, l, t]) =>
      h('button', { type: 'button', class: state.boardDays === n ? 'on' : '', title: t, onclick: (e) => {
        state.boardDays = n; store.set('board_days', String(n)); applyZoom();
        e.currentTarget.parentNode.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === e.currentTarget)); load();
      } }, l))),
    can('manager') ? h('button', { class: 'btn primary', onclick: () => bookingDrawer({}) }, icon('plus'), 'Бронь') : null);
  head.append(tools);
  const banner = h('div');
  const typeFilter = h('div', { class: 'type-filter' });
  const onboard = h('div');
  const card = h('div', { class: 'card board-card' }, skeleton(9, 'board'));
  main.append(head, onboard, banner, typeFilter, card);
  if (can('manager') && !store.get('onboardHidden')) drawOnboarding(onboard);

  const shift = (n) => { state.boardFrom = addDays(state.boardFrom, n); load(); };
  boardActions = { shift, today: () => { state.boardFrom = addDays(todayISO(), -2); load(); } };
  const load = async () => {
    dateIn.value = state.boardFrom;
    try {
      boardData = await api('GET', (state.me.role === 'landlord' ? '/api/landlord/board?' : '/api/board?') + qs({ property_id: state.propertyId, from: state.boardFrom, days: state.boardDays }));
      state.conflicts = boardData.open_conflicts;
      banner.innerHTML = '';
      if (boardData.open_conflicts) {
        banner.append(h('div', { class: 'banner' }, h('b', {}, '!'),
          h('div', {}, `С площадок пришли брони на уже занятые даты: ${boardData.open_conflicts}. `,
            h('a', { href: '#/channels' }, 'Разобрать конфликты'))));
      }
      // при автообновлении не сбрасываем прокрутку шахматки
      const old = card.querySelector('.board-scroll');
      const pos = old ? [old.scrollLeft, old.scrollTop] : null;
      card.innerHTML = '';
      const hidden = hiddenTypes();
      typeFilter.innerHTML = '';
      if (boardData.room_types.length > 1) {
        typeFilter.append(h('span', { class: 'muted small' }, 'Категории:'), ...boardData.room_types.map((t) => h('button', { type: 'button', class: 'chip' + (hidden.has(t.id) ? '' : ' on'), onclick: () => {
          const hs = hiddenTypes(); if (hs.has(t.id)) hs.delete(t.id); else hs.add(t.id);
          if (hs.size >= boardData.room_types.length) hs.clear();
          store.set('board_hidden', JSON.stringify([...hs])); load();
        } }, t.name)));
      }
      card.append(drawBoard({ ...boardData, room_types: boardData.room_types.filter((t) => !hidden.has(t.id)) }, load));
      const fresh = card.querySelector('.board-scroll');
      if (pos && fresh) { fresh.scrollLeft = pos[0]; fresh.scrollTop = pos[1]; }
    } catch (ex) { if (!card.querySelector('.board')) { card.innerHTML = ''; card.append(h('div', { class: 'empty' }, ex.message)); } }
  };
  load();
  autoRefresh(load);
}

// Перенос брони перетаскиванием (в другой номер и/или на другие даты) и изменение длины за
// край полоски. Мышь: потянуть сразу. Касание (телефон): сначала долгое нажатие на полоску,
// затем перетащить — иначе нельзя было бы прокручивать шахматку пальцем. После отпускания
// ничего не сохраняется сразу: открывается окно подтверждения с новыми датами и ценой.
// Брони с площадок (b.feed_id) не перетаскиваются — их даты меняются на площадке.
function bindBarDrag(bar, b, room, draggable, ctx) {
  const { days, cellW, roomRows, reload } = ctx;
  let st = null;
  let justDragged = false;
  let pressTimer = null;
  const begin = (ev, mode, active) => {
    st = {
      mode, active, startX: ev.clientX, startY: ev.clientY, moved: false, startCheckIn: b.check_in, startCheckOut: b.check_out,
      roomId: b.room_id, curRoomId: b.room_id, resultCheckIn: b.check_in, resultCheckOut: b.check_out,
    };
  };
  bar.addEventListener('pointerdown', (ev) => {
    ev.stopPropagation();
    if (!draggable || ev.button !== 0) return;
    if (ev.pointerType === 'mouse') {
      const rect = bar.getBoundingClientRect();
      const edge = 10;
      begin(ev, ev.clientX - rect.left < edge ? 'left' : rect.right - ev.clientX < edge ? 'right' : 'move', true);
      bar.setPointerCapture(ev.pointerId);
    } else {
      begin(ev, 'move', false);
      pressTimer = setTimeout(() => {
        if (!st) return;
        st.active = true;
        bar.classList.add('lifted');
        if (navigator.vibrate) navigator.vibrate(12);
        try { bar.setPointerCapture(ev.pointerId); } catch { /* уже отпущено */ }
      }, 380);
    }
  });
  // Пока полоска «поднята» долгим нажатием, шахматка не должна прокручиваться вслед за пальцем
  bar.addEventListener('touchmove', (ev) => { if (st && st.active) ev.preventDefault(); }, { passive: false });
  bar.addEventListener('contextmenu', (ev) => { if (draggable) ev.preventDefault(); });
  bar.addEventListener('pointermove', (ev) => {
    if (!st) return;
    const dx = ev.clientX - st.startX;
    if (!st.active) {
      // палец поехал до долгого нажатия — это обычная прокрутка, а не перенос
      if (Math.abs(dx) > 8 || Math.abs(ev.clientY - st.startY) > 8) { clearTimeout(pressTimer); st = null; }
      return;
    }
    const dayDelta = Math.round(dx / cellW);
    let curCheckIn = st.startCheckIn, curCheckOut = st.startCheckOut;
    if (st.mode === 'move') {
      curCheckIn = addDays(st.startCheckIn, dayDelta);
      curCheckOut = addDays(st.startCheckOut, dayDelta);
    } else if (st.mode === 'left') {
      curCheckIn = addDays(st.startCheckIn, dayDelta);
      if (diffDays(curCheckIn, st.startCheckOut) < 1) curCheckIn = addDays(st.startCheckOut, -1);
    } else {
      curCheckOut = addDays(st.startCheckOut, dayDelta);
      if (diffDays(st.startCheckIn, curCheckOut) < 1) curCheckOut = addDays(st.startCheckIn, 1);
    }
    let curRoomId = st.curRoomId;
    if (st.mode === 'move') {
      const hit = roomRows.find((rr) => { const r = rr.track.getBoundingClientRect(); return ev.clientY >= r.top && ev.clientY < r.bottom; });
      if (hit) curRoomId = hit.room.id;
    }
    if (Math.abs(dx) > 3 || curRoomId !== st.roomId) st.moved = true;
    if (!st.moved) return;
    bar.classList.add('dragging');
    const ns = diffDays(days[0], curCheckIn), ne = diffDays(days[0], curCheckOut);
    bar.style.left = `${(ns + 0.5) * cellW + 2}px`;
    bar.style.width = `${Math.max((ne - ns) * cellW - 4, 12)}px`;
    if (curRoomId !== st.curRoomId) {
      const hit = roomRows.find((rr) => rr.room.id === curRoomId);
      if (hit) hit.track.append(bar);
    }
    st.curRoomId = curRoomId;
    st.resultCheckIn = curCheckIn;
    st.resultCheckOut = curCheckOut;
  });
  const finish = (ev) => {
    clearTimeout(pressTimer);
    if (!st) return;
    const done = st; st = null;
    bar.classList.remove('dragging', 'lifted');
    try { bar.releasePointerCapture(ev.pointerId); } catch { /* уже отпущено */ }
    if (!done.active || !done.moved) return;
    justDragged = true;
    setTimeout(() => { justDragged = false; }, 400);
    const change = {};
    if (done.resultCheckIn !== done.startCheckIn) change.check_in = done.resultCheckIn;
    if (done.resultCheckOut !== done.startCheckOut) change.check_out = done.resultCheckOut;
    if (done.curRoomId !== done.roomId) change.room_id = done.curRoomId;
    if (!Object.keys(change).length) { reload(); return; }
    moveDialog(b, change, reload);
  };
  bar.addEventListener('pointerup', finish);
  bar.addEventListener('pointercancel', finish);
  bar.addEventListener('click', (ev) => {
    if (state.me.role === 'landlord') return;
    if (justDragged) { justDragged = false; ev.preventDefault(); return; }
    bookingDrawer(b, reload);
  });
}

// ---------- окно подтверждения (по центру на компьютере, снизу на телефоне) ----------
let modalEl = null;
let modalOnDismiss = null;
function closeModal(dismissed = false) {
  if (!modalEl) return;
  const cb = dismissed ? modalOnDismiss : null;
  modalEl.remove(); modalEl = null; modalOnDismiss = null;
  document.removeEventListener('keydown', escModal);
  if (cb) cb();
}
function escModal(e) { if (e.key === 'Escape') closeModal(true); }
function openModal(title, body, foot, onDismiss) {
  closeModal();
  modalOnDismiss = onDismiss || null;
  modalEl = h('div', { class: 'modal-wrap' },
    h('div', { class: 'modal-back', onclick: () => closeModal(true) }),
    h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
      h('div', { class: 'modal-head' }, h('h2', {}, title)),
      h('div', { class: 'modal-body' }, body),
      foot ? h('div', { class: 'modal-foot' }, foot) : null));
  document.body.append(modalEl);
  document.addEventListener('keydown', escModal);
  if (!matchMedia('(pointer: coarse)').matches) setTimeout(() => modalEl?.querySelector('input:not([type=hidden]), select, button.primary')?.focus(), 50);
}

// Подтверждение переноса брони: новые даты и номер можно поправить, цена пересчитывается по тарифам
// (или остаётся прежней / вводится вручную) — и только после «Подтвердить» уходит на сервер.
async function moveDialog(b, change, reload) {
  await ensureBoardData();
  const rooms = allRooms();
  const roomName = (id) => { const r = rooms.find((x) => x.id === id); return r ? `№${r.name} · ${r.type}` : '—'; };
  const oldTotal = Math.round(Number(b.total_price || 0));
  const paid = Math.round(Number(b.paid_amount || 0));
  const f = {};
  const note = h('div', { class: 'note', style: { display: 'none' } });
  f.room_id = h('select', { class: 'input', onchange: () => requote() }, rooms.map((r) => h('option', { value: r.id, selected: r.id === (change.room_id || b.room_id) }, `№${r.name} · ${r.type}`)));
  f.check_in = h('input', { class: 'input', type: 'date', value: change.check_in || b.check_in, onchange: () => {
    if (f.check_out.value <= f.check_in.value) f.check_out.value = addDays(f.check_in.value, 1);
    requote();
  } });
  f.check_out = h('input', { class: 'input', type: 'date', value: change.check_out || b.check_out, onchange: () => requote() });
  f.price = h('input', { class: 'input', money: true, type: 'number', inputmode: 'decimal', min: 0, value: oldTotal, oninput: () => { priceMode = 'custom'; drawPriceMode(); drawSummary(); } });
  let priceMode = 'keep';
  let tariff = null; // стоимость по тарифам на выбранные даты и номер
  let tariffOld = null; // по тарифам на прежние даты — чтобы понять, была ли цена «автоматической»
  const modeBox = h('div', { class: 'seg', style: { marginBottom: '10px', width: '100%' } });
  const hint = h('div', { class: 'muted small', style: { marginBottom: '12px' } });
  const summary = h('div', { class: 'move-summary' });
  const drawPriceMode = () => {
    modeBox.innerHTML = '';
    [['recalc', 'По тарифу'], ['keep', 'Как было']].forEach(([k, l]) => modeBox.append(h('button', {
      type: 'button', class: priceMode === k ? 'on' : '', style: { flex: 1 }, disabled: k === 'recalc' && tariff === null,
      onclick: () => { priceMode = k; f.price.value = k === 'recalc' ? Math.round(tariff) : oldTotal; drawPriceMode(); drawSummary(); },
    }, l)));
    hint.textContent = tariff === null ? 'Считаю стоимость по тарифам…'
      : `По тарифам на новые даты: ${fmtMoney(tariff)}. Прежняя стоимость: ${fmtMoney(oldTotal)}. Можно ввести свою сумму.`;
  };
  const nightsOf = (ci, co) => Math.max(diffDays(ci, co), 0);
  const drawSummary = () => {
    const ci = f.check_in.value, co = f.check_out.value;
    const total = Math.round(Number(f.price.value || 0));
    const diff = total - oldTotal;
    summary.innerHTML = '';
    summary.append(...[
      h('div', { class: 'move-row' }, h('span', { class: 'lbl' }, 'Было'),
        h('span', {}, `${roomName(b.room_id)} · ${fmtShort(b.check_in)} — ${fmtShort(b.check_out)} (${nightsOf(b.check_in, b.check_out)} ${nightsWord(nightsOf(b.check_in, b.check_out))}) · ${fmtMoney(oldTotal)}`)),
      h('div', { class: 'move-row now' }, h('span', { class: 'lbl' }, 'Станет'),
        h('span', {}, `${roomName(f.room_id.value)} · ${ci ? fmtShort(ci) : '—'} — ${co ? fmtShort(co) : '—'} (${nightsOf(ci, co)} ${nightsWord(nightsOf(ci, co))}) · `, h('b', {}, fmtMoney(total)),
          diff ? h('span', { class: diff > 0 ? 'delta up' : 'delta down' }, ` ${diff > 0 ? '+' : '−'}${fmtMoney(Math.abs(diff))}`) : null)),
      paid ? h('div', { class: 'muted small', style: { marginTop: '6px' } }, `Оплачено ${fmtMoney(paid)}, останется доплатить ${fmtMoney(Math.max(total - paid, 0))}`) : null,
    ].filter(Boolean));
  };
  let timer;
  async function quoteFor(room, ci, co) {
    return api('GET', '/api/bookings/quote?' + qs({ room_id: room, check_in: ci, check_out: co, exclude: b.id }));
  }
  function requote() {
    clearTimeout(timer);
    drawSummary();
    timer = setTimeout(async () => {
      const ci = f.check_in.value, co = f.check_out.value;
      if (!ci || !co || co <= ci) { note.className = 'note bad'; note.textContent = 'Дата выезда должна быть позже даты заезда'; note.style.display = ''; return; }
      try {
        const q = await quoteFor(f.room_id.value, ci, co);
        tariff = Number(q.total);
        if (priceMode === 'recalc') f.price.value = Math.round(tariff);
        const warn = [];
        if (q.busy) warn.push(q.busy);
        if (q.closed_dates.length && b.status !== 'blocked') warn.push('Продажи на часть дат закрыты');
        if (q.nights < q.min_stay && b.status !== 'blocked') warn.push(`Минимальный срок — ${q.min_stay} ${nightsWord(q.min_stay)}`);
        if (warn.length) { note.className = 'note bad'; note.textContent = warn.join('. '); note.style.display = ''; } else note.style.display = 'none';
      } catch { /* ошибку покажем при подтверждении */ }
      drawPriceMode(); drawSummary();
    }, 200);
  }
  // была ли прежняя цена посчитана автоматически: тогда по умолчанию пересчитываем
  try {
    tariffOld = Number((await quoteFor(b.room_id, b.check_in, b.check_out)).total);
    if (Math.round(tariffOld) === oldTotal) priceMode = 'recalc';
  } catch { /* оставим «как было» */ }
  const confirmBtn = h('button', { class: 'btn primary', onclick: async () => {
    confirmBtn.disabled = true;
    const payload = b.status === 'blocked' ? {} : { total_price: f.price.value || 0 };
    if (f.room_id.value !== b.room_id) payload.room_id = f.room_id.value;
    if (f.check_in.value !== b.check_in) payload.check_in = f.check_in.value;
    if (f.check_out.value !== b.check_out) payload.check_out = f.check_out.value;
    try {
      await api('PATCH', `/api/bookings/${b.id}`, payload);
      closeModal(); reload();
      toastUndo('Бронь перенесена', () => api('PATCH', `/api/bookings/${b.id}`,
        b.status === 'blocked' ? { room_id: b.room_id, check_in: b.check_in, check_out: b.check_out } : { room_id: b.room_id, check_in: b.check_in, check_out: b.check_out, total_price: b.total_price }), reload);
    } catch (ex) { note.className = 'note bad'; note.textContent = ex.message; note.style.display = ''; confirmBtn.disabled = false; }
  } }, 'Подтвердить перенос');
  const title = b.status === 'blocked' ? 'Перенести закрытые даты?' : `Перенести бронь${b.guest_name ? ` «${b.guest_name}»` : ''}?`;
  openModal(title, h('div', {}, note, summary,
    h('label', { class: 'field' }, h('span', {}, 'Номер'), f.room_id),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Заезд'), f.check_in), h('label', { class: 'field' }, h('span', {}, 'Выезд'), f.check_out)),
    b.status === 'blocked' ? null : [h('div', { class: 'field' }, h('span', {}, 'Стоимость'), modeBox, f.price), hint]),
  [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), confirmBtn],
  () => reload());
  drawPriceMode(); drawSummary(); requote();
}

function drawBoard(data, reload) {
  const days = data.days;
  const today = todayISO();
  const cellW = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--cell'), 10) || 44;
  const dayClass = (d, i) => {
    const dt = parseISO(d); const c = [];
    if (dt.getDay() === 0 || dt.getDay() === 6) c.push('we');
    if (d === today) c.push('today');
    if (dt.getDate() === 1 && i > 0) c.push('month-start');
    if (holidayName(d)) c.push('holiday');
    return c.join(' ');
  };
  const board = h('div', { class: 'board' + (cellW < 30 ? ' compact' : '') });
  // заголовок с датами
  const headRow = h('div', { class: 'b-row b-head' }, h('div', { class: 'b-side' }, 'Номер'));
  days.forEach((d, i) => {
    const dt = parseISO(d);
    const dnote = (data.date_notes || {})[d];
    headRow.append(h('div', { class: 'b-day ' + dayClass(d, i) + (dnote ? ' has-note' : ''), title: [holidayName(d), dnote ? `Заметка: ${dnote}` : (can('manager') ? 'Нажмите, чтобы добавить заметку на эту дату' : '')].filter(Boolean).join('\n'),
      onclick: () => can('manager') && dateNoteDialog(d, dnote, reload) },
      dt.getDate() === 1 || i === 0 ? h('span', { class: 'b-month' }, MONTHS_SHORT[dt.getMonth()]) : null,
      h('span', { class: 'n' }, dt.getDate()), h('span', { class: 'w' }, WD[dt.getDay()])));
  });
  board.append(headRow);

  const byRoom = {};
  const flags = data.guest_flags || {};
  data.bookings.forEach((b) => (byRoom[b.room_id] ||= []).push(b));

  // выделение диапазона мышью; на телефоне — касание
  let sel = null;
  let lastPointer = 'mouse';
  const clearSel = () => board.querySelectorAll('.b-cell.sel').forEach((c) => c.classList.remove('sel'));
  const paintSel = () => {
    clearSel(); if (!sel) return;
    const [a, b] = [Math.min(sel.start, sel.end), Math.max(sel.start, sel.end)];
    for (let i = a; i <= b; i++) sel.cells[i]?.classList.add('sel');
  };
  const finishSel = () => {
    if (!sel) return;
    const [a, b] = [Math.min(sel.start, sel.end), Math.max(sel.start, sel.end)];
    const room = sel.room; sel = null;
    setTimeout(clearSel, 300);
    if (can('manager')) bookingDrawer({ room_id: room.id, check_in: days[a], check_out: addDays(days[b], 1) }, reload);
  };
  document.removeEventListener('pointerup', window.__boardPointerUp || (() => {}));
  window.__boardPointerUp = finishSel;
  document.addEventListener('pointerup', finishSel);

  const roomRows = [];
  data.room_types.forEach((t) => {
    const roomIds = new Set(t.rooms.map((r) => r.id));
    const typeRow = h('div', { class: 'b-row b-type' },
      h('div', { class: 'b-side', title: t.name }, h('span', {}, t.name), h('span', { class: 'muted small num' }, t.rooms.length)));
    days.forEach((d) => {
      const rate = t.rates[d];
      const price = rate?.price ?? t.base_price;
      const busy = data.bookings.filter((b) => roomIds.has(b.room_id) && b.check_in <= d && b.check_out > d).length;
      const free = t.rooms.length - busy;
      typeRow.append(h('div', {
        class: 'b-price' + (rate?.price != null ? ' custom' : '') + (rate?.closed ? ' closed' : ''),
        title: `${fmtDate(d)}: ${fmtMoney(price)}${rate?.min_stay ? `, от ${count(rate.min_stay, 'night')}` : ''}${rate?.closed ? ', продажи закрыты' : ''}. Свободно: ${free}`,
        onclick: () => can('manager') && rateDrawer(t, d, reload),
      }, fmtPriceCell(price), h('span', { class: 'free' + (free <= 0 ? ' zero' : '') }, free)));
    });
    board.append(typeRow);

    t.rooms.forEach((room) => {
      const track = h('div', { class: 'b-track' });
      roomRows.push({ room, track });
      const cells = days.map((d, i) => {
        const c = h('div', { class: 'b-cell ' + dayClass(d, i), 'data-i': i });
        c.addEventListener('click', (e) => {
          // на телефоне протягивать неудобно: касание = бронь на одну ночь
          if (lastPointer !== 'mouse' && can('manager')) bookingDrawer({ room_id: room.id, check_in: d, check_out: addDays(d, 1) }, reload);
        });
        c.addEventListener('pointerdown', (e) => {
          lastPointer = e.pointerType;
          if (e.button !== 0 || e.pointerType !== 'mouse') return;
          e.preventDefault();
          sel = { room, start: i, end: i, cells }; paintSel();
        });
        c.addEventListener('pointerenter', () => { if (sel && sel.room === room) { sel.end = i; paintSel(); } });
        return c;
      });
      track.append(...cells);
      (byRoom[room.id] || []).forEach((b) => {
        let s = diffDays(days[0], b.check_in);
        let e = diffDays(days[0], b.check_out);
        const cutL = s < 0; const cutR = e > days.length;
        const left = cutL ? 0 : (s + 0.5) * cellW;
        const right = cutR ? days.length * cellW : (e + 0.5) * cellW;
        const nights = diffDays(b.check_in, b.check_out);
        const label = b.status === 'blocked' ? 'Закрыто' : (b.guest_name || SOURCE[b.source]);
        const draggable = can('manager') && !b.feed_id;
        const bar = h('div', {
          class: `bar ${b.status}${b.group_id ? ' grouped' : ''}${cutL ? ' cut-left' : ''}${cutR ? ' cut-right' : ''}${draggable ? ' draggable' : ''}`,
          style: { left: `${left + 2}px`, width: `${Math.max(right - left - 4, 12)}px`, background: `var(--src-${b.source})` },
          title: `${label} · ${SOURCE[b.source]} · ${STATUS[b.status]}\n${fmtDate(b.check_in)} — ${fmtDate(b.check_out)}, ${nights} ${nightsWord(nights)}`
            + (draggable ? '\nПеретащите, чтобы перенести, или потяните за край, чтобы изменить длину' : ''),
        }, h('span', { class: 'ttl' }, label),
        b.status !== 'blocked' && b.source !== 'manual' && right - left < 130 ? h('span', { class: 'sb', title: SOURCE[b.source] }, SOURCE_ABBR[b.source]) : null,
        flags[b.id]?.blacklisted ? h('span', { class: 'flag', title: 'Гость в чёрном списке' }, '⛔') : null,
        flags[b.id]?.birthday ? h('span', { class: 'flag', title: `День рождения гостя: ${fmtDate(flags[b.id].birthday)}` }, '🎂') : null,
        b.status !== 'blocked' && b.guest_name && right - left > 120 ? h('span', { class: 'src' }, SOURCE[b.source]) : null);
        bindBarDrag(bar, b, room, draggable, { days, cellW, roomRows, reload });
        track.append(bar);
      });
      board.append(h('div', { class: 'b-row b-room' },
        h('div', { class: 'b-side' }, h('span', {}, room.name, ['dirty', 'cleaning', 'inspect', 'repair'].includes(room.hk_status) ? h('i', { class: `hk-dot hk-${room.hk_status}`, title: `${HK[room.hk_status]}${room.hk_note ? ': ' + room.hk_note : ''}` }) : null), h('span', { class: 'rt' }, t.name)), track));
    });
  });

  if (!data.room_types.length) board.append(h('div', { class: 'empty' }, 'Номеров пока нет. Добавьте их в настройках.'));

  const noteEntries = Object.entries(data.date_notes || {}).sort();
  const notesBox = noteEntries.length ? h('div', { class: 'date-notes' }, noteEntries.map(([d, t]) => h('span', { class: 'date-note', onclick: () => can('manager') && dateNoteDialog(d, t, reload) }, h('b', {}, fmtDate(d)), ` — ${t}`))) : null;
  const legend = h('div', { class: 'legend' },
    ['direct', 'manual', 'avito', 'yandex', 'sutochno', 'ostrovok'].map((s) => h('span', {}, h('i', { class: 'dot', style: { background: `var(--src-${s})` } }), SOURCE[s])),
    h('span', {}, h('i', { class: 'dot', style: { background: 'repeating-linear-gradient(135deg,#9AA296 0 3px,#C9CEC5 3px 6px)' } }), 'Даты закрыты'),
    h('span', {}, 'Штриховка — заявка, ждёт подтверждения'),
    can('manager') ? h('span', { style: { marginLeft: 'auto' } }, 'Протяните по свободным клеткам, чтобы создать бронь') : null);
  const scroll = h('div', { class: 'board-scroll' }, board);
  // прокрутить к сегодняшнему дню на узких экранах
  requestAnimationFrame(() => {
    const idx = days.indexOf(today);
    if (idx > 2 && scroll.scrollLeft === 0) scroll.scrollTo({ left: (idx - 1) * cellW, behavior: 'smooth' });
  });
  return h('div', {}, scroll, notesBox, legend);
}

function dateNoteDialog(day, text, reload) {
  const input = h('textarea', { class: 'input', placeholder: 'Например: День города — цены выше, ждём много заездов' }, text || '');
  openModal(`Заметка на ${fmtDate(day)}`, h('div', {}, h('label', { class: 'field' }, h('span', {}, 'Видят все сотрудники'), input)),
    [text ? h('button', { class: 'btn ghost danger', onclick: async () => { await api('PUT', '/api/date-notes', { day, text: '', property_id: state.propertyId }); closeModal(); reload(); } }, 'Удалить') : null, h('span', { class: 'spacer' }),
      h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'),
      h('button', { class: 'btn primary', onclick: async () => { try { await api('PUT', '/api/date-notes', { day, text: input.value, property_id: state.propertyId }); closeModal(); reload(); } catch (ex) { toast(ex.message, true); } } }, 'Сохранить')]);
}

// ---------- карточка брони ----------
function allRooms() {
  if (!boardData) return [];
  return boardData.room_types.flatMap((t) => t.rooms.map((r) => ({ ...r, type: t.name })));
}

async function ensureBoardData() {
  if (!boardData || boardData.property.id !== state.propertyId) {
    boardData = await api('GET', '/api/board?' + qs({ property_id: state.propertyId, from: todayISO(), days: 1 }));
  }
}

// ---------- телефоны ----------
function formatPhone(raw) {
  const s = String(raw || '').trim();
  let d = s.replace(/\D/g, '');
  if (!d) return s.startsWith('+') ? '+' : '';
  if (s.startsWith('+') && d[0] !== '7' && d[0] !== '8') return '+' + d.slice(0, 15);
  if (d[0] === '8') d = '7' + d.slice(1); else if (d[0] !== '7') d = '7' + d;
  d = d.slice(0, 11);
  let out = '+7';
  if (d.length > 1) out += ' ' + d.slice(1, 4);
  if (d.length > 4) out += ' ' + d.slice(4, 7);
  if (d.length > 7) out += '-' + d.slice(7, 9);
  if (d.length > 9) out += '-' + d.slice(9, 11);
  return out;
}
// Подставляет формат +7 999 123-45-67 при вводе (если курсор в конце) и при выходе из поля
function bindPhone(input) {
  input.addEventListener('input', () => {
    if (input.selectionStart === input.value.length && !(input.inputType === 'deleteContentBackward')) input.value = formatPhone(input.value);
  });
  input.addEventListener('blur', () => { input.value = formatPhone(input.value); });
  return input;
}
const phoneDigits = (p) => String(p || '').replace(/\D/g, '');
async function copyText(text, okMsg = 'Скопировано') {
  try { await navigator.clipboard.writeText(text); toast(okMsg); }
  catch { toast('Не удалось скопировать — выделите текст и скопируйте вручную', true); }
}
// Позвонить, написать в Telegram, скопировать номер для MAX
function phoneActions(phone) {
  const d = phoneDigits(phone);
  if (d.length < 10) return null;
  const intl = (d.length === 11 && d[0] === '8' ? '7' + d.slice(1) : d);
  return h('span', { class: 'phone-actions' },
    h('a', { class: 'btn small ghost', href: `tel:+${intl}`, title: 'Позвонить' }, icon('phone'), 'Позвонить'),
    h('a', { class: 'btn small ghost', href: `https://t.me/+${intl}`, target: '_blank', rel: 'noopener', title: 'Открыть чат в Telegram' }, 'Telegram'),
    h('button', { class: 'btn small ghost', type: 'button', title: 'Скопировать номер для поиска в MAX', onclick: () => copyText('+' + intl, 'Номер скопирован — вставьте его в поиск MAX') }, 'MAX'));
}

// ---------- гости ----------
async function viewGuests(main) {
  const q = h('input', { class: 'input', placeholder: 'Имя, телефон или тег', style: { width: '260px' }, value: store.get('guests_q', '') });
  const sort = h('select', { class: 'input', style: { width: '210px' } }, [['last', 'Недавние'], ['visits', 'По числу визитов'], ['spent', 'По сумме'], ['name', 'По имени']].map(([k, l]) => h('option', { value: k, selected: k === store.get('guests_sort', 'last') }, l)));
  const card = h('div', { class: 'card' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Гости')), h('div', { class: 'board-tools', style: { marginBottom: '14px' } }, q, sort), card);
  let timer; let page = 1;
  const load = async (more) => {
    store.set('guests_q', q.value); store.set('guests_sort', sort.value);
    if (!more) page = 1;
    try {
      const r = await api('GET', '/api/guests/list?' + qs({ q: q.value.trim(), sort: sort.value, page }));
      if (!more) card.innerHTML = '';
      else card.querySelector('.more-row')?.remove();
      if (!r.items.length && !more) {
        card.append(h('div', { class: 'empty' }, h('h3', {}, q.value ? 'Никого не нашли' : 'Гостей пока нет'),
          q.value ? 'Попробуйте часть имени или последние цифры телефона.' : 'Гости появятся здесь сами, когда вы создадите брони с телефоном гостя.'));
        return;
      }
      let table = card.querySelector('table');
      if (!table) {
        table = h('table', { class: 'list cards-mobile' }, h('thead', {}, h('tr', {}, ['Гость', 'Визитов', 'Ночей', 'Сумма', 'Последний визит', ''].map((t) => h('th', {}, t)))), h('tbody'));
        card.append(h('div', { class: 'table-wrap' }, table));
      }
      table.querySelector('tbody').append(...r.items.map((g) => h('tr', { class: 'click', onclick: () => guestDrawer(g.phone, g.name, () => load()) },
        h('td', { 'data-l': 'Гость' }, h('b', {}, g.name || 'Без имени'), g.blacklisted ? h('span', { class: 'pill bad', style: { marginLeft: '8px' } }, 'чёрный список') : null,
          h('div', { class: 'muted small' }, g.phone), g.tags.length ? h('div', { class: 'tags' }, g.tags.map((t) => h('span', { class: 'tag' }, t))) : null),
        h('td', { class: 'num', 'data-l': 'Визитов' }, g.visits), h('td', { class: 'num', 'data-l': 'Ночей' }, g.nights), h('td', { class: 'num', 'data-l': 'Сумма' }, fmtMoney(g.spent)),
        h('td', { 'data-l': 'Последний визит' }, fmtShort(g.last_stay), g.next_stay ? h('div', { class: 'muted small' }, `ближайший: ${fmtShort(g.next_stay)}`) : null),
        h('td', {}, g.visits >= 2 ? h('span', { class: 'pill ok' }, 'постоянный') : null))));
      if (r.more) card.append(h('div', { class: 'more-row', style: { padding: '12px', textAlign: 'center' } }, h('button', { class: 'btn', onclick: () => { page += 1; load(true); } }, 'Показать ещё')));
    } catch (ex) { card.innerHTML = ''; card.append(h('div', { class: 'empty' }, ex.message)); }
  };
  q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => load(), 250); });
  sort.addEventListener('change', () => load());
  load();
}

// Карточка гостя: итоги, заметки, теги, чёрный список, история проживаний
async function guestDrawer(phone, name, onChange) {
  let g;
  try { g = await api('GET', '/api/guests/card?' + qs({ phone })); } catch (ex) { toast(ex.message, true); return; }
  const p = g.profile;
  const f = {
    name: h('input', { class: 'input', value: p.name || name || '' }),
    birthday: h('input', { class: 'input', type: 'date', value: p.birthday || '' }),
    tags: h('input', { class: 'input', value: (p.tags || []).join(', '), placeholder: 'vip, с собакой, командировка' }),
    notes: h('textarea', { class: 'input', placeholder: 'Что важно помнить: любит тишину, аллергия, просит поздний заезд…' }, p.notes || ''),
    black: h('input', { type: 'checkbox', checked: p.blacklisted }),
    reason: h('input', { class: 'input', value: p.blacklist_reason || '', placeholder: 'Причина (обязательно)' }),
  };
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const reasonBox = h('label', { class: 'field', style: { display: p.blacklisted ? '' : 'none' } }, h('span', {}, 'Причина'), f.reason);
  f.black.addEventListener('change', () => { reasonBox.style.display = f.black.checked ? '' : 'none'; if (f.black.checked) f.reason.focus(); });
  const stays = g.stays.slice(0, 15);
  const save = h('button', { class: 'btn primary', onclick: async () => {
    try {
      await api('PUT', '/api/guests/profile', { phone: g.phone, name: f.name.value, birthday: f.birthday.value || null,
        tags: f.tags.value.split(/[,;]/).map((x) => x.trim()).filter(Boolean), notes: f.notes.value, blacklisted: f.black.checked, blacklist_reason: f.reason.value });
      toast('Карточка гостя сохранена'); closeDrawer(); onChange?.();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  } }, 'Сохранить');
  openDrawer(f.name.value || 'Гость', h('div', {}, err,
    h('div', { style: { marginBottom: '10px' } }, h('b', {}, g.phone), ' ', phoneActions(g.phone)),
    h('div', { class: 'money-sum' },
      h('div', {}, h('span', { class: 'muted small' }, 'Визитов'), h('b', {}, g.visits)), h('div', {}, h('span', { class: 'muted small' }, 'Ночей'), h('b', {}, g.nights)),
      h('div', {}, h('span', { class: 'muted small' }, 'Принёс'), h('b', {}, fmtMoney(g.total_spent)))),
    g.cancelled ? h('p', { class: 'muted small' }, `Отменённых броней: ${g.cancelled}`) : null,
    h('div', { style: { marginTop: '14px' } }, h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Имя'), f.name), h('label', { class: 'field' }, h('span', {}, 'День рождения'), f.birthday)),
      h('label', { class: 'field' }, h('span', {}, 'Теги (через запятую)'), f.tags), h('label', { class: 'field' }, h('span', {}, 'Заметки'), f.notes),
      h('label', { class: 'check', style: { marginBottom: '10px' } }, f.black, 'Чёрный список (при новой брони покажем предупреждение)'), reasonBox),
    h('h3', { style: { margin: '16px 0 8px' } }, 'История проживаний'),
    stays.length ? stays.map((s) => h('div', { class: 'pay-row click', onclick: async () => {
      try { const b = await api('GET', `/api/bookings/${s.id}`); closeDrawer(); bookingDrawer(b, onChange); } catch (ex) { toast(ex.message, true); }
    } }, h('span', { class: 'pay-sum', style: { minWidth: '120px' } }, `${fmtShort(s.check_in)} — ${fmtShort(s.check_out)}`),
      h('span', { class: 'muted small' }, `${s.property_name}, ${s.room_name}${s.status === 'cancelled' ? ' · отменена' : ''}`), h('span', { class: 'small' }, fmtMoney(s.total_price))))
      : h('div', { class: 'muted small' }, 'Проживаний пока нет.')),
  [h('button', { class: 'btn', onclick: () => { closeDrawer(); bookingDrawer({ guest_name: f.name.value, guest_phone: g.phone }); } }, icon('plus'), 'Новая бронь'), h('span', { class: 'spacer' }),
    h('button', { class: 'btn foot-close', onclick: requestCloseDrawer }, 'Закрыть'), save], { guard: true });
}

// Сообщение гостю: шаблон с подстановкой данных брони → отправить на email, скопировать, Telegram, MAX
async function messageDialog(b) {
  let tpl;
  try { tpl = await api('GET', '/api/message-templates'); } catch (ex) { toast(ex.message, true); return; }
  const sel = h('select', { class: 'input' }, tpl.items.map((t) => h('option', { value: t.id }, t.name)));
  const text = h('textarea', { class: 'input', style: { minHeight: '180px' } });
  let ctx = {};
  const fill = async () => {
    try { ctx = await api('POST', `/api/bookings/${b.id}/message`, { template_id: sel.value }); text.value = ctx.text; } catch (ex) { toast(ex.message, true); }
  };
  sel.addEventListener('change', fill);
  await fill();
  const mail = h('button', { class: 'btn primary', type: 'button', disabled: !ctx.email, title: ctx.email ? '' : 'У гостя не указан email', onclick: async () => {
    try { const r = await api('POST', `/api/bookings/${b.id}/message/email`, { subject: ctx.subject, text: text.value }); toast(r.configured ? `Письмо отправлено: ${r.to}` : 'Почта на сервере не настроена — письмо записано в журнал сервера'); closeModal(); }
    catch (ex) { toast(ex.message, true); }
  } }, ctx.email ? `Отправить на ${ctx.email}` : 'Нет email');
  openModal('Написать гостю', h('div', {}, h('label', { class: 'field' }, h('span', {}, 'Шаблон'), sel),
    h('label', { class: 'field' }, h('span', {}, 'Текст (можно поправить)'), text),
    h('p', { class: 'muted small', style: { margin: 0 } }, 'Шаблоны правятся в «Настройки» → «Шаблоны сообщений».')),
  [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Закрыть'), h('span', { class: 'spacer' }),
    h('button', { class: 'btn', type: 'button', onclick: () => copyText(text.value, 'Текст скопирован') }, 'Скопировать'),
    h('button', { class: 'btn', type: 'button', title: 'Скопировать и вставить в чат MAX', onclick: () => copyText(text.value, 'Текст скопирован — вставьте его в чат MAX') }, 'Для MAX'),
    h('a', { class: 'btn', target: '_blank', rel: 'noopener', href: `https://t.me/share/url?${qs({ url: ctx.share_url || location.origin, text: text.value })}` }, 'В Telegram'), mail]);
}

// После создания брони по телефону — сразу предложить отправить гостю подтверждение
function offerSendConfirmation(created) {
  openModal('Бронь создана', h('div', {}, h('p', { style: { marginTop: 0 } }, 'Отправить гостю подтверждение? Подставим даты, цену и адрес из шаблона.')),
    [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Позже'), h('span', { class: 'spacer' }),
      h('button', { class: 'btn primary', onclick: () => { closeModal(); messageDialog(created); } }, 'Написать гостю')]);
}

// Переселение посреди проживания: до выбранной даты гость остаётся в прежнем номере, дальше — в новом
function relocateDialog(b, rooms, onSaved) {
  const today = todayISO();
  const first = addDays(b.check_in, 1);
  const f = {
    room: h('select', { class: 'input' }, rooms.filter((r) => r.id !== b.room_id).map((r) => h('option', { value: r.id }, `${r.name} · ${r.type}`))),
    from: h('input', { class: 'input', type: 'date', min: first, max: addDays(b.check_out, -1), value: today > b.check_in && today < b.check_out ? today : first }),
    total: h('input', { class: 'input', money: true, type: 'number', min: 0, placeholder: 'По умолчанию — остаток суммы пропорционально ночам' }),
  };
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  openModal('Переселить гостя', h('div', {}, err,
    h('p', { class: 'muted small', style: { marginTop: 0 } }, `Бронь ${fmtDate(b.check_in)} — ${fmtDate(b.check_out)} разделится на две части: до выбранной даты гость остаётся в прежнем номере, с этой даты (день выезда из прежнего) — в новом.`),
    h('label', { class: 'field' }, h('span', {}, 'Новый номер'), f.room), h('label', { class: 'field' }, h('span', {}, 'Переселить с даты'), f.from),
    h('label', { class: 'field' }, h('span', {}, 'Стоимость второй части, ₽ (необязательно)'), f.total)),
  [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
    try {
      await api('POST', `/api/bookings/${b.id}/relocate`, { room_id: f.room.value, from_date: f.from.value, total_price: f.total.value });
      closeModal(); closeDrawer(); toast('Гость переселён'); onSaved ? onSaved() : render();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  } }, 'Переселить')]);
}

// Шаблоны сообщений гостю — правка в настройках
function templatesCard() {
  const card = h('div', { class: 'card card-pad' });
  async function draw() {
    const r = await api('GET', '/api/message-templates');
    card.innerHTML = '';
    card.append(h('h2', { style: { marginBottom: '6px' } }, 'Шаблоны сообщений гостю'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, `Подставляются данные брони: ${r.placeholders.map((x) => `{${x}}`).join(' ')}.`),
      h('div', { class: 'pay-list' }, r.items.map((t) => h('div', { class: 'pay-row' }, h('span', { class: 'pay-sum', style: { flex: 1 } }, t.name),
        h('button', { class: 'btn small ghost', type: 'button', onclick: () => editTpl(t) }, 'Изменить')))),
      h('button', { class: 'btn small', type: 'button', onclick: () => editTpl(null) }, icon('plus'), 'Шаблон'));
  }
  function editTpl(t) {
    const name = h('input', { class: 'input', value: t?.name || '' });
    const body = h('textarea', { class: 'input', style: { minHeight: '180px' } }, t?.body || '');
    const err = h('div', { class: 'note bad', style: { display: 'none' } });
    openModal(t ? 'Шаблон' : 'Новый шаблон', h('div', {}, err, h('label', { class: 'field' }, h('span', {}, 'Название'), name), h('label', { class: 'field' }, h('span', {}, 'Текст'), body)),
      [t ? h('button', { class: 'btn ghost danger', onclick: async () => { if (confirm('Удалить шаблон?')) { await api('DELETE', `/api/message-templates/${t.id}`); closeModal(); draw(); } } }, 'Удалить') : null, h('span', { class: 'spacer' }),
        h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'),
        h('button', { class: 'btn primary', onclick: async () => {
          try { if (t) await api('PATCH', `/api/message-templates/${t.id}`, { name: name.value, body: body.value }); else await api('POST', '/api/message-templates', { name: name.value, body: body.value }); closeModal(); draw(); }
          catch (ex) { err.textContent = ex.message; err.style.display = ''; }
        } }, 'Сохранить')]);
  }
  draw().catch((ex) => { card.textContent = ex.message; });
  return card;
}

// ---------- деньги в брони: платежи, услуги, скидка, залог ----------
const PAY_METHOD = { cash: 'Наличные', card: 'Карта', transfer: 'Перевод', online: 'Онлайн', other: 'Другое' };
const DEPOSIT = { none: 'Без залога', expected: 'Ожидается', held: 'Внесён', returned: 'Возвращён', kept: 'Удержан' };

function moneyBlock(b, onChange) {
  const box = h('div', { class: 'money-box' });
  let m = null;
  async function load() {
    try { m = await api('GET', `/api/bookings/${b.id}/money`); } catch (ex) { box.textContent = ex.message; return; }
    draw();
  }
  const act = async (fn) => {
    try { m = await fn(); onChange?.(m); draw(); } catch (ex) { toast(ex.message, true); }
  };
  function draw() {
    box.innerHTML = '';
    const due = Number(m.due);
    box.append(
      h('div', { class: 'money-sum' },
        h('div', {}, h('span', { class: 'muted small' }, 'Итого'), h('b', {}, fmtMoney(m.total))),
        h('div', {}, h('span', { class: 'muted small' }, 'Оплачено'), h('b', {}, fmtMoney(m.paid))),
        h('div', { class: due > 0 ? 'due' : 'ok' }, h('span', { class: 'muted small' }, due > 0 ? 'К оплате' : 'Оплачено полностью'), h('b', {}, fmtMoney(due)))));
    // платежи
    const amount = h('input', { class: 'input', money: true, type: 'number', min: 1, placeholder: 'Сумма, ₽', value: due > 0 ? Math.round(due) : '' });
    const method = h('select', { class: 'input' }, Object.entries(PAY_METHOD).map(([k, l]) => h('option', { value: k }, l)));
    const day = h('input', { class: 'input', type: 'date', value: todayISO() });
    const note = h('input', { class: 'input', placeholder: 'Комментарий (необязательно)' });
    const addPay = (kind) => act(async () => {
      const r = await api('POST', `/api/bookings/${b.id}/payments`, { amount: amount.value, method: method.value, paid_on: day.value, note: note.value, kind });
      toast(kind === 'refund' ? 'Возврат записан' : 'Платёж записан'); return r;
    });
    box.append(h('h3', {}, 'Платежи'),
      m.payments.length ? h('div', { class: 'pay-list' }, m.payments.map((p) => h('div', { class: 'pay-row' + (p.kind === 'refund' ? ' refund' : '') },
        h('span', { class: 'pay-sum' }, `${p.kind === 'refund' ? '−' : '+'}${fmtMoney(p.amount)}`),
        h('span', { class: 'muted small' }, `${fmtDate(p.paid_on)} · ${PAY_METHOD[p.method]}${p.note ? ' · ' + p.note : ''}${p.user_name ? ' · ' + p.user_name : ''}`),
        h('button', { class: 'btn icon ghost small', type: 'button', title: 'Удалить запись', 'aria-label': 'Удалить запись', onclick: () => {
          if (confirm('Удалить эту запись о платеже?')) act(() => api('DELETE', `/api/payments/${p.id}`));
        } }, icon('close')))))
        : h('div', { class: 'muted small', style: { marginBottom: '8px' } }, 'Платежей пока нет.'),
      h('div', { class: 'row3' }, h('label', { class: 'field' }, h('span', {}, 'Сумма'), amount), h('label', { class: 'field' }, h('span', {}, 'Способ'), method), h('label', { class: 'field' }, h('span', {}, 'Дата'), day)),
      h('div', { class: 'money-actions', style: { marginBottom: '14px' } }, note,
        h('button', { class: 'btn primary small', type: 'button', onclick: () => addPay('payment') }, 'Принять оплату'),
        Number(m.paid) > 0 ? h('button', { class: 'btn small', type: 'button', onclick: () => addPay('refund') }, 'Вернуть') : null));
    // услуги
    const svcSel = h('select', { class: 'input' }, h('option', { value: '' }, 'Выбрать из справочника…'));
    api('GET', '/api/services').then((list) => list.filter((x) => x.active).forEach((x) => svcSel.append(h('option', { value: x.id }, `${x.name} — ${fmtMoney(x.price)}`)))).catch(() => {});
    const svcName = h('input', { class: 'input', placeholder: 'или своя услуга' });
    const svcPrice = h('input', { class: 'input', money: true, type: 'number', min: 0, placeholder: 'Цена, ₽' });
    const svcQty = h('input', { class: 'input', type: 'number', min: 1, value: 1, style: { maxWidth: '80px' } });
    box.append(h('h3', {}, 'Дополнительные услуги'),
      m.services.length ? h('div', { class: 'pay-list' }, m.services.map((x) => h('div', { class: 'pay-row' },
        h('span', { class: 'pay-sum' }, `${x.name}${x.qty > 1 ? ' × ' + x.qty : ''}`),
        h('span', { class: 'muted small' }, fmtMoney(Number(x.price) * x.qty)),
        h('button', { class: 'btn icon ghost small', type: 'button', title: 'Убрать услугу', 'aria-label': 'Убрать услугу', onclick: () => act(() => api('DELETE', `/api/booking-services/${x.id}`)) }, icon('close')))))
        : h('div', { class: 'muted small', style: { marginBottom: '8px' } }, 'Услуг нет. Завтрак, трансфер, поздний выезд — добавьте здесь, и сумма пересчитается.'),
      h('div', { class: 'money-actions', style: { marginBottom: '14px' } }, svcSel, svcName, svcPrice, svcQty,
        h('button', { class: 'btn small', type: 'button', onclick: () => {
          if (!svcSel.value && !svcName.value.trim()) { toast('Выберите услугу или введите название', true); return; }
          act(() => api('POST', `/api/bookings/${b.id}/services`, svcSel.value ? { service_id: svcSel.value, qty: svcQty.value } : { name: svcName.value, price: svcPrice.value, qty: svcQty.value }));
        } }, icon('plus'), 'Добавить')));
    // скидка и залог
    const disc = h('input', { class: 'input', money: true, type: 'number', min: 0, value: Math.round(Number(m.discount_amount)) || '', placeholder: '0' });
    const discWhy = h('input', { class: 'input', value: m.discount_reason, placeholder: 'Причина: постоянный гость, акция…' });
    const dep = h('input', { class: 'input', money: true, type: 'number', min: 0, value: Math.round(Number(m.deposit_amount)) || '', placeholder: '0' });
    const depSt = h('select', { class: 'input' }, Object.entries(DEPOSIT).map(([k, l]) => h('option', { value: k, selected: k === m.deposit_status }, l)));
    const patch = (payload) => act(async () => { await api('PATCH', `/api/bookings/${b.id}`, payload); return api('GET', `/api/bookings/${b.id}/money`); });
    box.append(h('h3', {}, 'Скидка и залог'),
      h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Скидка, ₽'), disc), h('label', { class: 'field' }, h('span', {}, 'Причина скидки'), discWhy)),
      h('div', { class: 'money-actions', style: { marginBottom: '8px' } }, h('button', { class: 'btn small', type: 'button', onclick: () => patch({ discount_amount: disc.value || 0, discount_reason: discWhy.value }) }, 'Применить скидку')),
      h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Залог, ₽'), dep), h('label', { class: 'field' }, h('span', {}, 'Статус залога'), depSt)),
      h('div', { class: 'money-actions' }, h('button', { class: 'btn small', type: 'button', onclick: () => patch({ deposit_amount: dep.value || 0, deposit_status: dep.value && depSt.value === 'none' ? 'expected' : depSt.value }) }, 'Сохранить залог'),
        h('span', { class: 'muted small' }, 'Залог не входит в стоимость и в выручку.')));
  }
  load();
  box.reload = load;
  return box;
}

async function printInvoice(b) {
  try {
    const [prop, m] = await Promise.all([api('GET', `/api/properties/${b.property_id}`), api('GET', `/api/bookings/${b.id}/money`)]);
    const room = allRooms().find((r) => r.id === b.room_id);
    const nights = Math.round((parseISO(b.check_out) - parseISO(b.check_in)) / 86400000);
    const th = (t, right) => h('th', { style: { textAlign: right ? 'right' : 'left', padding: '6px 8px', borderBottom: '2px solid #000', fontSize: '13px' } }, t);
    const td = (t, right, bold) => h('td', { style: { textAlign: right ? 'right' : 'left', padding: '6px 8px', borderBottom: '1px solid #ccc', fontWeight: bold ? 700 : 400 } }, t);
    const rows = [
      [`Проживание, номер ${room ? room.name : ''}, ${fmtDate(b.check_in)} — ${fmtDate(b.check_out)} (${nights} ${nightsWord(nights)})`, 1, Number(m.stay_price) + Number(m.discount_amount)],
      ...m.services.map((x) => [x.name, x.qty, Number(x.price) * x.qty]),
    ];
    document.getElementById('print-sheet')?.remove();
    document.body.append(h('div', { id: 'print-sheet' },
      letterhead(prop.name, [prop.address, prop.phone].filter(Boolean).join(' · ')),
      h('h1', { style: { fontSize: '22px', marginBottom: '2px' } }, `Счёт № ${String(b.id).slice(0, 8).toUpperCase()}`),
      h('p', { style: { marginTop: 0, color: '#555' } }, `от ${fmtDate(todayISO())} ${new Date().getFullYear()}`),
      h('p', { style: { margin: '0 0 14px' } }, 'Гость: ', h('b', {}, b.guest_name || '—'), b.guest_phone ? `, ${b.guest_phone}` : ''),
      h('table', { style: { borderCollapse: 'collapse', width: '100%', fontSize: '14px' } },
        h('thead', {}, h('tr', {}, th('Наименование'), th('Кол-во', 1), th('Сумма', 1))),
        h('tbody', {}, rows.map(([n, q, sum]) => h('tr', {}, td(n), td(String(q), 1), td(fmtMoney(sum), 1))),
          Number(m.discount_amount) ? h('tr', {}, td(`Скидка${m.discount_reason ? ': ' + m.discount_reason : ''}`), td('', 1), td('−' + fmtMoney(m.discount_amount), 1)) : null,
          h('tr', {}, td('Итого', 0, 1), td('', 1), td(fmtMoney(m.total), 1, 1)),
          h('tr', {}, td('Оплачено'), td('', 1), td(fmtMoney(m.paid), 1)),
          h('tr', {}, td('К оплате', 0, 1), td('', 1), td(fmtMoney(m.due), 1, 1)))),
      Number(m.deposit_amount) ? h('p', { style: { marginTop: '14px', color: '#333' } }, `Залог: ${fmtMoney(m.deposit_amount)} (${DEPOSIT[m.deposit_status].toLowerCase()}). Возвращается при выезде, если нет претензий.`) : null,
      h('p', { style: { marginTop: '28px', color: '#555' } }, 'Спасибо, что выбрали нас!')));
    window.print();
  } catch (ex) { toast(ex.message, true); }
}

const DRAFT_KEY = 'draft_booking';
function loadDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
    if (!d || Date.now() - d.at > 3 * 3600 * 1000 || d.property !== state.propertyId) return null;
    return d.data;
  } catch { return null; }
}
const clearDraft = () => { try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ } };

async function bookingDrawer(b, onSaved) {
  await ensureBoardData();
  const isNew = !b.id;
  // Новая бронь, открытая кнопкой (а не кликом по клетке шахматки): подхватываем черновик, если закрыли случайно
  let restored = null;
  if (isNew && !b.room_id && !b.guest_name) {
    restored = loadDraft();
    if (restored) b = { ...b, ...restored };
  }
  const imported = !!b.feed_id;
  const readOnly = !can('manager');
  const rooms = allRooms();
  const f = {};
  let priceTouched = !isNew;
  const status = { value: b.status || 'confirmed' };
  const note = h('div', { class: 'note', style: { display: 'none' } });
  const totalEl = h('b');
  const nightsEl = h('span', { class: 'muted' });
  const breakdownEl = h('div', { class: 'muted small breakdown' });
  const freeBox = h('div', { class: 'free-box', style: { display: 'none' } });

  const inp = (key, label, attrs = {}) => h('label', { class: 'field' }, h('span', {}, label),
    f[key] = h('input', { class: 'input', value: b[key] ?? '', disabled: readOnly, ...attrs }));

  const statusSeg = h('div', { class: 'seg', style: { marginBottom: '14px', width: '100%' } });
  const guestBox = h('div');
  const drawSeg = () => {
    statusSeg.innerHTML = '';
    [['confirmed', 'Подтверждена'], ['pending', 'Заявка'], ['blocked', 'Закрыть даты']].forEach(([k, l]) => {
      statusSeg.append(h('button', { type: 'button', class: status.value === k ? 'on' : '', style: { flex: 1 }, disabled: readOnly || (imported && k !== status.value),
        onclick: () => { status.value = k; drawSeg(); guestBox.style.display = k === 'blocked' ? 'none' : ''; requote(); } }, l));
    });
  };
  drawSeg();

  f.room_id = h('select', { class: 'input', disabled: readOnly || imported, onchange: requote },
    rooms.map((r) => h('option', { value: r.id, selected: r.id === b.room_id }, `${r.name} · ${r.type}`)));
  f.check_in = h('input', { class: 'input', type: 'date', value: b.check_in || todayISO(), disabled: readOnly || imported, onchange: () => {
    if (f.check_out.value <= f.check_in.value) f.check_out.value = addDays(f.check_in.value, 1);
    requote();
  } });
  f.check_out = h('input', { class: 'input', type: 'date', value: b.check_out || addDays(b.check_in || todayISO(), 1), disabled: readOnly || imported, onchange: requote });
  f.source = h('select', { class: 'input', disabled: readOnly || imported },
    Object.entries(SOURCE).map(([k, l]) => h('option', { value: k, selected: (b.source || 'manual') === k }, l)));
  f.rate_plan_id = h('select', { class: 'input', disabled: readOnly || imported || !isNew, onchange: () => { priceTouched = false; requote(); } });
  const planField = h('label', { class: 'field', style: { display: 'none' } }, h('span', {}, 'Тариф'), f.rate_plan_id);
  let planTypeId = null;
  async function loadPlans() {
    const room = rooms.find((r) => r.id === f.room_id.value);
    if (!room || room.room_type_id === planTypeId) return;
    planTypeId = room.room_type_id;
    let plans = [];
    try { plans = (await api('GET', `/api/room-types/${planTypeId}/plans`)).filter((x) => x.active || x.id === b.rate_plan_id); } catch { /* нет прав — без тарифов */ }
    const keep = f.rate_plan_id.value || b.rate_plan_id || '';
    f.rate_plan_id.innerHTML = '';
    f.rate_plan_id.append(h('option', { value: '' }, 'Базовый'), plans.map((x) => h('option', { value: x.id, selected: x.id === keep }, x.name + (Number(x.percent_delta) || Number(x.fixed_delta) ? '' : ''))));
    planField.style.display = plans.length || (!isNew && b.rate_plan_name) ? '' : 'none';
    if (!isNew && b.rate_plan_name && !plans.length) f.rate_plan_id.append(h('option', { value: b.rate_plan_id || '', selected: true }, b.rate_plan_name));
  }
  f.notes = h('textarea', { class: 'input', disabled: readOnly }, b.notes || '');

  let quoteTimer;
  async function requote() {
    clearTimeout(quoteTimer);
    quoteTimer = setTimeout(async () => {
      if (!f.check_in.value || !f.check_out.value || f.check_out.value <= f.check_in.value) return;
      try {
        await loadPlans();
        loadFree();
        const q = await api('GET', '/api/bookings/quote?' + qs({ room_id: f.room_id.value, check_in: f.check_in.value, check_out: f.check_out.value, exclude: b.id,
          guests: f.guests_count?.value || 1, rate_plan_id: f.rate_plan_id.value }));
        nightsEl.textContent = `${count(q.nights, 'night')}, ${dateRange(f.check_in.value, f.check_out.value)} · заезд ${humanDay(f.check_in.value)}`;
        nightsEl.title = (q.breakdown || []).map((x) => `${x.label}: ${fmtMoney(x.amount)}`).join('\n');
        breakdownEl.innerHTML = '';
        if ((q.breakdown || []).length > 1) breakdownEl.append(...q.breakdown.map((x) => h('div', {}, `${x.label}: `, h('b', {}, fmtMoney(x.amount)))));
        if (!priceTouched && status.value !== 'blocked') f.total_price.value = Math.round(q.total);
        updateTotal();
        const warn = [];
        if (q.busy) warn.push(q.busy);
        if (q.closed_dates.length && status.value !== 'blocked') warn.push('Продажи на часть дат закрыты');
        if (q.nights < q.min_stay && status.value !== 'blocked') warn.push(`Минимальный срок — ${q.min_stay} ${nightsWord(q.min_stay)}`);
        if (warn.length) { note.className = 'note bad'; note.textContent = warn.join(' ') + (q.busy ? ' Свободные номера — под датами, нажмите на нужный.' : ''); note.style.display = ''; }
        else if (q.gaps?.length && status.value !== 'blocked') { note.className = 'note warn'; note.textContent = q.gaps.join('. ') + '.'; note.style.display = ''; }
        else if (!imported && !(b.status === 'pending' && b.source === 'direct' && b.hold_expires_at)) note.style.display = 'none';
      } catch { /* покажем при сохранении */ }
    }, 200);
  }
  // Свободные номера на выбранные даты: удобно, когда гость звонит и спрашивает «что есть»
  let freeSeq = 0;
  async function loadFree() {
    if (readOnly || imported || status.value === 'blocked' || (!isNew && b.status === 'cancelled')) { freeBox.style.display = 'none'; return; }
    const seq = ++freeSeq;
    try {
      const r = await api('GET', '/api/bookings/free-rooms?' + qs({ property_id: state.propertyId, check_in: f.check_in.value, check_out: f.check_out.value, guests: f.guests_count?.value || 1, exclude: b.id }));
      if (seq !== freeSeq) return;
      freeBox.innerHTML = '';
      const rows = r.types.filter((t) => t.rooms.length);
      if (!rows.length) { freeBox.append(h('div', { class: 'note bad' }, 'На эти даты свободных номеров нет. Попробуйте сдвинуть даты.')); freeBox.style.display = ''; return; }
      freeBox.append(h('div', { class: 'muted small', style: { marginBottom: '4px' } }, 'Свободны на эти даты (нажмите, чтобы выбрать):'),
        ...rows.map((t) => h('div', { class: 'type-filter', style: { margin: '0 0 4px' } },
          h('span', { class: 'small', style: { minWidth: '88px', fontWeight: 600 } }, t.type, !t.fits ? h('small', { class: 'muted' }, ` до ${t.capacity}`) : null),
          ...t.rooms.map((rm) => h('button', { type: 'button', class: 'chip' + (rm.id === f.room_id.value ? ' on' : ''), disabled: readOnly,
            onclick: () => { f.room_id.value = rm.id; priceTouched = !isNew; requote(); } }, rm.name)),
          h('span', { class: 'muted small' }, fmtMoney(t.price)))));
      freeBox.style.display = '';
    } catch { freeBox.style.display = 'none'; }
  }
  const updateTotal = () => {
    const total = Number(f.total_price.value || 0); const paid = Number(f.paid_amount ? f.paid_amount.value || 0 : b.paid_amount || 0);
    totalEl.textContent = fmtMoney(total);
    const pm = document.querySelector('.drawer [data-prepay]'); if (pm) pm.style.display = paid > 0 ? '' : 'none';
    totalEl.title = paid ? `Оплачено ${fmtMoney(paid)}, к оплате ${fmtMoney(total - paid)}` : '';
  };

  if (b.status === 'pending' && b.source === 'direct' && b.hold_expires_at) {
    note.className = 'note';
    note.textContent = `Заявка с сайта. Подтвердите её — или она сама снимется ${fmtDateTime(b.hold_expires_at)}, и номер освободится.`;
    note.style.display = '';
  }
  if (imported) {
    note.className = 'note';
    note.textContent = `Бронь пришла с площадки «${SOURCE[b.source]}» через синхронизацию календаря. Даты и номер меняются на самой площадке. Имя гостя, телефон и сумму можно дописать здесь.`;
    note.style.display = '';
  }

  // несколько номеров одному гостю (групповая бронь)
  const extra = new Set();
  const extraBox = h('div', { class: 'type-filter', style: { display: 'none', marginTop: '-4px' } });
  const extraHint = h('div', { class: 'muted small', style: { marginBottom: '10px', display: 'none' } });
  const drawExtra = () => {
    extra.delete(f.room_id.value);
    extraBox.innerHTML = '';
    rooms.filter((r) => r.id !== f.room_id.value).forEach((r) => extraBox.append(h('button', { type: 'button', class: 'chip' + (extra.has(r.id) ? ' on' : ''), title: r.type,
      onclick: () => { if (extra.has(r.id)) extra.delete(r.id); else extra.add(r.id); drawExtra(); } }, r.name)));
    extraHint.style.display = extra.size ? '' : 'none';
    extraHint.textContent = `Будет создано броней: ${extra.size + 1}. Цена каждого номера считается по его тарифу, оплату можно вносить в любую.`;
  };
  f.room_id.addEventListener('change', () => { if (extraBox.style.display !== 'none') drawExtra(); });
  const extraToggle = isNew && !readOnly ? h('button', { type: 'button', class: 'btn small ghost', style: { marginBottom: '10px' }, onclick: () => {
    extraBox.style.display = extraBox.style.display === 'none' ? '' : 'none'; if (extraBox.style.display === '') drawExtra(); else { extra.clear(); extraHint.style.display = 'none'; }
  } }, '+ Ещё номера для этого гостя') : null;
  // связанные брони (группа / части переселения)
  const groupBox = h('div', { style: { display: 'none', marginBottom: '14px' } });
  if (!isNew && b.group_id) api('GET', `/api/bookings/${b.id}/group`).then((list) => {
    if (list.length < 2) return;
    groupBox.style.display = '';
    groupBox.append(h('h3', { style: { margin: '4px 0 8px', fontSize: '14px' } }, 'Связанные брони'),
      list.map((x) => h('div', { class: 'pay-row' + (x.id === b.id ? '' : ' click'), onclick: async () => {
        if (x.id === b.id) return;
        try { const full = await api('GET', `/api/bookings/${x.id}`); closeDrawer(); bookingDrawer(full, onSaved); } catch (ex) { toast(ex.message, true); }
      } }, h('span', { class: 'pay-sum', style: { minWidth: '70px' } }, `№${x.room_name}`), h('span', { class: 'muted small' }, `${fmtShort(x.check_in)} — ${fmtShort(x.check_out)}${x.status === 'cancelled' ? ' · отменена' : ''}${x.id === b.id ? ' · эта' : ''}`),
        h('span', { class: 'small' }, fmtMoney(x.total_price)))),
      can('manager') && !readOnly ? h('button', { type: 'button', class: 'btn small ghost danger', style: { marginTop: '6px' }, onclick: async () => {
        if (!confirm('Отменить все брони этой группы?')) return;
        try { await api('DELETE', `/api/bookings/${b.id}?group=1`); toast('Группа отменена'); closeDrawer(); onSaved ? onSaved() : render(); } catch (ex) { toast(ex.message, true); }
      } }, 'Отменить всю группу') : null);
  }).catch(() => {});
  const drawDraftSoon = () => f.check_out.dispatchEvent(new Event('change', { bubbles: true }));
  const ref = String(b.id || '').slice(0, 8).toUpperCase();
  const body = h('div', {},
    note,
    ref ? h('div', { class: 'ref-line muted' }, `Бронь № ${ref}`, h('button', { type: 'button', class: 'link', onclick: () => copyText(ref, 'Номер брони скопирован') }, 'скопировать')) : null,
    statusSeg,
    h('label', { class: 'field' }, h('span', {}, 'Номер'), f.room_id),
    extraToggle, extraBox, extraHint,
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Заезд'), f.check_in), h('label', { class: 'field' }, h('span', {}, 'Выезд'), f.check_out)),
    readOnly || imported ? null : h('div', { class: 'nights-chips' }, h('span', { class: 'muted small' }, 'Ночей:'),
      [1, 2, 3, 5, 7, 14].map((n) => h('button', { type: 'button', class: 'chip', onclick: () => { f.check_out.value = addDays(f.check_in.value, n); drawDraftSoon(); requote(); } }, n))),
    freeBox,
    groupBox,
    guestBox,
    h('label', { class: 'field' }, h('span', {}, 'Комментарий'), f.notes));
  const changeLogBox = h('div', { style: { display: 'none', marginBottom: '14px' } });
  const showChangeLog = async () => {
    try {
      const rows = await api('GET', `/api/bookings/${b.id}/log`);
      changeLogBox.innerHTML = ''; changeLogBox.style.display = '';
      const ACTION = { created: 'Создана', updated: 'Изменена', cancelled: 'Отменена', payment: 'Платёж' };
      changeLogBox.append(h('div', {}, h('h3', { style: { margin: '4px 0 8px' } }, 'История изменений'),
        rows.length ? rows.map((r) => h('div', { class: 'log-row' },
          h('div', { class: 'small' }, h('b', {}, ACTION[r.action] || r.action), h('span', { class: 'muted' }, ` · ${r.user_name} · ${fmtDateTime(r.created_at)}`)),
          r.details.summary ? h('div', { class: 'muted small' }, r.details.summary) : null,
          r.details.reason ? h('div', { class: 'muted small' }, r.details.reason) : null,
          (r.details.changes || []).map((c) => h('div', { class: 'small' }, `${c.field}: `, h('span', { class: 'muted' }, c.from), ' → ', h('b', {}, c.to)))))
          : h('div', { class: 'muted small' }, 'Записей пока нет (бронь создана до появления истории).')));
    } catch (ex) { toast(ex.message, true); }
  };
  const printVoucher = async () => {
    try {
      const prop = await api('GET', `/api/properties/${b.property_id}`);
      const room = allRooms().find((r) => r.id === b.room_id);
      const total = Number(b.total_price || 0), paidSum = Number(b.paid_amount || 0);
      const line = (k, v) => h('tr', {}, h('td', { style: { padding: '6px 10px 6px 0', color: '#555', width: '190px' } }, k), h('td', { style: { padding: '6px 0', fontWeight: 600 } }, v));
      document.getElementById('print-sheet')?.remove();
      document.body.append(h('div', { id: 'print-sheet' },
        letterhead(prop.name, [prop.address, prop.phone].filter(Boolean).join(' · ')),
        h('h1', { style: { fontSize: '22px', marginBottom: '2px' } }, 'Подтверждение бронирования'),
        h('p', { style: { marginTop: 0, marginBottom: '18px', color: '#555' } }, `№ ${String(b.id).slice(0, 8).toUpperCase()}`),
        h('table', { style: { borderCollapse: 'collapse', fontSize: '14px' } }, h('tbody', {},
          line('Гость', f.guest_name.value || '—'),
          line('Номер', room ? `№${room.name} (${room.type})` : '—'),
          line('Заезд', `${fmtDate(f.check_in.value)} ${parseISO(f.check_in.value).getFullYear()}, с ${String(prop.check_in_time).slice(0, 5)}`),
          line('Выезд', `${fmtDate(f.check_out.value)} ${parseISO(f.check_out.value).getFullYear()}, до ${String(prop.check_out_time).slice(0, 5)}`),
          line('Гостей', f.guests_count.value || '1'),
          line('Стоимость', fmtMoney(f.total_price.value || total)),
          line('Оплачено', fmtMoney(f.paid_amount ? f.paid_amount.value || paidSum : paidSum)),
          line('К оплате при заселении', fmtMoney(Math.max(Number(f.total_price.value || total) - Number(f.paid_amount ? f.paid_amount.value || paidSum : paidSum), 0))))),
        h('p', { style: { marginTop: '28px', color: '#555' } }, 'Ждём вас в гости!')));
      window.print();
    } catch (ex) { toast(ex.message, true); }
  };
  const guestHint = h('div', { style: { marginBottom: '10px' } });
  let draftTimer;
  const saveDraft = () => {
    if (!isNew || readOnly) return;
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => {
      const data = { room_id: f.room_id.value, check_in: f.check_in.value, check_out: f.check_out.value, guest_name: f.guest_name?.value || '', guest_phone: f.guest_phone?.value || '', guest_email: f.guest_email?.value || '', notes: f.notes.value, guests_count: f.guests_count?.value || 1, status: status.value };
      if (!data.guest_name && !data.guest_phone && !data.guest_email && !data.notes) { clearDraft(); return; }
      try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ at: Date.now(), property: state.propertyId, data })); } catch { /* приватный режим */ }
    }, 400);
  };
  const guestHistoryBox = h('div', { style: { display: 'none', marginBottom: '14px' } });
  const showGuestHistory = async () => {
    const phone = f.guest_phone.value.trim();
    if (!phone) { toast('Введите телефон гостя', true); return; }
    try {
      const gh = await api('GET', '/api/guests?' + qs({ phone }));
      guestHistoryBox.innerHTML = '';
      guestHistoryBox.style.display = '';
      if (!gh.visits) { guestHistoryBox.append(h('div', { class: 'note' }, 'Раньше не останавливался(ась)')); return; }
      guestHistoryBox.append(
        h('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '8px' } },
          gh.returning ? h('span', { class: 'pill ok' }, 'Постоянный гость') : null,
          h('span', { class: 'muted small' }, `${gh.visits} ${gh.visits === 1 ? 'визит' : 'визита'} · всего ${fmtMoney(gh.total_spent)}`)),
        h('div', {}, gh.stays.slice(0, 10).map((s) => h('div', {
          class: 'muted small', style: { padding: '4px 0', borderBottom: '1px solid var(--line)' },
        }, `${fmtShort(s.check_in)} — ${fmtShort(s.check_out)} · ${s.property_name}, ${s.room_name} · ${fmtMoney(s.total_price)}`))));
    } catch (ex) { toast(ex.message, true); }
  };
  guestBox.append(
    inp('guest_name', 'Гость', { autocomplete: 'off', placeholder: 'Имя и фамилия' }),
    h('div', { class: 'row2' }, inp('guest_phone', 'Телефон', { type: 'tel', placeholder: '+7 900 000-00-00', autocomplete: 'off' }), inp('guest_email', 'Email', { type: 'email' })),
    guestHint,
    h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' } },
      h('button', { type: 'button', class: 'btn small ghost', onclick: () => f.guest_phone.value.trim() ? guestDrawer(f.guest_phone.value.trim(), f.guest_name.value, onSaved) : toast('Введите телефон гостя', true) }, 'Карточка гостя'),
      isNew || readOnly ? null : h('button', { type: 'button', class: 'btn small ghost', onclick: () => messageDialog(b) }, 'Написать гостю'),
      readOnly || !isNew ? null : h('button', { type: 'button', class: 'btn small ghost', onclick: () => { f.paid_amount.value = f.total_price.value || 0; updateTotal(); } }, 'Оплачено полностью'),
      isNew ? null : h('button', { type: 'button', class: 'btn small ghost', onclick: printVoucher }, 'Печать подтверждения'),
      isNew ? null : h('button', { type: 'button', class: 'btn small ghost', onclick: () => printInvoice(b) }, 'Счёт'),
      !isNew && !readOnly && !imported && ['confirmed', 'pending'].includes(b.status) && diffDays(b.check_in, b.check_out) > 1 ? h('button', { type: 'button', class: 'btn small ghost', onclick: () => relocateDialog(b, rooms, onSaved) }, 'Переселить') : null),
    guestHistoryBox,
    h('div', { class: 'row3' },
      inp('guests_count', 'Гостей', { type: 'number', min: 1, value: b.guests_count || 1, oninput: () => requote() }),
      inp('total_price', 'Стоимость, ₽', { money: true, type: 'number', min: 0, value: b.total_price != null ? Math.round(b.total_price) : '', oninput: () => { priceTouched = true; updateTotal(); } }),
      isNew ? inp('paid_amount', 'Предоплата, ₽', { money: true, type: 'number', min: 0, value: 0, oninput: updateTotal }) : h('div')),
    isNew ? h('label', { class: 'field', style: { display: 'none' }, 'data-prepay': '1' }, h('span', {}, 'Как оплачена предоплата'), f.pay_method = h('select', { class: 'input' }, Object.entries(PAY_METHOD).map(([k, l]) => h('option', { value: k }, l)))) : null,
    h('label', { class: 'field' }, h('span', {}, 'Источник'), f.source),
    planField,
    h('div', { class: 'summary' }, nightsEl, totalEl), breakdownEl,
    isNew || status.value === 'blocked' ? null : moneyBlock(b, (m) => { b.total_price = m.total; b.paid_amount = m.paid; f.total_price.value = Math.round(Number(m.total)); priceTouched = true; updateTotal(); }));
  guestBox.style.display = status.value === 'blocked' ? 'none' : '';
  bindPhone(f.guest_phone);
  let hintTimer;
  const checkGuest = async () => {
    guestHint.innerHTML = '';
    if (readOnly || phoneDigits(f.guest_phone.value).length < 10) return;
    try {
      const g = await api('GET', '/api/guests/check?' + qs({ phone: f.guest_phone.value }));
      if (!g.known) return;
      if (g.blacklisted) guestHint.append(h('div', { class: 'note bad' }, h('b', {}, 'Гость в чёрном списке. '), g.blacklist_reason || ''));
      const bits = [];
      if (g.returning) bits.push(`постоянный гость, ${g.visits} ${plural(g.visits, ['визит', 'визита', 'визитов'])}`);
      else if (g.visits) bits.push(`уже останавливался(ась): ${g.visits} ${plural(g.visits, ['раз', 'раза', 'раз'])}`);
      if (g.tags?.length) bits.push(g.tags.join(', '));
      if (g.notes) bits.push(`заметка: ${g.notes}`);
      if (bits.length) guestHint.append(h('div', { class: 'note ok' }, bits.join(' · ')));
      if (isNew && !f.guest_name.value && g.name) f.guest_name.value = g.name;
    } catch { /* подсказка необязательна */ }
  };
  f.guest_phone.addEventListener('input', () => { clearTimeout(hintTimer); hintTimer = setTimeout(checkGuest, 350); });
  if (b.guest_phone) checkGuest();
  if (!isNew && can('manager')) {
    body.append(h('button', { type: 'button', class: 'btn small ghost', onclick: showChangeLog }, 'История изменений'), changeLogBox);
  }

  let offerConfirmation = null;
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true;
    const payload = {
      room_id: f.room_id.value, check_in: f.check_in.value, check_out: f.check_out.value, status: status.value,
      notes: f.notes.value,
    };
    if (status.value !== 'blocked') Object.assign(payload, {
      guest_name: f.guest_name.value, guest_phone: f.guest_phone.value, guest_email: f.guest_email.value,
      guests_count: f.guests_count.value || 1, total_price: f.total_price.value, source: f.source.value,
    });
    if (isNew && f.paid_amount) { payload.paid_amount = f.paid_amount.value || 0; payload.payment_method = f.pay_method.value; }
    if (isNew && f.rate_plan_id.value && status.value !== 'blocked') payload.rate_plan_id = f.rate_plan_id.value;
    if (isNew && extra.size) payload.extra_room_ids = [...extra];
    if (imported) { delete payload.room_id; delete payload.check_in; delete payload.check_out; delete payload.source; }
    try {
      let created = null;
      if (isNew) created = await api('POST', '/api/bookings', payload);
      else await api('PATCH', `/api/bookings/${b.id}`, payload);
      if (isNew && status.value !== 'blocked' && (f.guest_phone.value || f.guest_email.value)) offerConfirmation = created;
      if (isNew) clearDraft();
      toast(isNew ? (status.value === 'blocked' ? (extra.size ? 'Даты закрыты в нескольких номерах' : 'Даты закрыты') : (extra.size ? `Создано броней: ${extra.size + 1}` : 'Бронь создана')) : 'Изменения сохранены');
      closeDrawer(); onSaved ? onSaved() : render();
      if (offerConfirmation) offerSendConfirmation(offerConfirmation);
    } catch (ex) {
      note.className = 'note bad'; note.textContent = ex.message; note.style.display = '';
      if (ex.data?.field && f[ex.data.field]) f[ex.data.field].classList.add('invalid');
    } finally { save.disabled = false; }
  } }, isNew ? 'Создать' : 'Сохранить');

  const remove = !isNew && can('manager') ? h('button', { class: 'btn danger ghost', onclick: async () => {
    const blocked = b.status === 'blocked' && !imported;
    if (!confirm(blocked ? 'Открыть эти даты для продажи?' : 'Отменить бронь? Номер освободится на всех площадках при следующей синхронизации.')) return;
    try {
      await api('DELETE', `/api/bookings/${b.id}`); closeDrawer(); onSaved ? onSaved() : render();
      toastUndo(blocked ? 'Даты открыты' : 'Бронь отменена', () => (blocked
        ? api('POST', '/api/bookings', { room_id: b.room_id, check_in: b.check_in, check_out: b.check_out, status: 'blocked', notes: b.notes })
        : api('PATCH', `/api/bookings/${b.id}`, { status: b.status })), () => (onSaved ? onSaved() : render()));
    } catch (ex) { toast(ex.message, true); }
  } }, b.status === 'blocked' && !imported ? 'Открыть даты' : 'Отменить бронь') : null;

  const title = isNew ? 'Новая бронь' : (b.status === 'blocked' ? 'Закрытые даты' : (b.guest_name || `Бронь ${SOURCE[b.source]}`));
  openDrawer(title, body, readOnly ? null : [remove, h('span', { class: 'spacer' }), h('button', { class: 'btn foot-close', onclick: requestCloseDrawer }, 'Закрыть'), save],
    { guard: !readOnly, onDismiss: isNew ? () => true : undefined });
  if (isNew) { body.addEventListener('input', saveDraft); body.addEventListener('change', saveDraft); }
  if (restored) {
    note.className = 'note'; note.style.display = '';
    note.append('Восстановлен черновик брони, который вы не успели сохранить. ', h('button', { type: 'button', class: 'link', onclick: () => { clearDraft(); closeDrawer(); bookingDrawer({}, onSaved); } }, 'Начать заново'));
  }
  updateTotal();
  requote();
}

// ---------- цена на дату из шахматки ----------
function rateDrawer(t, day, reload) {
  const rate = t.rates[day] || {};
  const f = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  f.from = h('input', { class: 'input', type: 'date', value: day });
  f.to = h('input', { class: 'input', type: 'date', value: day });
  f.price = h('input', { class: 'input', money: true, type: 'number', min: 0, value: rate.price != null ? Math.round(rate.price) : '', placeholder: `Базовая: ${Math.round(t.base_price)}` });
  f.min = h('input', { class: 'input', type: 'number', min: 1, value: rate.min_stay || '', placeholder: `Базовый: ${t.min_stay}` });
  f.closed = h('input', { type: 'checkbox', checked: !!rate.closed });
  const send = async (payload) => {
    try {
      await api('PUT', '/api/rates', { room_type_ids: [t.id], date_from: f.from.value, date_to: f.to.value, ...payload });
      toast('Цены обновлены'); closeDrawer(); reload();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  };
  openDrawer(`${t.name}: цена`, h('div', {}, err,
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'С'), f.from), h('label', { class: 'field' }, h('span', {}, 'По (включительно)'), f.to)),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Цена за ночь, ₽'), f.price), h('label', { class: 'field' }, h('span', {}, 'Мин. ночей'), f.min)),
    h('label', { class: 'check', style: { marginBottom: '14px' } }, f.closed, 'Закрыть продажи на эти даты'),
    h('p', { class: 'muted small' }, 'Закрытые даты уходят на площадки как занятые. Цены на площадки через iCal не передаются — их нужно менять в личных кабинетах площадок.')),
  [h('button', { class: 'btn ghost', onclick: () => send({ reset: true }) }, 'Сбросить к базовой'), h('span', { class: 'spacer' }),
    h('button', { class: 'btn primary', onclick: () => send({ price: f.price.value, min_stay: f.min.value, closed: f.closed.checked }) }, 'Сохранить')]);
}

// ---------- уборка ----------
const HK = { clean: 'Чистый', dirty: 'Нужна уборка', cleaning: 'Убирают', inspect: 'Ждёт проверки', repair: 'Ремонт', occupied: 'Заселён' };
const HK_ORDER = ['dirty', 'cleaning', 'inspect', 'repair', 'clean', 'occupied'];

async function viewCleaning(main) {
  const manager = can('manager');
  const mineOnly = { value: store.get('hk_mine') === '1' };
  const box = h('div', { class: 'stack' });
  const sum = h('div', { class: 'hk-sum' });
  const mineBtn = h('button', { class: 'btn', type: 'button', onclick: () => { mineOnly.value = !mineOnly.value; store.set('hk_mine', mineOnly.value ? '1' : '0'); draw(); } });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Уборка'), mineBtn), sum, box);
  let data = null;
  const setStatus = async (room, status, note) => {
    try { await api('POST', `/api/rooms/${room.id}/status`, { status, note }); await load(); }
    catch (ex) { toast(ex.message, true); }
  };
  const repairDialog = (room) => {
    const note = h('textarea', { class: 'input', placeholder: 'Что случилось: течёт кран, не работает розетка, разбито окно…' });
    const err = h('div', { class: 'note bad', style: { display: 'none' } });
    openModal(`Поломка в номере ${room.name}`, h('div', {}, err, h('label', { class: 'field' }, h('span', {}, 'Что сломалось'), note),
      h('p', { class: 'muted small', style: { marginBottom: 0 } }, 'Администратор сразу увидит сообщение в колокольчике и (если подключён) в Telegram.')),
    [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
      try { await api('POST', `/api/rooms/${room.id}/status`, { status: 'repair', note: note.value }); closeModal(); toast('Сообщение отправлено'); load(); }
      catch (ex) { err.textContent = ex.message; err.style.display = ''; }
    } }, 'Сообщить')]);
  };
  const noteDialog = (room) => {
    const note = h('textarea', { class: 'input', placeholder: 'Ключ у соседей, диван раскладывается, не включать кондиционер…' }, room.note || '');
    openModal(`Заметка к номеру ${room.name}`, h('div', {}, h('label', { class: 'field' }, h('span', {}, 'Видят все сотрудники'), note)),
      [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
        try { await api('PUT', `/api/rooms/${room.id}/note`, { note: note.value }); closeModal(); load(); } catch (ex) { toast(ex.message, true); }
      } }, 'Сохранить')]);
  };
  const actions = (room) => {
    const b = (label, cls, fn) => h('button', { class: `btn small ${cls || ''}`, type: 'button', onclick: fn }, label);
    const out = [];
    if (room.status === 'dirty') out.push(b('Начать уборку', '', () => setStatus(room, 'cleaning')), b('Убрано', 'primary', () => setStatus(room, 'clean')));
    if (room.status === 'cleaning') out.push(b('Убрано', 'primary', () => setStatus(room, 'clean')), b('На проверку', '', () => setStatus(room, 'inspect')));
    if (room.status === 'inspect') out.push(manager ? b('Проверено', 'primary', () => setStatus(room, 'clean')) : h('span', { class: 'muted small' }, 'Ждёт проверки администратором'), b('Переделать', '', () => setStatus(room, 'dirty')));
    if (room.status === 'repair') out.push(manager ? b('Исправлено', 'primary', () => setStatus(room, 'dirty')) : null);
    if (room.status === 'clean' || room.status === 'occupied') out.push(b('Нужна уборка', 'ghost', () => setStatus(room, 'dirty')));
    if (room.status !== 'repair') out.push(b('Поломка', 'ghost', () => repairDialog(room)));
    if (manager) out.push(b(room.note ? 'Заметка' : '+ Заметка', 'ghost', () => noteDialog(room)));
    return out;
  };
  const roomCard = (room) => h('div', { class: `hk-card hk-${room.status}` },
    h('div', { class: 'hk-head' }, h('b', { class: 'hk-name' }, room.name), h('span', { class: 'muted small' }, room.type), h('span', { class: `hk-pill hk-${room.status}` }, HK[room.status])),
    h('div', { class: 'hk-tags' },
      room.arrives_today ? h('span', { class: 'tag warn' }, 'заезд сегодня') : (room.next_arrival ? h('span', { class: 'tag' }, `заезд ${fmtDate(room.next_arrival)}`) : null),
      room.departs_today ? h('span', { class: 'tag' }, `выезд${room.departing ? ': ' + room.departing : ''}`) : null,
      room.assigned_name ? h('span', { class: 'tag' }, `убирает: ${room.assigned_name}`) : null),
    room.hk_note ? h('div', { class: 'note bad', style: { margin: '8px 0 0' } }, room.hk_note) : null,
    room.note ? h('div', { class: 'hk-note' }, room.note) : null,
    h('div', { class: 'hk-actions' }, ...actions(room).filter(Boolean)),
    manager && data.housekeepers.length && room.status !== 'occupied' ? h('select', { class: 'input hk-assign', 'aria-label': 'Назначить горничной', onchange: async (e) => {
      try { await api('POST', '/api/housekeeping/assign', { room_ids: [room.id], user_id: e.target.value || null }); load(); } catch (ex) { toast(ex.message, true); }
    } }, h('option', { value: '' }, 'Не назначено'), data.housekeepers.map((u) => h('option', { value: u.id, selected: u.id === room.assigned_to }, u.name))) : null);
  function draw() {
    if (!data) return;
    mineBtn.textContent = mineOnly.value ? 'Показать все номера' : 'Только мои номера';
    mineBtn.style.display = data.rooms.some((r) => r.assigned_to === data.me) ? '' : 'none';
    sum.innerHTML = '';
    HK_ORDER.forEach((k) => { if (data.counts[k]) sum.append(h('span', { class: `hk-pill hk-${k}` }, `${HK[k]}: ${data.counts[k]}`)); });
    box.innerHTML = '';
    let rooms = data.rooms;
    if (mineOnly.value) rooms = rooms.filter((r) => r.assigned_to === data.me);
    const urgency = (r) => (r.arrives_today ? 0 : 1);
    HK_ORDER.forEach((k) => {
      const list = rooms.filter((r) => r.status === k).sort((a, b2) => urgency(a) - urgency(b2));
      if (!list.length) return;
      box.append(h('div', {}, h('h2', { class: 'hk-title' }, `${HK[k]} · ${list.length}`), h('div', { class: 'hk-grid' }, list.map(roomCard))));
    });
    if (!rooms.length) box.append(h('div', { class: 'card empty' }, h('h3', {}, 'Номеров нет'), 'Номера добавляются в «Настройках».'));
  }
  async function load() { data = await api('GET', '/api/housekeeping?' + qs({ property_id: state.propertyId })); draw(); }
  load().catch((ex) => box.append(h('div', { class: 'card empty' }, ex.message)));
  autoRefresh(load);
}

// ---------- сегодня ----------
async function viewToday(main) {
  let day = todayISO();
  let lastData = null;
  const scope = { value: 'current' };
  const content = h('div');
  const dateInput = h('input', { class: 'input', type: 'date', value: day, style: { width: '160px' }, onchange: (e) => { day = e.target.value || todayISO(); load(); } });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Заезды и выезды'),
    h('button', { class: 'btn icon', 'aria-label': 'Предыдущий день', onclick: () => { day = addDays(day, -1); dateInput.value = day; load(); } }, icon('left')),
    dateInput,
    h('button', { class: 'btn icon', 'aria-label': 'Следующий день', onclick: () => { day = addDays(day, 1); dateInput.value = day; load(); } }, icon('right')),
    scopeSeg(scope, () => load()),
    h('button', { class: 'btn', onclick: () => lastData && printDaySheet(day, lastData) }, icon('print'), 'Печать')), content);
  const item = (b, kind) => {
    const due = Number(b.total_price) - Number(b.paid_amount);
    return h('div', { class: 'item', onclick: () => bookingDrawer(b, load) },
      h('div', { class: 'room-chip' }, b.room_name),
      h('div', { style: { flex: 1, minWidth: 0 } },
        h('div', { style: { fontWeight: 600 } }, b.guest_name || `Гость с площадки ${SOURCE[b.source]}`,
          scope.value === 'all' ? h('span', { class: 'muted small', style: { fontWeight: 400 } }, ' · ', b.property_name) : null),
        h('div', { class: 'muted small' }, `${fmtShort(b.check_in)} — ${fmtShort(b.check_out)} · ${count(b.guests_count, 'guest')} · ${SOURCE[b.source]}`),
        b.guest_phone ? h('a', { class: 'small tel', href: `tel:${b.guest_phone}`, onclick: (e) => e.stopPropagation() }, b.guest_phone) : null),
      kind !== 'staying' && due > 0 && can('manager') ? h('span', { class: 'pill warn num' }, `к оплате ${fmtMoney(due)}`) : null,
      b.status === 'pending' ? h('span', { class: 'pill warn' }, 'заявка') : null,
      kind === 'out' && day === todayISO() ? cleaningControl(b) : null);
  };
  // Уборка: номер, из которого сегодня выезжают, «ждёт уборки», пока горничная (или любой сотрудник) не отметит его убранным
  const cleaningControl = (b) => {
    const clean = b.room_cleaned_on && b.room_cleaned_on.slice(0, 10) === day;
    return h('button', {
      class: 'btn small' + (clean ? ' ok-btn' : ''), title: clean ? 'Нажмите, чтобы снять отметку' : 'Отметить номер убранным',
      onclick: async (e) => {
        e.stopPropagation();
        try { await api('POST', `/api/rooms/${b.room_id}/cleaned`, { cleaned: !clean }); load(); } catch (ex) { toast(ex.message, true); }
      },
    }, clean ? '✓ Убран' : 'Убрать');
  };
  const block = (title, list, kind, emptyText) => h('div', { class: 'card' },
    h('div', { class: 'card-head' }, h('h2', {}, title), h('span', { class: 'pill none num' }, list.length)),
    list.length ? h('div', { class: 'day-list' }, list.map((b) => item(b, kind))) : h('div', { class: 'empty' }, emptyText));
  const load = async () => {
    try {
      const d = await api('GET', '/api/today?' + qs({ date: day, property_id: scope.value === 'current' ? state.propertyId : undefined, summary: can('manager') && day === todayISO() ? 1 : undefined }));
      lastData = d;
      content.innerHTML = '';
      const dueToday = [...d.arrivals, ...d.departures].reduce((sum, b) => sum + Math.max(Number(b.total_price) - Number(b.paid_amount), 0), 0);
      content.append(
        h('p', { class: 'muted', style: { marginTop: '-6px' } }, `${fmtDate(day)}, ${WD[parseISO(day).getDay()].toLowerCase()}`),
        d.summary ? homeSummary(d.summary) : '',
        h('div', { class: 'kpis' },
          kpiCard('Заезды', String(d.arrivals.length)), kpiCard('Выезды', String(d.departures.length)),
          kpiCard('Проживают', String(d.staying.length)),
          kpiCard('Свободно на ночь', `${d.free_tonight}`, `из ${d.rooms_total}`),
          day === todayISO() ? kpiCard('Ждут уборки', String(d.departures.filter((b) => !(b.room_cleaned_on && b.room_cleaned_on.slice(0, 10) === day)).length)) : null,
          can('manager') ? kpiCard('К доплате по заездам и выездам', fmtMoney(dueToday)) : null),
        h('div', { class: 'grid-2' },
          block('Заезды', d.arrivals, 'in', 'Заездов нет'),
          block('Выезды', d.departures, 'out', 'Выездов нет'),
          block('Проживают', d.staying, 'staying', 'Сейчас никто не проживает')));
    } catch (ex) { content.innerHTML = ''; content.append(h('div', { class: 'card empty' }, ex.message)); }
  };
  load();
  autoRefresh(load);
}

// Главное за минуту: что требует внимания и итог месяца на сегодня (вверху страницы «Сегодня» у владельца и администратора)
function homeSummary(sm) {
  const a = sm.alerts, m = sm.month;
  const items = [
    a.requests ? ['Заявки с сайта ждут ответа', `${a.requests}`, '#/bookings', 'warn'] : null,
    a.conflicts ? ['Конфликты с площадок', `${a.conflicts}`, '#/channels', 'bad'] : null,
    a.debt_count ? ['Гости должны', fmtMoney(a.debt_amount), '#/bookings', 'warn', `${a.debt_count} ${plural(a.debt_count, ['бронь', 'брони', 'броней'])}`] : null,
    a.repairs ? ['Номера в ремонте', `${a.repairs}`, '#/cleaning', 'bad'] : null,
  ].filter(Boolean);
  const month = MONTHS_NOM[parseISO(m.from).getMonth()];
  return h('div', { class: 'home-summary' },
    h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '10px' } }, 'Требует внимания'),
      items.length ? h('div', { class: 'alert-list' }, items.map(([t, v, href, cls, sub]) => h('a', { href, class: `alert-item ${cls}` }, h('span', {}, t, sub ? h('small', {}, sub) : null), h('b', {}, v))))
        : h('div', { class: 'muted' }, 'Всё спокойно: заявок, конфликтов, долгов и поломок нет.')),
    h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '10px' } }, `${month}: итог на сегодня`),
      h('div', { class: 'month-grid' },
        h('div', {}, h('span', { class: 'muted small' }, 'Выручка'), h('b', {}, fmtMoney(m.revenue))),
        h('div', {}, h('span', { class: 'muted small' }, 'Расходы'), h('b', {}, fmtMoney(m.expenses))),
        h('div', {}, h('span', { class: 'muted small' }, 'Прибыль'), h('b', { class: Number(m.profit) < 0 ? 'neg' : 'pos' }, fmtMoney(m.profit))),
        h('div', {}, h('span', { class: 'muted small' }, 'Загрузка'), h('b', {}, `${m.occupancy}%`))),
      h('a', { href: '#/stats', class: 'small', style: { display: 'inline-block', marginTop: '8px' } }, 'Подробнее в отчётах →')));
}

// ---------- печатный лист ----------
function printDaySheet(day, data) {
  document.getElementById('print-sheet')?.remove();
  const W = { 'Номер': '9%', 'Гость': '30%', 'Телефон': '21%', 'Гостей': '8%', 'К оплате': '14%', 'Отметка': '18%' };
  const th = (t) => h('th', { style: { textAlign: 'left', borderBottom: '2px solid #000', padding: '5px 6px', fontSize: '13px', width: W[t] } }, t);
  const td = (t) => h('td', { style: { borderBottom: '1px solid #999', padding: '6px', fontSize: '13px' } }, t);
  const section = (title, list, withDue) => {
    const cols = ['Номер', 'Гость', 'Телефон', 'Гостей', withDue ? 'К оплате' : null, 'Отметка'].filter(Boolean);
    const rows = list.length
      ? list.map((b) => h('tr', {}, td(b.room_name), td(b.guest_name || `Гость (${SOURCE[b.source]})`), td(b.guest_phone || '—'),
          td(String(b.guests_count)), withDue ? td(fmtMoney(Number(b.total_price) - Number(b.paid_amount))) : null,
          h('td', { style: { borderBottom: '1px solid #999', width: '70px' } })))
      : [h('tr', {}, h('td', { colspan: String(cols.length), style: { padding: '6px', color: '#666' } }, 'Нет'))];
    return h('div', { style: { marginBottom: '26px' } },
      h('h2', { style: { margin: '0 0 8px', fontSize: '16px' } }, title),
      h('table', { style: { width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' } },
        h('thead', {}, h('tr', {}, cols.map(th))), h('tbody', {}, rows)));
  };
  const sheet = h('div', { id: 'print-sheet' },
    letterhead((state.me.properties.find((p) => p.id === state.propertyId) || {}).name || 'Флигель'),
    h('h1', { style: { fontSize: '20px', marginBottom: '4px' } }, 'Заезды и выезды'),
    h('p', { style: { marginTop: 0, marginBottom: '18px', color: '#333' } }, `${fmtDate(day)}, ${WD[parseISO(day).getDay()].toLowerCase()}`),
    section('Заезды', data.arrivals, true),
    section('Выезды', data.departures, true),
    section('Проживают', data.staying, false));
  document.body.append(sheet);
  window.print();
}

// ---------- список броней ----------
async function viewBookings(main) {
  const scope = { value: 'current' };
  const f = {
    q: h('input', { class: 'input', placeholder: 'Имя, телефон или email', style: { width: '240px' } }),
    from: h('input', { class: 'input', type: 'date', value: addDays(todayISO(), -7), style: { width: '150px' } }),
    to: h('input', { class: 'input', type: 'date', value: addDays(todayISO(), 60), style: { width: '150px' } }),
    status: h('select', { class: 'input', style: { width: '170px' } }, h('option', { value: '' }, 'Все активные'),
      Object.entries(STATUS).map(([k, l]) => h('option', { value: k, selected: k === store.get('bk_status', '') }, l))),
  };
  let chip = store.get('bk_chip', 'all');
  const chips = h('div', { class: 'type-filter' });
  const drawChips = () => {
    chips.innerHTML = '';
    [['all', 'Все'], ['requests', 'Заявки с сайта'], ['debt', 'Должны оплатить'], ['arrive', 'Заезжают сегодня']].forEach(([k, l]) => chips.append(h('button', { type: 'button', class: 'chip' + (chip === k ? ' on' : ''),
      onclick: () => { chip = k; store.set('bk_chip', k); drawChips(); shown = PAGE; draw(); } }, l)));
  };
  const table = h('div', { class: 'card' });
  let timer;
  Object.values(f).forEach((el) => el.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 250); }));
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Брони'),
    h('button', { class: 'btn', onclick: () => downloadCsv('/api/bookings/export.csv?' + qs({
      q: f.q.value, from: f.from.value, to: f.to.value, status: f.status.value,
      property_id: scope.value === 'current' ? state.propertyId : undefined }), `bookings_${f.from.value}_${f.to.value}.csv`) }, icon('download'), 'CSV'),
    h('button', { class: 'btn', onclick: () => importDialog(load) }, icon('upload'), 'Импорт'),
    h('button', { class: 'btn primary', onclick: () => bookingDrawer({}, load) }, icon('plus'), 'Бронь')),
  h('div', { class: 'board-tools', style: { marginBottom: '10px' } }, f.q, f.from, '—', f.to, f.status, scopeSeg(scope, () => load())), chips, table);
  const PAGE = 50;
  let shown = PAGE;
  let all = [];
  let rows = [];
  const draw = () => {
    table.innerHTML = '';
    const today = todayISO();
    rows = all.filter((b) => (chip === 'requests' ? b.status === 'pending' && b.source === 'direct'
      : chip === 'debt' ? b.status === 'confirmed' && Number(b.total_price) > Number(b.paid_amount)
      : chip === 'arrive' ? b.check_in === today && b.status !== 'cancelled' && b.status !== 'blocked' : true));
    if (!rows.length) {
      table.append(h('div', { class: 'empty' }, h('h3', {}, all.length ? 'В этом разделе пусто' : 'Броней не найдено'),
        all.length ? 'Нажмите «Все», чтобы увидеть остальные брони периода.' : 'Измените период или поиск — или создайте бронь.',
        h('div', { style: { marginTop: '12px' } }, can('manager') ? h('button', { class: 'btn primary', onclick: () => bookingDrawer({}, load) }, icon('plus'), 'Создать бронь') : null)));
      return;
    }
    const part = rows.slice(0, shown);
    const multi = scope.value === 'all';
    table.append(...[
      h('div', { class: 'card-head' }, h('h2', {}, 'Найдено броней'), h('span', { class: 'pill none num' }, rows.length)),
      h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' },
        h('thead', {}, h('tr', {}, [multi ? 'Объект' : null, 'Заезд', 'Выезд', 'Номер', 'Гость', 'Источник', 'Статус', 'Сумма', 'Оплачено', ''].filter((t) => t !== null).map((t) => h('th', {}, t)))),
        h('tbody', {}, part.map((b) => h('tr', { class: 'click', onclick: () => bookingDrawer(b, load) },
          multi ? h('td', { class: 'muted small', 'data-l': 'Объект' }, b.property_name) : null,
          h('td', { class: 'num', 'data-l': 'Заезд' }, fmtShort(b.check_in), h('div', { class: 'muted small' }, humanDay(b.check_in))), h('td', { class: 'num', 'data-l': 'Выезд' }, fmtShort(b.check_out)),
          h('td', { class: 'num', 'data-l': 'Номер' }, b.room_name),
          h('td', { 'data-l': 'Гость' }, b.status === 'blocked' ? h('span', { class: 'muted' }, 'Закрыто') : (b.guest_name || h('span', { class: 'muted' }, '—')),
            b.guest_phone ? h('div', { class: 'muted small' }, b.guest_phone) : null),
          h('td', { 'data-l': 'Источник' }, h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: '6px' } }, h('i', { class: 'dot', style: { background: `var(--src-${b.source})` } }), SOURCE[b.source])),
          h('td', { 'data-l': 'Статус' }, h('span', { class: 'pill ' + ({ confirmed: 'ok', pending: 'warn', blocked: 'none', cancelled: 'bad' }[b.status]) }, STATUS[b.status])),
          h('td', { class: 'num', 'data-l': b.status === 'blocked' ? null : 'Сумма' }, b.status === 'blocked' ? '' : fmtMoney(b.total_price)),
          h('td', { class: 'num', 'data-l': b.status === 'blocked' ? null : 'Оплачено' }, b.status === 'blocked' ? '' : fmtMoney(b.paid_amount)),
          h('td', { class: 'wide row-actions' }, b.status === 'pending' && !b.feed_id ? [
            h('button', { class: 'btn small primary', onclick: async (e) => {
              e.stopPropagation();
              try {
                await api('PATCH', `/api/bookings/${b.id}`, { status: 'confirmed' }); load(); refreshBadges();
                toastUndo('Бронь подтверждена', () => api('PATCH', `/api/bookings/${b.id}`, { status: 'pending' }), () => { load(); refreshBadges(); });
              } catch (ex) { toast(ex.message, true); }
            } }, 'Подтвердить'),
            h('button', { class: 'btn small ghost danger', onclick: async (e) => {
              e.stopPropagation();
              try {
                await api('DELETE', `/api/bookings/${b.id}`); load(); refreshBadges();
                toastUndo(`Заявка${b.guest_name ? ` от «${b.guest_name}»` : ''} отклонена, номер освободился`, () => api('PATCH', `/api/bookings/${b.id}`, { status: 'pending' }), () => { load(); refreshBadges(); });
              } catch (ex) { toast(ex.message, true); }
            } }, 'Отклонить')] : null)))))),
      rows.length > shown ? h('div', { class: 'more-count' }, h('button', { class: 'btn', onclick: () => { shown += PAGE; draw(); } },
        `Показать ещё (${Math.min(PAGE, rows.length - shown)} из ${rows.length - shown} оставшихся)`)) : null,
    ].filter(Boolean));
  };
  async function load() {
    store.set('bk_status', f.status.value);
    if (!all.length) { table.innerHTML = ''; table.append(skeleton(6)); }
    try {
      all = await api('GET', '/api/bookings?' + qs({
        q: f.q.value, from: f.from.value, to: f.to.value, status: f.status.value,
        property_id: scope.value === 'current' ? state.propertyId : undefined,
      }));
      shown = PAGE;
      draw();
    } catch (ex) { table.innerHTML = ''; table.append(h('div', { class: 'empty' }, ex.message)); }
  }
  drawChips();
  load();
}

// ---------- цены ----------
// Календарь цен на 3 месяца: выделите даты (клик, Shift — диапазон) и измените цену / минимум ночей / закрытие сразу
async function priceCalendar(card, prop) {
  const first = new Date(); first.setDate(1);
  const start = iso(first);
  const endD = new Date(first.getFullYear(), first.getMonth() + 3, 1);
  const days = Math.round((endD - first) / 86400000);
  const data = await api('GET', '/api/board?' + qs({ property_id: prop.id, from: start, days }));
  const typeId = { value: store.get('cal_type') && data.room_types.some((t) => t.id === store.get('cal_type')) ? store.get('cal_type') : data.room_types[0]?.id };
  const selected = new Set();
  let lastClicked = null;
  const f = {
    price: h('input', { class: 'input', money: true, type: 'number', min: 0, placeholder: 'Не менять' }),
    min: h('input', { class: 'input', type: 'number', min: 1, placeholder: 'Не менять' }),
    closed: h('select', { class: 'input' }, h('option', { value: '' }, 'Не менять'), h('option', { value: 'true' }, 'Закрыть продажи'), h('option', { value: 'false' }, 'Открыть продажи')),
    all: h('input', { type: 'checkbox' }),
  };
  const info = h('b', {});
  const bar = h('div', { class: 'cal-bar' });
  const grid = h('div', { class: 'cal-months' });
  const tabs = h('div', { class: 'seg', style: { flexWrap: 'wrap' } });
  const type = () => data.room_types.find((t) => t.id === typeId.value);
  const updateBar = () => {
    info.textContent = selected.size ? `Выбрано: ${selected.size} ${plural(selected.size, ['дата', 'даты', 'дат'])}` : 'Выберите даты в календаре';
    bar.style.display = selected.size ? '' : 'none';
    grid.querySelectorAll('.cal-day').forEach((el) => el.classList.toggle('sel', selected.has(el.dataset.d)));
  };
  const apply = async (reset) => {
    const ids = f.all.checked ? data.room_types.map((t) => t.id) : [typeId.value];
    const dates = [...selected].sort();
    const payload = { room_type_ids: ids, date_from: dates[0], date_to: dates[dates.length - 1], dates };
    if (reset) payload.reset = true;
    else Object.assign(payload, { price: f.price.value, min_stay: f.min.value, closed: f.closed.value === '' ? null : f.closed.value === 'true' });
    try {
      await api('PUT', '/api/rates', payload);
      toast(reset ? 'Возвращены базовые цены' : 'Цены обновлены');
      selected.clear(); f.price.value = ''; f.min.value = ''; f.closed.value = '';
      const fresh = await api('GET', '/api/board?' + qs({ property_id: prop.id, from: start, days }));
      data.room_types = fresh.room_types; drawGrid();
    } catch (ex) { toast(ex.message, true); }
  };
  bar.append(info, h('div', { class: 'row3' },
    h('label', { class: 'field' }, h('span', {}, 'Цена за ночь, ₽'), f.price), h('label', { class: 'field' }, h('span', {}, 'Минимум ночей'), f.min), h('label', { class: 'field' }, h('span', {}, 'Продажи'), f.closed)),
    h('label', { class: 'check', style: { marginBottom: '10px' } }, f.all, 'Применить ко всем категориям'),
    h('div', { class: 'money-actions' },
      h('button', { class: 'btn primary', type: 'button', onclick: () => apply(false) }, 'Применить'),
      h('button', { class: 'btn ghost', type: 'button', onclick: () => confirm('Вернуть базовые цены на выбранные даты?') && apply(true) }, 'Сбросить к базовой'),
      h('button', { class: 'btn ghost', type: 'button', onclick: () => { selected.clear(); updateBar(); } }, 'Снять выделение')));
  function pick(d, shift) {
    if (shift && lastClicked) {
      const [a, b] = [lastClicked, d].sort();
      for (let x = a; x <= b; x = addDays(x, 1)) selected.add(x);
    } else if (selected.has(d)) selected.delete(d); else selected.add(d);
    lastClicked = d; updateBar();
  }
  function drawGrid() {
    tabs.innerHTML = '';
    data.room_types.forEach((t) => tabs.append(h('button', { type: 'button', class: t.id === typeId.value ? 'on' : '', onclick: () => { typeId.value = t.id; store.set('cal_type', t.id); selected.clear(); drawGrid(); } }, t.name)));
    grid.innerHTML = '';
    const t = type(); if (!t) return;
    const today = todayISO();
    for (let m = 0; m < 3; m++) {
      const md = new Date(first.getFullYear(), first.getMonth() + m, 1);
      const dim = new Date(md.getFullYear(), md.getMonth() + 1, 0).getDate();
      const lead = (md.getDay() + 6) % 7;
      const monthDates = Array.from({ length: dim }, (_, i) => iso(new Date(md.getFullYear(), md.getMonth(), i + 1)));
      grid.append(h('div', { class: 'cal-month' },
        h('div', { class: 'cal-title' }, h('b', {}, `${MONTHS_NOM[md.getMonth()]} ${md.getFullYear()}`),
          h('span', { class: 'cal-links' },
            h('button', { type: 'button', class: 'link', onclick: () => { monthDates.filter((d) => d >= today).forEach((d) => selected.add(d)); updateBar(); } }, 'весь месяц'),
            h('button', { type: 'button', class: 'link', onclick: () => { monthDates.filter((d) => d >= today && [5, 6].includes((parseISO(d).getDay() + 6) % 7)).forEach((d) => selected.add(d)); updateBar(); } }, 'выходные'))),
        h('div', { class: 'cal-grid' },
          ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((w, i) => h('div', { class: 'cal-wd' + (i > 4 ? ' we' : '') }, w)),
          Array.from({ length: lead }, () => h('div')),
          monthDates.map((d) => {
            const r = t.rates[d]; const dt = parseISO(d); const past = d < today;
            const price = r?.price ?? t.base_price;
            return h('button', { type: 'button', 'data-d': d, disabled: past,
              class: 'cal-day' + (r?.price != null ? ' custom' : '') + (r?.closed ? ' closed' : '') + (past ? ' past' : '') + (d === today ? ' today' : '') + ([0, 6].includes(dt.getDay()) || holidayName(d) ? ' we' : ''),
              title: `${holidayName(d) ? holidayName(d) + '. ' : ''}${fmtDate(d)}: ${fmtMoney(price)}${r?.min_stay ? `, от ${count(r.min_stay, 'night')}` : ''}${r?.closed ? ', продажи закрыты' : ''}`,
              onclick: (e) => pick(d, e.shiftKey) }, h('span', { class: 'n' }, dt.getDate()), h('span', { class: 'p' }, r?.closed ? '×' : fmtPriceCell(price)));
          }))));
    }
    updateBar();
  }
  card.innerHTML = '';
  card.className = 'card card-pad';
  card.append(h('div', { class: 'card-head', style: { padding: 0, marginBottom: '10px' } }, h('h2', {}, 'Календарь цен'), h('span', { class: 'muted small' }, 'цена, минимум ночей и закрытие продаж на 3 месяца вперёд')),
    tabs, grid, bar);
  drawGrid();
}

// ---------- цены и ограничения ----------
async function viewRates(main) {
  const content = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Цены и ограничения')), content);
  const prop = await api('GET', `/api/properties/${state.propertyId}`);
  const f = { types: {}, days: {} };
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  f.from = h('input', { class: 'input', type: 'date', value: todayISO() });
  f.to = h('input', { class: 'input', type: 'date', value: addDays(todayISO(), 30) });
  f.price = h('input', { class: 'input', money: true, type: 'number', min: 0, placeholder: 'Не менять' });
  f.min = h('input', { class: 'input', type: 'number', min: 1, placeholder: 'Не менять' });
  f.closed = h('select', { class: 'input' }, h('option', { value: '' }, 'Не менять'), h('option', { value: 'true' }, 'Закрыть продажи'), h('option', { value: 'false' }, 'Открыть продажи'));
  const dayOrder = [1, 2, 3, 4, 5, 6, 0];
  const preview = h('div', { class: 'card' });
  const send = async (reset) => {
    const ids = Object.entries(f.types).filter(([, c]) => c.checked).map(([id]) => id);
    const weekdays = dayOrder.filter((d) => f.days[d].classList.contains('on')).map((d) => (d + 6) % 7);
    try {
      const payload = { room_type_ids: ids, date_from: f.from.value, date_to: f.to.value, weekdays };
      if (reset) payload.reset = true;
      else Object.assign(payload, { price: f.price.value, min_stay: f.min.value, closed: f.closed.value === '' ? null : f.closed.value === 'true' });
      const r = await api('PUT', '/api/rates', payload);
      err.style.display = 'none';
      toast(`Обновлено дат: ${r.updated}`);
      drawPreview();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  };
  const daySeg = h('div', { class: 'seg' }, dayOrder.map((d) => f.days[d] = h('button', { type: 'button', class: 'on', onclick: (e) => e.currentTarget.classList.toggle('on') }, WD[d])));
  content.append(preview, h('div', { class: 'card card-pad' },
    h('h2', { style: { marginBottom: '14px' } }, 'Изменить сразу на период'), err,
    h('div', { class: 'field' }, h('span', {}, 'Категории'), h('div', { style: { display: 'flex', gap: '16px', flexWrap: 'wrap' } },
      prop.room_types.map((t) => h('label', { class: 'check' }, f.types[t.id] = h('input', { type: 'checkbox', checked: true }), `${t.name} (${t.rooms.length})`)))),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'С'), f.from), h('label', { class: 'field' }, h('span', {}, 'По (включительно)'), f.to)),
    h('div', { class: 'field' }, h('span', {}, 'Дни недели'), h('div', {}, daySeg)),
    h('div', { class: 'row3' }, h('label', { class: 'field' }, h('span', {}, 'Цена за ночь, ₽'), f.price), h('label', { class: 'field' }, h('span', {}, 'Минимум ночей'), f.min), h('label', { class: 'field' }, h('span', {}, 'Продажи'), f.closed)),
    h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap' } },
      h('button', { class: 'btn primary', onclick: () => send(false) }, 'Применить'),
      h('button', { class: 'btn ghost', onclick: () => confirm('Вернуть базовые цены и снять ограничения на выбранный период?') && send(true) }, 'Сбросить к базовым')),
    h('p', { class: 'muted small', style: { marginBottom: 0 } }, 'Пример: выходные подороже — оставьте только Пт и Сб и укажите цену. Базовые цены категорий — в настройках.')));
  const drawPreview = () => priceCalendar(preview, prop);
  drawPreview();
}

// ---------- площадки ----------
const CHANNEL_HELP = {
  avito: [
    'На Авито откройте «Мои объявления», у нужного объявления нажмите «Управлять календарём» → «Синхронизация календарей».',
    'Скопируйте ссылку «Ваш календарь на Авито» и вставьте её сюда в поле «Ссылка с площадки».',
    'Нашу ссылку (кнопка «Копировать») вставьте на Авито в поле «Добавить календарь».',
  ],
  yandex: [
    'В Экстранете Яндекс Путешествий откройте категорию номеров → раздел «Синхронизация календарей». Для гостиницы календарь подключается к каждой категории.',
    'Ссылку календаря Яндекса вставьте сюда в строку этой категории, а нашу ссылку — в Экстранет.',
    'После подключения откройте доступность в Экстранете и проверьте, что Яндекс видит правильное число свободных номеров.',
  ],
  sutochno: [
    'На Суточно.ру: «Мои объекты» → шестерёнка у объекта → «Синхронизация календаря».',
    'Ссылку для экспорта с Суточно вставьте сюда, нашу ссылку — в поле импорта на Суточно.',
  ],
  ostrovok: [
    'В личном кабинете партнёра Островка найдите синхронизацию календаря по iCal.',
    'Обменяйтесь ссылками так же, как с другими площадками.',
  ],
  other: ['Подойдёт любая площадка, которая умеет импорт и экспорт календаря в формате iCal (.ics).'],
};

async function viewChannels(main) {
  let channel = store.get('channel', 'avito');
  const levelOverride = {};
  const content = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Площадки'),
    h('button', { class: 'btn', onclick: async (e) => {
      const btn = e.currentTarget; btn.disabled = true;
      try { const r = await api('POST', '/api/feeds/sync-all'); toast(r.feeds ? `Обновлено календарей: ${r.feeds}. Новых броней: ${r.added}${r.errors ? `, ошибок: ${r.errors}` : ''}` : 'Нет подключённых календарей', r.errors > 0); load(); }
      catch (ex) { toast(ex.message, true); } finally { btn.disabled = false; }
    } }, icon('sync'), 'Обновить всё')), content);

  const copy = async (text) => { try { await navigator.clipboard.writeText(text); toast('Ссылка скопирована'); } catch { prompt('Скопируйте ссылку:', text); } };

  function row(item, level, labels) {
    const ch = item.channels[channel];
    const feed = ch.feed;
    const input = h('input', { class: 'input', placeholder: 'https://… ссылка календаря с площадки', value: feed?.url || '' });
    const saveBtn = h('button', { class: 'btn small primary', onclick: async () => {
      saveBtn.disabled = true;
      try {
        const body = { channel, url: input.value, [level === 'type' ? 'room_type_id' : 'room_id']: item.id };
        const res = await api('POST', '/api/feeds', body);
        if (res.status === 'ok') toast(`Календарь подключён. Броней загружено: ${res.added}${res.conflicts ? `, конфликтов: ${res.conflicts}` : ''}`, res.conflicts > 0);
        else toast(`Ссылка сохранена, но календарь не загрузился: ${res.message}`, true);
        load();
      } catch (ex) { toast(ex.message, true); input.classList.add('invalid'); } finally { saveBtn.disabled = false; }
    } }, feed ? 'Заменить' : 'Подключить');
    let status;
    if (!feed) status = h('span', { class: 'pill none' }, 'не подключено');
    else if (feed.last_status === 'error') status = h('span', { class: 'pill bad', title: feed.last_error }, 'ошибка');
    else if (feed.last_error) status = h('span', { class: 'pill warn', title: feed.last_error }, 'есть конфликты');
    else status = h('span', { class: 'pill ok' }, 'работает');
    const modeSel = level === 'type' ? h('select', { class: 'input', style: { height: '32px', fontSize: '12.5px', marginTop: '6px' },
      title: 'Как площадка узнаёт о занятости категории',
      onchange: async (e) => { await api('PUT', '/api/channels/export-mode', { room_type_id: item.id, channel, mode: e.target.value }); toast('Сохранено'); } },
      h('option', { value: 'per_booking', selected: ch.export_mode === 'per_booking' }, 'Каждая бронь — отдельным событием'),
      h('option', { value: 'sold_out', selected: ch.export_mode === 'sold_out' }, 'Только даты, когда мест нет')) : null;
    return h('tr', {},
      h('td', { class: 'wide' }, level === 'type'
        ? [h('b', {}, item.name), h('div', { class: 'muted small' }, `${item.rooms_count} ${item.rooms_count === 1 ? 'номер' : 'номеров'}`)]
        : [h('b', { class: 'num' }, item.name), h('div', { class: 'muted small' }, item.room_type)]),
      h('td', { class: 'ch-cell wide', 'data-l': 'Наш календарь — вставьте на площадке' },
        h('div', { class: 'copy-line' }, h('input', { class: 'input', readonly: true, value: ch.export_url, onclick: (e) => e.target.select() }),
          h('button', { class: 'btn small icon', title: 'Копировать', onclick: () => copy(ch.export_url) }, icon('copy'))),
        h('div', { class: 'muted small', style: { marginTop: '4px' } }, 'площадка забирала: ', ago(ch.export_last_fetched_at)),
        modeSel),
      h('td', { class: 'ch-cell wide', 'data-l': 'Календарь площадки — вставьте сюда' }, h('div', { class: 'copy-line' }, input, saveBtn),
        feed?.last_status === 'error' ? h('div', { class: 'small', style: { color: 'var(--clay)', marginTop: '4px' } }, feed.last_error) : null),
      h('td', { class: 'wide', 'data-l': 'Состояние' }, h('div', { class: 'state' }, status),
        feed ? h('div', { class: 'muted small' }, 'обновлено: ', ago(feed.last_synced_at)) : null,
        feed ? h('div', { class: 'ch-actions', style: { marginTop: '6px' } },
          h('button', { class: 'btn small', onclick: async (e) => {
            e.currentTarget.disabled = true;
            try { const res = await api('POST', `/api/feeds/${feed.id}/sync`); toast(res.status === 'ok' ? `Готово: новых ${res.added}, изменено ${res.updated}, отменено ${res.removed}` : res.message, res.status !== 'ok'); load(); }
            catch (ex) { toast(ex.message, true); }
          } }, icon('sync'), 'Обновить'),
          h('button', { class: 'btn small ghost danger', onclick: async () => {
            if (!confirm(`Отключить календарь площадки «${labels[channel]}»? Брони, уже загруженные с неё, останутся в шахматке.`)) return;
            await api('DELETE', `/api/feeds/${feed.id}`); toast('Календарь отключён'); load();
          } }, 'Отключить')) : null));
  }

  async function load() {
    const [data, conflicts] = await Promise.all([
      api('GET', '/api/channels?' + qs({ property_id: state.propertyId })), api('GET', '/api/conflicts')]);
    state.conflicts = conflicts.length;
    const level = levelOverride[channel] || data.levels[channel];
    content.innerHTML = '';
    if (conflicts.length) {
      content.append(h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', {}, 'Конфликты: двойное бронирование'), h('span', { class: 'pill bad' }, conflicts.length)),
        h('div', { class: 'card-pad', style: { paddingTop: '10px' } },
          h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Площадка продала даты, на которые у вас нет свободного номера. Свяжитесь с гостем площадки или переселите одну из броней, затем отметьте конфликт решённым.'),
          h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, conflicts.map((c) => h('tr', {},
            h('td', {}, h('b', {}, c.target_name)), h('td', { class: 'num' }, `${fmtShort(c.check_in)} — ${fmtShort(c.check_out)}`),
            h('td', {}, data.labels[c.channel] || '—'), h('td', { class: 'muted small' }, c.summary),
            h('td', { style: { textAlign: 'right' } }, h('button', { class: 'btn small', onclick: async () => { await api('POST', `/api/conflicts/${c.id}/resolve`); load(); } }, 'Решено'))))))))));
    }
    const tabs = h('div', { class: 'seg', style: { flexWrap: 'wrap' } }, Object.entries(data.labels).map(([k, l]) => {
      const connected = data.rooms.filter((r) => r.channels[k].feed).length + data.room_types.filter((t) => t.channels[k].feed).length;
      return h('button', { class: k === channel ? 'on' : '', onclick: () => { channel = k; store.set('channel', k); load(); } }, l, connected ? ` · ${connected}` : '');
    }));
    const anyFeeds = data.rooms.some((r) => r.channels[channel].feed) || data.room_types.some((t) => t.channels[channel].feed);
    const levelSeg = h('div', { class: 'seg' },
      [['room', 'По номерам'], ['type', 'По категориям']].map(([k, l]) => h('button', {
        class: level === k ? 'on' : '', disabled: anyFeeds && level !== k,
        title: anyFeeds && level !== k ? 'Сначала отключите текущие календари этой площадки' : '',
        onclick: () => { levelOverride[channel] = k; load(); },
      }, l)));
    const items = level === 'type' ? data.room_types : data.rooms;
    content.append(
      h('div', { class: 'board-tools' }, tabs),
      h('div', { class: 'card card-pad' },
        h('div', { style: { display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '10px' } },
          h('h3', { style: { marginRight: 'auto' } }, `Как подключить: ${data.labels[channel]}`), levelSeg),
        h('ol', { class: 'steps small' }, CHANNEL_HELP[channel].map((st) => h('li', {}, st))),
        h('p', { class: 'muted small', style: { marginBottom: 0 } },
          level === 'type'
            ? 'Календарь категории: брони площадки мы сами расставляем по свободным номерам этой категории. Если площадка закрывает всю категорию при первой же брони, переключите способ передачи на «Только даты, когда мест нет».'
            : 'Календарь номера: одно объявление на площадке = один номер у нас.',
          ` Календари площадок обновляются каждые ${data.sync_interval_minutes} минут. Сама площадка забирает наш календарь по своему расписанию. Через iCal передаётся только занятость; цены меняются в кабинете площадки.`)),
      h('div', { class: 'card' }, h('div', { class: 'table-wrap' }, h('table', { class: 'list ch-table cards-mobile' },
        h('thead', {}, h('tr', {}, [level === 'type' ? 'Категория' : 'Номер', 'Ссылка для площадки (наш календарь)', 'Ссылка с площадки (их календарь)', 'Состояние'].map((t) => h('th', {}, t)))),
        h('tbody', {}, items.map((it) => row(it, level, data.labels)))))));
  }
  load().catch((ex) => content.append(h('div', { class: 'card empty' }, ex.message)));
}

// ---------- отчёты: графики (свой SVG, без библиотек) ----------
const escHtml = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safeColor = (c) => (/^#[0-9a-fA-F]{6}$/.test(c || '') ? c : '#69755F');

function svgEl(markup) {
  const wrap = document.createElement('div');
  wrap.innerHTML = markup.trim();
  return wrap.firstChild;
}

const CHART_COLORS = ['#2F5D50', '#B7791F', '#6E4A93', '#23767E', '#B4562E', '#4A5A6A', '#5E6B5A', '#7A3418', '#8A5A12', '#69755F'];

function monthlyChart(monthly) {
  const W = 720, H = 230, padB = 24, plotH = H - padB - 8;
  const vals = monthly.flatMap((m) => [Number(m.revenue) + Number(m.other_income || 0), Number(m.expenses), Math.abs(Number(m.profit))]);
  const max = Math.max(1, ...vals);
  const n = monthly.length;
  const colW = W / n;
  const barW = Math.min(16, colW * 0.32);
  const y0 = plotH + 8;
  let bars = '';
  let points = '';
  monthly.forEach((m, i) => {
    const cx = colW * (i + 0.5);
    const rev = Number(m.revenue), oth = Number(m.other_income || 0), exp = Number(m.expenses), profit = Number(m.profit);
    const revH = (rev / max) * plotH, othH = (oth / max) * plotH, expH = (exp / max) * plotH;
    const dt = parseISO(m.month);
    const tip = `${MONTHS_SHORT[dt.getMonth()]} ${dt.getFullYear()}: проживание ${fmtMoney(rev)}, прочие доходы ${fmtMoney(oth)}, расходы ${fmtMoney(exp)}, прибыль ${fmtMoney(profit)}`;
    bars += `<g><title>${tip}</title>`;
    bars += `<rect x="${cx - barW - 2}" y="${y0 - revH}" width="${barW}" height="${revH}" fill="${CHART_COLORS[0]}" rx="2"/>`;
    if (othH > 0.5) bars += `<rect x="${cx - barW - 2}" y="${y0 - revH - othH}" width="${barW}" height="${othH}" fill="${CHART_COLORS[3]}" rx="2"/>`;
    bars += `<rect x="${cx + 2}" y="${y0 - expH}" width="${barW}" height="${expH}" fill="${CHART_COLORS[4]}" rx="2"/>`;
    bars += `<rect x="${cx - colW / 2}" y="0" width="${colW}" height="${H}" fill="transparent"/></g>`;
    const py = Math.max(-4, Math.min(y0, y0 - (profit / max) * plotH));
    points += `${cx},${py} `;
    bars += `<text x="${cx}" y="${H - 6}" font-size="10.5" fill="var(--muted)" text-anchor="middle">${MONTHS_SHORT[dt.getMonth()]}</text>`;
  });
  return svgEl(`<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;display:block;overflow:visible" role="img" aria-label="Доходы, расходы и прибыль по месяцам">
    <line x1="0" y1="${y0}" x2="${W}" y2="${y0}" stroke="var(--border)"/>
    ${bars}
    <polyline points="${points.trim()}" fill="none" stroke="${CHART_COLORS[1]}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`);
}

// Расходы по категориям помесячно — столбцы с накоплением. Показаны крупнейшие категории,
// остальные слиты в «Остальные» (это делает сервер).
function stackedExpenseChart(em) {
  const W = 720, H = 220, padB = 24, plotH = H - padB - 8, y0 = plotH + 8;
  const totals = em.rows.map((r) => Object.values(r.amounts).reduce((s, v) => s + Number(v), 0));
  const max = Math.max(1, ...totals);
  const colW = W / em.rows.length, barW = Math.min(30, colW * 0.6);
  let bars = '';
  em.rows.forEach((row, i) => {
    const cx = colW * (i + 0.5);
    let y = y0;
    const tipLines = [];
    em.categories.forEach((c) => {
      const v = Number(row.amounts[c.category_id] || 0);
      if (v <= 0) return;
      const hgt = (v / max) * plotH;
      y -= hgt;
      bars += `<rect x="${cx - barW / 2}" y="${y}" width="${barW}" height="${Math.max(hgt, 0.5)}" fill="${safeColor(c.color)}"/>`;
      tipLines.push(`${escHtml(c.name)}: ${fmtMoney(v)}`);
    });
    const dt = parseISO(row.month);
    bars += `<rect x="${cx - colW / 2}" y="0" width="${colW}" height="${H}" fill="transparent"><title>${MONTHS_SHORT[dt.getMonth()]} ${dt.getFullYear()} — всего ${fmtMoney(totals[i])}\n${tipLines.join('\n')}</title></rect>`;
    bars += `<text x="${cx}" y="${H - 6}" font-size="10.5" fill="var(--muted)" text-anchor="middle">${MONTHS_SHORT[dt.getMonth()]}</text>`;
  });
  return svgEl(`<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;display:block" role="img" aria-label="Расходы по категориям по месяцам">
    <line x1="0" y1="${y0}" x2="${W}" y2="${y0}" stroke="var(--border)"/>${bars}</svg>`);
}

function weekdayChart(weekday) {
  const W = 420, H = 160, padB = 22;
  const plotH = H - padB;
  const order = [1, 2, 3, 4, 5, 6, 0]; // показываем неделю с понедельника
  const colW = W / order.length;
  const barW = Math.min(34, colW * 0.55);
  let bars = '';
  order.forEach((wd, i) => {
    const x = weekday.find((w) => w.weekday === wd) || { occupancy: 0 };
    const cx = colW * (i + 0.5);
    const bh = (Math.min(100, x.occupancy) / 100) * plotH;
    bars += `<rect x="${cx - barW / 2}" y="${plotH - bh}" width="${barW}" height="${Math.max(bh, 1)}" fill="var(--pine)" rx="3"/>`;
    bars += `<text x="${cx}" y="${plotH - bh - 6}" font-size="11" fill="var(--ink)" text-anchor="middle" font-weight="600">${Math.round(x.occupancy)}%</text>`;
    bars += `<text x="${cx}" y="${H - 6}" font-size="11" fill="var(--muted)" text-anchor="middle">${WD[wd]}</text>`;
  });
  return svgEl(`<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;display:block">
    <line x1="0" y1="${plotH}" x2="${W}" y2="${plotH}" stroke="var(--border)"/>
    ${bars}
  </svg>`);
}

function expenseDonut(byCategory) {
  const size = 160, r = 62, cx = size / 2, cy = size / 2, circ = 2 * Math.PI * r;
  const total = byCategory.reduce((s, x) => s + Number(x.amount), 0) || 1;
  let offset = 0;
  let circles = '';
  byCategory.forEach((x, i) => {
    const frac = Number(x.amount) / total;
    const len = frac * circ;
    circles += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${safeColor(x.color)}" stroke-width="22"` +
      ` stroke-dasharray="${len} ${circ - len}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})"/>`;
    offset += len;
  });
  return svgEl(`<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">${circles}</svg>`);
}

function deltaBadge(delta) {
  if (delta === null || delta === undefined) return h('span', { class: 'muted small' }, '—');
  const good = delta >= 0;
  return h('span', { class: 'small', style: { color: good ? 'var(--pine)' : 'var(--clay)', fontWeight: 600 } },
    `${good ? '▲' : '▼'} ${Math.abs(delta).toFixed(1).replace('.', ',')}%`);
}

function kpiCard(label, value, unit, compare, text = false) {
  const v = h('div', { class: 'v' + (text ? ' txt' : '') }, value, unit ? h('small', {}, ` ${unit}`) : null);
  const cmp = compare ? h('div', { class: 'small muted', style: { marginTop: '6px', display: 'flex', gap: '10px' } },
    h('span', {}, 'к периоду: ', deltaBadge(compare.period)), h('span', {}, 'к году: ', deltaBadge(compare.year))) : null;
  return h('div', { class: 'kpi' }, h('div', { class: 'l' }, label), v, cmp);
}

// ---------- отчёты ----------
async function viewStats(main) {
  const t = todayISO(); const d = parseISO(t);
  const monthStart = iso(new Date(d.getFullYear(), d.getMonth(), 1));
  const nextMonth = iso(new Date(d.getFullYear(), d.getMonth() + 1, 1));
  const prevMonth = iso(new Date(d.getFullYear(), d.getMonth() - 1, 1));
  const quarterStart = iso(new Date(d.getFullYear(), Math.floor(d.getMonth() / 3) * 3, 1));
  const yearStart = iso(new Date(d.getFullYear(), 0, 1));
  const nextYear = iso(new Date(d.getFullYear() + 1, 0, 1));
  const periods = [
    ['Этот месяц', monthStart, nextMonth], ['Прошлый месяц', prevMonth, monthStart],
    ['Этот квартал', quarterStart, nextMonth > quarterStart ? nextMonth : addDays(quarterStart, 90)],
    ['Этот год', yearStart, nextYear], ['Свой период', null, null],
  ];
  let current = Math.min(parseInt(store.get('stats_period', '0'), 10) || 0, periods.length - 2); // свой период не запоминаем
  const custom = { from: addDays(t, -30), to: t };
  const scope = { value: 'current' };
  const content = h('div', { class: 'stack' });
  const customBox = h('div', { class: 'board-tools', style: { display: 'none' } });
  const seg = h('div', { class: 'seg', style: { flexWrap: 'wrap' } });
  const drawSeg = () => {
    seg.innerHTML = '';
    periods.forEach(([l], i) => seg.append(h('button', { class: i === current ? 'on' : '', onclick: () => { current = i; if (i < periods.length - 1) store.set('stats_period', String(i)); drawSeg(); customBox.style.display = i === periods.length - 1 ? 'flex' : 'none'; if (i !== periods.length - 1) load(); } }, l)));
  };
  drawSeg();
  const fromInp = h('input', { class: 'input', type: 'date', value: custom.from, style: { width: '150px' }, onchange: (e) => { custom.from = e.target.value; load(); } });
  const toInp = h('input', { class: 'input', type: 'date', value: custom.to, style: { width: '150px' }, onchange: (e) => { custom.to = e.target.value; load(); } });
  customBox.append(fromInp, '—', toInp);
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Отчёты'), seg, scopeSeg(scope, () => load())), customBox, content);

  async function load() {
    const isCustom = current === periods.length - 1;
    const from = isCustom ? custom.from : periods[current][1];
    const to = isCustom ? custom.to : periods[current][2];
    const propertyId = scope.value === 'current' ? state.propertyId : undefined;
    let r;
    try {
      r = await api('GET', '/api/reports?' + qs({ from, to, property_id: propertyId }));
    } catch (ex) { content.innerHTML = ''; content.append(h('div', { class: 'card empty' }, ex.message)); return; }
    const tt = r.totals;
    const cmp = { period: r.compare_prev_period, year: r.compare_prev_year };
    const money = (v) => fmtMoney(v).replace('.', ',');

    content.innerHTML = '';
    content.append(h('div', { class: 'kpis' },
      kpiCard('Выручка от проживания', money(tt.revenue), null, { period: cmp.period.revenue_delta, year: cmp.year.revenue_delta }),
      kpiCard('Прочие доходы', money(tt.other_income), null, { period: cmp.period.other_income_delta, year: cmp.year.other_income_delta }),
      kpiCard('Расходы', money(tt.expenses), null, { period: cmp.period.expenses_delta, year: cmp.year.expenses_delta }),
      kpiCard('Прибыль', money(tt.profit), null, { period: cmp.period.profit_delta, year: cmp.year.profit_delta }),
      kpiCard('Рентабельность', tt.margin == null ? '—' : String(tt.margin).replace('.', ','), tt.margin == null ? null : '%'),
      kpiCard('Загрузка', String(tt.occupancy).replace('.', ','), '%', { period: cmp.period.occupancy_delta, year: cmp.year.occupancy_delta }),
      kpiCard('Цена ночи (ADR)', money(tt.adr)),
      kpiCard('Доход на номер (RevPAR)', money(tt.revpar)),
      kpiCard('Средний срок проживания', String(tt.avg_stay).replace('.', ','), 'ноч.'),
      kpiCard('Доля отмен', String(tt.cancellation_rate).replace('.', ','), '%'),
      kpiCard('Гости должны доплатить', money(tt.due_amount))));

    const chartsRow = h('div', { class: 'grid-2' });
    chartsRow.append(
      h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, 'Доходы, расходы и прибыль по месяцам'),
        monthlyChart(r.monthly),
        h('div', { class: 'legend', style: { padding: '10px 0 0', border: 0 } },
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[0] } }), 'Проживание'),
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[3] } }), 'Прочие доходы'),
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[4] } }), 'Расходы'),
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[1] } }), 'Прибыль (линия)'))),
      h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, 'Загрузка по дням недели'),
        weekdayChart(r.weekday_occupancy)));
    content.append(chartsRow);

    const structureCard = (title, items, emptyText) => {
      const card = h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, title));
      if (items.length) {
        const total = items.reduce((s, x) => s + Number(x.amount), 0) || 1;
        card.append(h('div', { class: 'donut-box' }, expenseDonut(items),
          h('div', { style: { flex: 1, minWidth: '200px' } }, items.map((x) => h('div', {
            style: { display: 'flex', justifyContent: 'space-between', gap: '10px', padding: '4px 0' },
          }, h('span', {}, h('i', { class: 'dot', style: { background: safeColor(x.color) } }), ' ', x.name,
            h('span', { class: 'muted small' }, ` ${Math.round((Number(x.amount) / total) * 100)}%`)), h('b', { class: 'num' }, money(x.amount)))))));
      } else card.append(h('div', { class: 'empty' }, emptyText));
      return card;
    };
    content.append(h('div', { class: 'grid-2' },
      structureCard('Структура расходов', r.by_expense_category, 'Расходов за период нет'),
      structureCard('Структура прочих доходов', r.by_income_category, 'Прочих доходов за период нет')));

    if (r.expense_monthly && r.expense_monthly.categories.length) {
      content.append(h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, 'Расходы по категориям по месяцам'),
        stackedExpenseChart(r.expense_monthly),
        h('div', { class: 'legend', style: { padding: '10px 0 0', border: 0 } },
          r.expense_monthly.categories.map((c) => h('span', {}, h('i', { class: 'dot', style: { background: safeColor(c.color) } }), c.name)))));
    }

    if (r.by_property && r.by_property.length) {
      content.append(h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', {}, 'По объектам')),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' },
          h('thead', {}, h('tr', {}, ['Объект', 'Номеров', 'Выручка', 'Прочие доходы', 'Расходы', 'Прибыль', 'Загрузка'].map((x) => h('th', {}, x)))),
          h('tbody', {}, r.by_property.map((p) => h('tr', {},
            h('td', {}, p.property_name), h('td', { class: 'num' }, p.rooms),
            h('td', { class: 'num' }, money(p.revenue)), h('td', { class: 'num' }, money(p.other_income)), h('td', { class: 'num' }, money(p.expenses)),
            h('td', { class: 'num' }, money(p.profit)), h('td', { class: 'num' }, `${String(p.occupancy).replace('.', ',')}%`))))))));
    }

    if (r.by_room_type.length) {
      content.append(h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', {}, 'По категориям номеров')),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' },
          h('thead', {}, h('tr', {}, ['Категория', 'Номеров', 'Ночей', 'Выручка'].map((x) => h('th', {}, x)))),
          h('tbody', {}, r.by_room_type.map((x) => h('tr', {},
            h('td', {}, x.room_type_name), h('td', { class: 'num' }, x.rooms),
            h('td', { class: 'num' }, x.nights), h('td', { class: 'num' }, money(x.revenue)))))))));
    }

    let roomSort = { key: 'profit', dir: -1 };
    const roomCard = h('div', { class: 'card' });
    const drawRoomTable = () => {
      const rows = [...r.by_room].sort((a, b) => {
        const av = isNaN(a[roomSort.key]) ? a[roomSort.key] : Number(a[roomSort.key]);
        const bv = isNaN(b[roomSort.key]) ? b[roomSort.key] : Number(b[roomSort.key]);
        return (av > bv ? 1 : av < bv ? -1 : 0) * roomSort.dir;
      });
      const th = (key, label) => h('th', { style: { cursor: 'pointer' }, onclick: () => { roomSort.dir = roomSort.key === key ? -roomSort.dir : -1; roomSort.key = key; drawRoomTable(); } },
        label, roomSort.key === key ? (roomSort.dir === -1 ? ' ↓' : ' ↑') : '');
      roomCard.innerHTML = '';
      const multi = state.me.properties.length > 1;
      const roomTableBody = rows.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' },
          h('thead', {}, h('tr', {}, th('room_name', 'Номер'), th('room_type_name', 'Категория'),
            multi ? th('property_name', 'Объект') : null, th('nights', 'Ночей'),
            th('occupancy', 'Загрузка'), th('revenue', 'Выручка'), th('other_income', 'Др. доходы'),
            th('expenses', 'Расходы'), th('profit', 'Прибыль'))),
          h('tbody', {}, rows.map((x) => h('tr', {},
            h('td', { 'data-l': 'Номер' }, h('b', {}, x.room_name)), h('td', { class: 'muted small', 'data-l': 'Категория' }, x.room_type_name),
            multi ? h('td', { class: 'muted small', 'data-l': 'Объект' }, x.property_name) : null,
            h('td', { class: 'num', 'data-l': 'Ночей' }, x.nights), h('td', { class: 'num', 'data-l': 'Загрузка' }, `${String(x.occupancy).replace('.', ',')}%`),
            h('td', { class: 'num', 'data-l': 'Выручка' }, money(x.revenue)),
            h('td', { class: 'num', 'data-l': 'Др. доходы' }, Number(x.other_income) ? money(x.other_income) : '—'),
            h('td', { class: 'num', 'data-l': 'Расходы' }, Number(x.expenses) ? money(x.expenses) : '—'),
            h('td', { class: 'num strong', 'data-l': 'Прибыль', style: { color: Number(x.profit) < 0 ? 'var(--clay)' : '' } }, money(x.profit))))))) : h('div', { class: 'empty' }, 'В этом объекте пока нет номеров');
      roomCard.append(h('div', { class: 'card-head' }, h('h2', {}, 'По номерам'), h('span', { class: 'muted small' }, 'нажмите на заголовок для сортировки')),
        roomTableBody,
        h('p', { class: 'muted small card-pad', style: { paddingTop: '8px' } }, 'Расходы и доходы здесь — только те, что записаны на сам номер (раздел «Финансы» → «Относится к»). Расходы объекта и общие между номерами не делятся.'));
    };
    drawRoomTable();
    content.append(roomCard);

    const maxSrc = Math.max(1, ...r.by_source.map((x) => Number(x.revenue)));
    const sourceRow = (x) => {
      const dot = h('i', { class: 'dot', style: { background: `var(--src-${x.source})` } });
      const label = h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, dot, x.label);
      const commission = Number(x.commission_percent) ? `${money(x.commission_amount)} (${x.commission_percent}%)` : '—';
      const barFill = h('i', { style: { width: `${(Number(x.revenue) / maxSrc) * 100}%`, background: `var(--src-${x.source})` } });
      const bar = h('div', { class: 'bar-h' }, barFill);
      return h('tr', {}, h('td', { class: 'wide' }, label), h('td', { class: 'num', 'data-l': 'Броней' }, x.bookings), h('td', { class: 'num', 'data-l': 'Ночей' }, x.nights),
        h('td', { class: 'num', 'data-l': 'Выручка' }, money(x.revenue)), h('td', { class: 'num muted small', 'data-l': 'Комиссия' }, commission),
        h('td', { class: 'num', 'data-l': 'Чистая выручка' }, money(x.net_revenue)), h('td', { class: 'wide', style: { width: '25%' } }, bar));
    };
    const sourceHead = h('thead', {}, h('tr', {}, ['Источник', 'Броней', 'Ночей', 'Выручка', 'Комиссия', 'Чистая выручка', ''].map((x) => h('th', {}, x))));
    const sourceBody = r.by_source.length
      ? h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' }, sourceHead, h('tbody', {}, r.by_source.map(sourceRow))))
      : h('div', { class: 'empty' }, 'За этот период броней нет');
    content.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'По источникам броней')), sourceBody));

    content.append(h('p', { class: 'muted small' },
      'Выручка считается по ночам внутри периода: бронь, которая начинается в одном месяце и заканчивается в другом, делится пропорционально. ',
      r.share_note,
      ' Комиссии площадок настраиваются в разделе «Настройки».'));

    content.append(h('div', { style: { display: 'flex', justifyContent: 'flex-end' } },
      h('button', { class: 'btn', onclick: () => downloadCsv('/api/reports/export.csv?' + qs({ from, to, property_id: propertyId }), `report_${from}_${to}.csv`) },
        icon('download'), 'Выгрузить отчёт в CSV')));
  }
  load();
}

// ---------- расходы ----------
async function downloadCsv(path, filename) {
  try {
    const res = await fetch(path, { headers: { Authorization: `Bearer ${store.get('token')}` } });
    if (!res.ok) throw new Error('Не удалось скачать файл');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = h('a', { href: url, download: filename });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  } catch (ex) { toast(ex.message, true); }
}

// Импорт броней из CSV: сначала проверка (ничего не сохраняется), потом настоящий импорт
function importDialog(onDone) {
  let text = '';
  const info = h('div', { class: 'muted small' }, 'Файл не выбран');
  const report = h('div', {});
  const go = h('button', { class: 'btn primary', disabled: true }, 'Проверить файл');
  let checked = false;
  const file = h('input', { type: 'file', accept: '.csv,.txt,text/csv', style: { display: 'none' }, onchange: async () => {
    const f = file.files[0]; if (!f) return;
    if (f.size > 1_500_000) { toast('Файл слишком большой (максимум 1,5 МБ)', true); return; }
    text = await f.text(); checked = false; report.innerHTML = '';
    info.textContent = `Выбран файл: ${f.name}`; go.textContent = 'Проверить файл'; go.disabled = false;
  } });
  const show = (r) => {
    report.innerHTML = '';
    report.append(h('div', { class: 'note ' + (r.created ? 'ok' : 'bad'), style: { margin: '12px 0 8px' } },
      r.dry_run ? `Можно загрузить броней: ${r.created} из ${r.total}.` : `Загружено броней: ${r.created} из ${r.total}.`,
      r.skipped ? ` Пропущено: ${r.skipped}.` : ''));
    if (r.errors.length) report.append(h('div', { class: 'table-wrap', style: { maxHeight: '220px', overflow: 'auto' } },
      h('table', { class: 'list' }, h('tbody', {}, r.errors.map((e) => h('tr', {}, h('td', { class: 'num' }, `строка ${e.line}`), h('td', {}, e.error)))))));
  };
  go.addEventListener('click', async () => {
    go.disabled = true;
    try {
      const r = await api('POST', '/api/bookings/import', { csv: text, dry_run: !checked, property_id: state.propertyId });
      show(r);
      if (r.dry_run) {
        checked = true; go.textContent = r.created ? `Загрузить ${r.created} бронь(ей)` : 'Проверить заново'; go.disabled = !r.created;
        if (!r.created) { checked = false; go.disabled = false; }
      } else { go.textContent = 'Готово'; toast(`Загружено броней: ${r.created}`); onDone?.(); refreshBadges?.(); }
    } catch (ex) { toast(ex.message, true); go.disabled = false; checked = false; }
  });
  openModal('Импорт броней из CSV', h('div', {},
    h('p', { class: 'muted small', style: { marginTop: 0 } },
      'Переезжаете из Excel или другой системы? Сохраните таблицу как CSV: нужны колонки «Заезд», «Выезд» и «Номер» (название номера из «Настроек»); необязательно — «Гость», «Телефон», «Email», «Гостей», «Источник», «Стоимость», «Оплачено», «Комментарий». Если стоимость не указана, она посчитается по тарифам. Брони загрузятся в выбранный объект как подтверждённые; пересекающиеся с уже существующими будут пропущены.'),
    h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' } },
      h('button', { class: 'btn', type: 'button', onclick: () => file.click() }, icon('upload'), 'Выбрать файл'),
      h('button', { class: 'btn ghost', type: 'button', onclick: () => downloadCsv('/api/bookings/import-template.csv', 'bookings_template.csv') }, icon('download'), 'Скачать образец'),
      info, file),
    report),
  [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Закрыть'), h('span', { class: 'spacer' }), go]);
}

function categoryDrawer(cat, cfg = FLOW.expense) {
  const g = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const COLORS = ['#23767E', '#4A5A6A', '#6E4A93', '#B4562E', '#B7791F', '#2F5D50', '#5E6B5A', '#7A3418', '#8A5A12', '#69755F', '#C1852B', '#3B7A9E'];
  let color = cat.color || COLORS[0];
  if (!cat.id && cfg.kind === 'income') color = '#2F5D50';
  const swatches = h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' } });
  const drawSwatches = () => {
    swatches.innerHTML = '';
    COLORS.forEach((c) => swatches.append(h('button', {
      type: 'button', onclick: () => { color = c; drawSwatches(); },
      style: { width: '26px', height: '26px', borderRadius: '7px', background: c, border: color === c ? '2px solid var(--ink)' : '2px solid transparent', cursor: 'pointer' },
    })));
  };
  drawSwatches();
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; err.style.display = 'none';
    try {
      const payload = { name: g.name.value, color };
      if (cat.id) await api('PATCH', `${cfg.catApi}/${cat.id}`, payload);
      else await api('POST', cfg.catApi, payload);
      closeDrawer(); toast('Сохранено'); cat.onSaved?.();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, 'Сохранить');
  const foot = [h('span', { class: 'spacer' }), save];
  if (cat.id) {
    foot.unshift(h('button', { class: 'btn ghost danger', onclick: async () => {
      if (!confirm(`Архивировать категорию «${cat.name}»? Старые расходы останутся, но выбрать её для новых будет нельзя.`)) return;
      try { await api('PATCH', `${cfg.catApi}/${cat.id}`, { archived: true }); closeDrawer(); toast('Категория архивирована'); cat.onSaved?.(); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Архивировать'));
  }
  openDrawer(cat.id ? (cfg.kind === 'income' ? 'Категория доходов' : 'Категория расходов') : 'Новая категория', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Название'), g.name = h('input', { class: 'input', value: cat.name || '', required: true })),
    h('div', { class: 'field' }, h('span', {}, 'Цвет'), swatches)), foot);
}

function recurringDrawer(cats, rule, propertyOptions, onSaved) {
  const g = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  g.category_id = h('select', { class: 'input' }, cats.map((c) => h('option', { value: c.id, selected: c.id === rule.category_id }, c.name)));
  g.amount = h('input', { class: 'input', money: true, type: 'number', min: 0, value: rule.amount ? Math.round(rule.amount) : '' });
  g.day_of_month = h('input', { class: 'input', type: 'number', min: 1, max: 28, value: rule.day_of_month || 1 });
  g.property_id = h('select', { class: 'input' }, h('option', { value: '' }, 'Общий — по всем объектам'),
    propertyOptions.map((p) => h('option', { value: p.id, selected: p.id === rule.property_id }, p.name)));
  g.comment = h('input', { class: 'input', value: rule.comment || '', placeholder: 'Например: аренда помещения' });
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; err.style.display = 'none';
    try {
      const payload = {
        category_id: g.category_id.value, amount: g.amount.value, day_of_month: g.day_of_month.value,
        property_id: g.property_id.value || null, comment: g.comment.value,
      };
      if (rule.id) await api('PATCH', `/api/expense-recurring/${rule.id}`, payload);
      else await api('POST', '/api/expense-recurring', payload);
      closeDrawer(); toast('Сохранено'); onSaved();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, 'Сохранить');
  const foot = [h('span', { class: 'spacer' }), save];
  if (rule.id) {
    foot.unshift(h('button', { class: 'btn ghost danger', onclick: async () => {
      if (!confirm('Удалить повторяющийся расход? Уже созданные записи расходов останутся.')) return;
      try { await api('DELETE', `/api/expense-recurring/${rule.id}`); closeDrawer(); toast('Удалено'); onSaved(); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Удалить'));
  }
  openDrawer(rule.id ? 'Повторяющийся расход' : 'Новый повторяющийся расход', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Категория'), g.category_id),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Сумма, ₽'), g.amount),
      h('label', { class: 'field' }, h('span', {}, 'Число месяца (1—28)'), g.day_of_month)),
    h('label', { class: 'field' }, h('span', {}, 'Объект'), g.property_id),
    h('label', { class: 'field' }, h('span', {}, 'Комментарий'), g.comment),
    h('p', { class: 'muted small' }, 'В нужный день месяца расход создастся сам — в том же фоновом режиме, что и синхронизация площадок.')),
  foot);
}

// ---------- финансы: расходы и прочие доходы ----------
// Расходы и прочие доходы (завтраки, парковка, трансфер…) устроены одинаково: свои категории,
// привязка к объекту или к конкретному номеру либо «общая» запись на весь аккаунт.
const FLOW = {
  expense: {
    kind: 'expense', api: '/api/expenses', catApi: '/api/expense-categories', csv: 'expenses', catColor: '#69755F',
    tab: 'Расходы', one: 'Расход', newTitle: 'Новый расход', addBtn: 'Расход', listTitle: 'Расходы за период',
    emptyList: 'Расходов не найдено', added: 'Расход добавлен', delConfirm: 'Удалить расход?',
    noCats: 'Нет ни одной активной категории расходов — добавьте хотя бы одну ниже', catTitle: 'Категории расходов',
    byRoomTitle: 'Расходы по номерам',
  },
  income: {
    kind: 'income', api: '/api/incomes', catApi: '/api/income-categories', csv: 'incomes', catColor: '#2F5D50',
    tab: 'Прочие доходы', one: 'Доход', newTitle: 'Новый доход', addBtn: 'Доход', listTitle: 'Доходы за период',
    emptyList: 'Доходов не найдено', added: 'Доход добавлен', delConfirm: 'Удалить запись о доходе?',
    noCats: 'Нет ни одной активной категории доходов — добавьте хотя бы одну ниже', catTitle: 'Категории доходов',
    byRoomTitle: 'Доходы по номерам',
  },
};

// Объекты и их номера для выбора «к чему относится запись». Сбрасывается при каждой перерисовке.
let scopeCache = null;
async function loadScopes() {
  if (!scopeCache) {
    scopeCache = await Promise.all(state.me.properties.map(async (p) => {
      const full = await api('GET', `/api/properties/${p.id}`);
      return { id: p.id, name: p.name, rooms: full.room_types.flatMap((t) => t.rooms.map((r) => ({ id: r.id, name: r.name, type: t.name }))) };
    }));
  }
  return scopeCache;
}
function scopeSelect(scopes, current, { general = true, extra = [], attrs = {} } = {}) {
  const sel = h('select', { class: 'input', ...attrs });
  extra.forEach(([v, l]) => sel.append(h('option', { value: v }, l)));
  if (general) sel.append(h('option', { value: '' }, 'Общий — по всем объектам'));
  scopes.forEach((p) => {
    const grp = h('optgroup', { label: p.name }, h('option', { value: `p:${p.id}` }, `${p.name} — весь объект`));
    p.rooms.forEach((r) => grp.append(h('option', { value: `r:${r.id}` }, `№${r.name} · ${r.type} (${p.name})`)));
    sel.append(grp);
  });
  sel.value = current;
  return sel;
}
const scopePayload = (v) => (v.startsWith('r:') ? { room_id: v.slice(2), property_id: null }
  : v.startsWith('p:') ? { property_id: v.slice(2), room_id: null } : { property_id: null, room_id: null });
const scopeOf = (row) => (row.room_id ? `r:${row.room_id}` : row.property_id ? `p:${row.property_id}` : '');
const scopeLabel = (row) => (row.property_name ? `${row.property_name}${row.room_name ? ` · №${row.room_name}` : ''}` : 'Общий');

function flowDrawer(cfg, cats, scopes, rec, onSaved) {
  const readOnly = !can('manager');
  const g = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  g.date = h('input', { class: 'input', type: 'date', value: rec.date || todayISO(), disabled: readOnly });
  g.amount = h('input', { class: 'input', money: true, type: 'number', inputmode: 'decimal', min: 0, step: '0.01', value: rec.amount != null ? Number(rec.amount) : '', disabled: readOnly });
  g.category_id = h('select', { class: 'input', disabled: readOnly }, cats.map((c) => h('option', { value: c.id, selected: c.id === rec.category_id }, c.name)));
  g.scope = scopeSelect(scopes, scopeOf(rec), { attrs: { disabled: readOnly } });
  g.comment = h('textarea', { class: 'input', disabled: readOnly }, rec.comment || '');
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; err.style.display = 'none';
    try {
      const payload = { date: g.date.value, amount: g.amount.value, category_id: g.category_id.value, comment: g.comment.value, ...scopePayload(g.scope.value) };
      if (rec.id) await api('PATCH', `${cfg.api}/${rec.id}`, payload);
      else await api('POST', cfg.api, payload);
      closeDrawer(); toast(rec.id ? 'Сохранено' : cfg.added); onSaved();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, rec.id ? 'Сохранить' : 'Добавить');
  const foot = readOnly ? null : [h('span', { class: 'spacer' }), save];
  if (rec.id && can('owner')) {
    foot.unshift(h('button', { class: 'btn ghost danger', onclick: async () => {
      if (!confirm(cfg.delConfirm)) return;
      try { await api('DELETE', `${cfg.api}/${rec.id}`); closeDrawer(); toast('Удалено'); onSaved(); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Удалить'));
  }
  openDrawer(rec.id ? cfg.one : cfg.newTitle, h('div', {}, err,
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Дата'), g.date),
      h('label', { class: 'field' }, h('span', {}, 'Сумма, ₽'), g.amount)),
    h('label', { class: 'field' }, h('span', {}, 'Категория'), g.category_id),
    h('label', { class: 'field' }, h('span', {}, 'Относится к'), g.scope),
    h('p', { class: 'muted small', style: { marginTop: '-6px' } }, 'Можно записать на весь объект, на конкретный номер или оставить общим — тогда сумма делится между объектами пропорционально числу номеров.'),
    h('label', { class: 'field' }, h('span', {}, 'Комментарий'), g.comment)),
  foot);
}

async function viewExpenses(main) {
  scopeCache = null;
  let cfg = FLOW[state.financeKind] || FLOW.expense;
  const filters = { from: addDays(todayISO(), -30), to: addDays(todayISO(), 1), scope: `p:${state.propertyId}`, category_id: '' };
  let quickCat = null;
  const content = h('div', { class: 'stack' });
  const tabs = h('div', { class: 'seg' });
  const drawTabs = () => {
    tabs.innerHTML = '';
    Object.values(FLOW).forEach((f) => tabs.append(h('button', { class: f === cfg ? 'on' : '', onclick: () => {
      cfg = f; state.financeKind = f.kind; store.set('finance_kind', f.kind); filters.category_id = ''; quickCat = null; drawTabs(); csvBtn.lastChild.textContent = ' CSV'; run();
    } }, f.tab)));
  };
  const flowQuery = () => ({
    from: filters.from, to: filters.to, category_id: filters.category_id,
    property_id: filters.scope === 'none' ? 'none' : filters.scope.startsWith('p:') ? filters.scope.slice(2) : undefined,
    room_id: filters.scope.startsWith('r:') ? filters.scope.slice(2) : undefined,
  });
  const csvBtn = h('button', { class: 'btn', onclick: () => downloadCsv(`${cfg.api}/export.csv?` + qs(flowQuery()), `${cfg.csv}_${filters.from}_${filters.to}.csv`) },
    icon('download'), ' CSV');
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Финансы'), tabs, csvBtn), content);
  drawTabs();

  async function load() {
    const [scopes, cats, data] = await Promise.all([
      loadScopes(), api('GET', cfg.catApi), api('GET', cfg.api + '?' + qs(flowQuery()))]);
    content.innerHTML = '';

    // быстрое добавление: сумма → категория → сохранить
    const amountInp = h('input', { class: 'input', money: true, type: 'number', inputmode: 'decimal', min: 0, step: '0.01', placeholder: 'Сумма, ₽', style: { width: '150px' } });
    const dateInp = h('input', { class: 'input', type: 'date', value: todayISO(), style: { width: '150px' } });
    const quickScope = scopeSelect(scopes, filters.scope.startsWith('p:') || filters.scope.startsWith('r:') ? filters.scope : '', { attrs: { style: 'width:220px', 'aria-label': 'Относится к' } });
    const chips = h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } });
    const quickSave = h('button', { class: 'btn primary', disabled: true, onclick: async () => {
      quickSave.disabled = true;
      try {
        await api('POST', cfg.api, { amount: amountInp.value, category_id: quickCat, date: dateInp.value, ...scopePayload(quickScope.value) });
        amountInp.value = ''; quickCat = null; toast(cfg.added); load();
      } catch (ex) { toast(ex.message, true); quickSave.disabled = false; }
    } }, 'Сохранить');
    const drawChips = () => {
      chips.innerHTML = '';
      cats.forEach((c) => chips.append(h('button', {
        type: 'button', class: 'btn small' + (quickCat === c.id ? ' primary' : ''),
        style: quickCat === c.id ? {} : { borderColor: c.color, color: c.color },
        onclick: () => { quickCat = c.id; drawChips(); quickSave.disabled = false; },
      }, h('i', { class: 'dot', style: { background: c.color } }), c.name)));
    };
    drawChips();
    if (can('manager')) {
      content.append(h('div', { class: 'card card-pad' },
        h('h3', { style: { marginBottom: '10px' } }, 'Быстрое добавление'),
        cats.length
          ? [h('div', { class: 'quick-row' }, amountInp, dateInp, quickScope, quickSave), chips]
          : h('div', { class: 'empty' }, cfg.noCats)));
    }

    // фильтры
    const scopeSel = scopeSelect(scopes, filters.scope, { general: false, extra: [['', 'Все записи'], ['none', 'Только общие']], attrs: { style: 'width:230px' } });
    scopeSel.addEventListener('change', () => { filters.scope = scopeSel.value; load(); });
    const catSel = h('select', { class: 'input', style: { width: '190px' } }, h('option', { value: '' }, 'Все категории'),
      cats.map((c) => h('option', { value: c.id, selected: c.id === filters.category_id }, c.name)));
    catSel.addEventListener('change', () => { filters.category_id = catSel.value; load(); });
    const fromInp = h('input', { class: 'input', type: 'date', value: filters.from, style: { width: '150px' } });
    const toInp = h('input', { class: 'input', type: 'date', value: filters.to, style: { width: '150px' } });
    fromInp.addEventListener('change', () => { filters.from = fromInp.value; load(); });
    toInp.addEventListener('change', () => { filters.to = toInp.value; load(); });
    content.append(h('div', { class: 'board-tools filters' }, fromInp, h('span', { class: 'dash' }, '—'), toInp, scopeSel, catSel,
      can('manager') && cats.length ? h('button', { class: 'btn primary add-btn', style: { marginLeft: 'auto' },
        onclick: () => flowDrawer(cfg, cats, scopes, {}, load) }, icon('plus'), cfg.addBtn) : null));

    // итоги
    const rowsWithRoom = data.rows.filter((r) => r.room_id);
    content.append(h('div', { class: 'kpis' },
      kpiCard(cfg.kind === 'expense' ? 'Расходов за период' : 'Доходов за период', fmtMoney(data.total)),
      kpiCard('Записей', String(data.rows.length)),
      kpiCard('Самая крупная категория', data.by_category[0] ? data.by_category[0].category_name : '—', null, null, true),
      kpiCard('Записано на номера', fmtMoney(rowsWithRoom.reduce((s, r) => s + Number(r.amount), 0)))));

    // список
    const table = h('div', { class: 'card' });
    if (!data.rows.length) {
      table.append(h('div', { class: 'empty' }, h('h3', {}, cfg.emptyList), 'Измените период или фильтры.'));
    } else {
      table.append(h('div', { class: 'card-head' }, h('h2', {}, cfg.listTitle), h('b', {}, fmtMoney(data.total))),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' },
          h('thead', {}, h('tr', {}, ['Дата', 'Категория', 'Относится к', 'Сумма', 'Комментарий', 'Добавил'].map((t) => h('th', {}, t)))),
          h('tbody', {}, data.rows.map((r) => h('tr', { class: 'click', onclick: () => flowDrawer(cfg, cats, scopes, r, load) },
            h('td', { class: 'num', 'data-l': 'Дата' }, fmtShort(r.date)),
            h('td', { 'data-l': 'Категория' }, h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, h('i', { class: 'dot', style: { background: r.category_color } }), r.category_name)),
            h('td', { class: 'muted small', 'data-l': 'Относится к' }, scopeLabel(r)),
            h('td', { class: 'num strong', 'data-l': 'Сумма' }, fmtMoney(r.amount)),
            h('td', { class: 'muted small', 'data-l': 'Комментарий' }, r.comment),
            h('td', { class: 'muted small', 'data-l': 'Добавил' }, r.created_by_name || '—')))))));
    }
    content.append(table);

    // итоги по категориям и по номерам
    const summaryRow = h('div', { class: 'grid-2' });
    if (data.by_category.length) {
      const maxAmt = Math.max(1, ...data.by_category.map((x) => Number(x.amount)));
      summaryRow.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'По категориям')),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, data.by_category.map((x) => h('tr', {},
          h('td', {}, h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, h('i', { class: 'dot', style: { background: x.category_color } }), x.category_name)),
          h('td', { class: 'num' }, x.count), h('td', { class: 'num' }, fmtMoney(x.amount)),
          h('td', { style: { width: '30%' } }, h('div', { class: 'bar-h' }, h('i', { style: { width: `${(Number(x.amount) / maxAmt) * 100}%`, background: x.category_color } }))))))))));
    }
    if (rowsWithRoom.length) {
      const byRoom = {};
      rowsWithRoom.forEach((r) => {
        const k = r.room_id;
        const e = byRoom[k] ||= { name: r.room_name, property: r.property_name, amount: 0, count: 0 };
        e.amount += Number(r.amount); e.count += 1;
      });
      const list = Object.values(byRoom).sort((a, b) => b.amount - a.amount);
      const maxRoom = Math.max(1, ...list.map((x) => x.amount));
      summaryRow.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, cfg.byRoomTitle)),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, list.map((x) => h('tr', {},
          h('td', {}, `№${x.name}`, state.me.properties.length > 1 ? h('div', { class: 'muted small' }, x.property) : null),
          h('td', { class: 'num' }, x.count), h('td', { class: 'num' }, fmtMoney(x.amount)),
          h('td', { style: { width: '30%' } }, h('div', { class: 'bar-h' }, h('i', { style: { width: `${(x.amount / maxRoom) * 100}%`, background: 'var(--pine)' } }))))))))));
    }
    if (summaryRow.children.length) content.append(summaryRow);

    // категории (владелец управляет, остальные видят список)
    content.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, cfg.catTitle),
      can('owner') ? h('button', { class: 'btn small', onclick: () => categoryDrawer({ onSaved: load }, cfg) }, icon('plus'), 'Своя категория') : null),
      h('div', { class: 'card-pad', style: { display: 'flex', gap: '8px', flexWrap: 'wrap', paddingTop: '10px' } },
        cats.map((c) => h('button', { class: 'btn small' + (can('owner') ? '' : ' ghost'), style: { borderColor: c.color, color: c.color },
          onclick: () => can('owner') && categoryDrawer({ ...c, onSaved: load }, cfg) }, h('i', { class: 'dot', style: { background: c.color } }), c.name))),
      !can('owner') ? h('p', { class: 'muted small card-pad', style: { paddingTop: 0 } }, 'Свои категории добавляет владелец аккаунта.') : null));

    // повторяющиеся расходы (только для расходов)
    if (cfg.kind === 'expense') {
      const recurring = await api('GET', '/api/expense-recurring');
      const recCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Повторяющиеся расходы'),
        can('owner') ? h('button', { class: 'btn small', onclick: () => recurringDrawer(cats, {}, state.me.properties, load) }, icon('plus'), 'Добавить') : null));
      if (!recurring.length) {
        recCard.append(h('div', { class: 'empty' }, 'Пока нет ни одного шаблона. Например: аренда 1-го числа или интернет 10-го.'));
      } else {
        recCard.append(h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, recurring.map((r) => h('tr', { class: can('owner') ? 'click' : '', onclick: () => can('owner') && recurringDrawer(cats, r, state.me.properties, load) },
          h('td', {}, h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, h('i', { class: 'dot', style: { background: r.category_color } }), r.category_name),
            !r.active ? h('span', { class: 'pill none', style: { marginLeft: '8px' } }, 'выключен') : null),
          h('td', { class: 'muted small' }, r.property_name || 'Общий'),
          h('td', { class: 'num' }, fmtMoney(r.amount)),
          h('td', { class: 'muted small' }, `${r.day_of_month}-го числа`),
          h('td', { class: 'muted small' }, r.comment)))))));
      }
      content.append(recCard);
    }
  }
  const run = () => { content.innerHTML = ''; content.append(loadingBox()); load().catch((ex) => { content.innerHTML = ''; content.append(h('div', { class: 'card empty' }, ex.message)); }); };
  run();
}

// ---------- добавление объекта ----------
function addPropertyDrawer() {
  const types = [{ name: 'Стандарт', count: 4, capacity: 2, base_price: 3000 }];
  const g = {};
  const list = h('div');
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const drawTypes = () => {
    list.innerHTML = '';
    types.forEach((t, i) => {
      const inp = (key, label, type = 'text') => h('label', { class: 'field' }, h('span', {}, label),
        h('input', { class: 'input', type, value: t[key], min: type === 'number' ? 0 : null, oninput: (e) => { t[key] = e.target.value; } }));
      list.append(h('div', { class: 'type-row' }, inp('name', 'Категория'), inp('count', 'Номеров', 'number'),
        inp('capacity', 'Гостей', 'number'), inp('base_price', 'Цена за ночь', 'number'),
        h('button', { class: 'btn icon ghost del', type: 'button', title: 'Убрать категорию', 'aria-label': 'Убрать категорию', disabled: types.length === 1,
          onclick: () => { types.splice(i, 1); drawTypes(); } }, icon('close'))));
    });
  };
  drawTypes();
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; err.style.display = 'none';
    try {
      const prop = await api('POST', '/api/setup', {
        name: g.name.value, address: g.address.value, phone: g.phone.value, first_number: g.first.value, room_types: types,
      });
      state.me = await api('GET', '/api/me');
      closeDrawer();
      switchProperty(prop.id);
      toast('Объект добавлен');
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, 'Создать объект');
  openDrawer('Новый объект', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Название'), g.name = h('input', { class: 'input', required: true })),
    h('div', { class: 'row2' },
      h('label', { class: 'field' }, h('span', {}, 'Адрес'), g.address = h('input', { class: 'input' })),
      h('label', { class: 'field' }, h('span', {}, 'Телефон для гостей'), g.phone = h('input', { class: 'input', type: 'tel' }))),
    h('h3', { style: { margin: '4px 0 10px' } }, 'Номера'),
    list,
    h('div', { style: { display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', margin: '4px 0' } },
      h('button', { class: 'btn small', type: 'button', onclick: () => { types.push({ name: '', count: 1, capacity: 2, base_price: 3000 }); drawTypes(); } }, icon('plus'), 'Категория'),
      h('label', { class: 'check small' }, 'Первый номер', g.first = h('input', { class: 'input', type: 'number', value: 101, style: { width: '90px', height: '32px' } })))),
  [h('span', { class: 'spacer' }), save]);
}

// ---------- фото категории номеров ----------
// Фото сжимаются прямо в браузере (до 1600 px, JPEG) — на сервер уходит ~200–400 КБ вместо 5–10 МБ с телефона.
async function compressImage(file, maxSide = 1600, quality = 0.82) {
  const bmp = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bmp.width * scale); canvas.height = Math.round(bmp.height * scale);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); // прозрачные PNG не должны стать чёрными
  ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', quality));
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.onerror = rej; r.readAsDataURL(blob); });
}

function photoManager(typeId, onChange) {
  const box = h('div', { class: 'photo-box' });
  const status = h('div', { class: 'muted small' });
  const fileInp = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp', multiple: true, style: { display: 'none' }, onchange: async () => {
    const files = [...fileInp.files]; fileInp.value = '';
    for (let i = 0; i < files.length; i++) {
      status.textContent = `Загружаю ${i + 1} из ${files.length}…`;
      try { await api('POST', `/api/room-types/${typeId}/photos`, { data: await compressImage(files[i]) }); }
      catch (ex) { toast(`${files[i].name}: ${ex.message}`, true); }
    }
    status.textContent = ''; draw(); onChange?.();
  } });
  async function draw() {
    let photos = [];
    try { photos = await api('GET', `/api/room-types/${typeId}/photos`); } catch (ex) { box.textContent = ex.message; return; }
    box.innerHTML = '';
    const grid = h('div', { class: 'photo-grid' });
    photos.forEach((p, i) => {
      const img = h('img', { alt: 'Фото номера', loading: 'lazy' });
      fetch(`/api/photos/${p.id}/file`, { headers: { Authorization: `Bearer ${store.get('token')}` } })
        .then((r) => r.blob()).then((b) => { img.src = URL.createObjectURL(b); }).catch(() => {});
      grid.append(h('div', { class: 'photo-item' + (i === 0 ? ' main' : '') }, img,
        i === 0 ? h('span', { class: 'photo-tag' }, 'Главное') : h('button', { class: 'photo-act first', title: 'Сделать главным', type: 'button', onclick: async () => {
          const ids = [p.id, ...photos.filter((x) => x.id !== p.id).map((x) => x.id)];
          await api('PUT', `/api/room-types/${typeId}/photos/order`, { ids }); draw(); onChange?.();
        } }, '★'),
        h('button', { class: 'photo-act del', title: 'Удалить фото', type: 'button', onclick: async () => {
          if (!confirm('Удалить это фото?')) return;
          await api('DELETE', `/api/photos/${p.id}`); draw(); onChange?.();
        } }, '✕')));
    });
    box.append(grid, h('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' } },
      photos.length < 8 ? h('button', { class: 'btn small', type: 'button', onclick: () => fileInp.click() }, icon('plus'), 'Добавить фото') : h('span', { class: 'muted small' }, 'Максимум 8 фото'),
      status, fileInp));
  }
  draw();
  return h('div', { class: 'field' }, h('span', {}, 'Фото для страницы бронирования'), box,
    h('span', { class: 'muted small', style: { fontWeight: 400 } }, 'Гости увидят их в карточке номера. Первое фото — главное.'));
}

// Справочник дополнительных услуг (завтрак, трансфер…): добавляются в бронь одним выбором
function servicesCard() {
  const card = h('div', { class: 'card card-pad' });
  async function draw() {
    const list = await api('GET', '/api/services');
    card.innerHTML = '';
    const name = h('input', { class: 'input', placeholder: 'Например: Завтрак' });
    const price = h('input', { class: 'input', money: true, type: 'number', min: 0, placeholder: 'Цена, ₽', style: { maxWidth: '140px' } });
    card.append(h('h2', { style: { marginBottom: '6px' } }, 'Дополнительные услуги'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Завтрак, трансфер, поздний выезд, доп. место — добавляются в бронь одним выбором и входят в счёт.'),
      list.length ? h('div', { class: 'pay-list' }, list.map((x) => h('div', { class: 'pay-row' },
        h('span', { class: 'pay-sum', style: { flex: 1 } }, x.name + (x.active ? '' : ' (скрыта)')),
        h('span', { class: 'muted small' }, fmtMoney(x.price)),
        h('button', { class: 'btn small ghost', type: 'button', onclick: async () => { await api('PATCH', `/api/services/${x.id}`, { active: !x.active }); draw(); } }, x.active ? 'Скрыть' : 'Показать'),
        h('button', { class: 'btn icon ghost small', type: 'button', 'aria-label': 'Удалить услугу', onclick: async () => {
          if (confirm(`Удалить услугу «${x.name}»? В уже созданных бронях она останется.`)) { await api('DELETE', `/api/services/${x.id}`); draw(); }
        } }, icon('trash')))))
        : h('div', { class: 'muted small', style: { marginBottom: '10px' } }, 'Пока пусто. Добавьте первую услугу.'),
      h('div', { class: 'money-actions' }, name, price, h('button', { class: 'btn small primary', type: 'button', onclick: async () => {
        if (!name.value.trim()) { toast('Введите название услуги', true); return; }
        try { await api('POST', '/api/services', { name: name.value, price: price.value || 0 }); draw(); } catch (ex) { toast(ex.message, true); }
      } }, icon('plus'), 'Добавить')));
  }
  draw().catch((ex) => { card.textContent = ex.message; });
  return card;
}

// Тарифы категории: невозвратный, с завтраком… (± % и ± ₽ к цене ночи)
function plansManager(typeId) {
  const box = h('div', { class: 'field' });
  async function draw() {
    const plans = await api('GET', `/api/room-types/${typeId}/plans`);
    box.innerHTML = '';
    box.append(h('span', {}, 'Тарифы'),
      plans.length ? h('div', { class: 'pay-list' }, plans.map((p) => h('div', { class: 'pay-row' },
        h('span', { class: 'pay-sum', style: { flex: 1, minWidth: 0 } }, p.name + (p.active ? '' : ' (скрыт)')),
        h('span', { class: 'muted small' }, [Number(p.percent_delta) ? `${Number(p.percent_delta) > 0 ? '+' : ''}${Number(p.percent_delta)}%` : '', Number(p.fixed_delta) ? `${Number(p.fixed_delta) > 0 ? '+' : ''}${Math.round(p.fixed_delta)} ₽/ночь` : '', p.refundable ? '' : 'невозвратный', p.breakfast ? 'завтрак' : ''].filter(Boolean).join(' · ') || 'как базовая'),
        h('button', { class: 'btn small ghost', type: 'button', onclick: () => planDialog(typeId, p, draw) }, 'Изменить'))))
        : h('div', { class: 'muted small', style: { marginBottom: '8px' } }, 'Тарифов нет — гости видят одну цену. Добавьте, например, «Невозвратный −10%» или «С завтраком +500 ₽».'),
      h('div', {}, h('button', { class: 'btn small', type: 'button', onclick: () => planDialog(typeId, null, draw) }, icon('plus'), 'Тариф')));
  }
  draw().catch((ex) => { box.textContent = ex.message; });
  return box;
}

function planDialog(typeId, plan, onDone) {
  const p = plan || { name: '', description: '', percent_delta: 0, fixed_delta: 0, refundable: true, breakfast: false, active: true };
  const f = {
    name: h('input', { class: 'input', value: p.name, placeholder: 'Например: Невозвратный' }),
    description: h('input', { class: 'input', value: p.description, placeholder: 'Что видит гость (необязательно)' }),
    percent: h('input', { class: 'input', type: 'number', step: '1', value: Number(p.percent_delta) || '', placeholder: '0' }),
    fixed: h('input', { class: 'input', type: 'number', step: '50', value: Number(p.fixed_delta) || '', placeholder: '0' }),
    refundable: h('input', { type: 'checkbox', checked: p.refundable }), breakfast: h('input', { type: 'checkbox', checked: p.breakfast }),
    active: h('input', { type: 'checkbox', checked: p.active }),
  };
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const save = h('button', { class: 'btn primary', onclick: async () => {
    const payload = { name: f.name.value, description: f.description.value, percent_delta: f.percent.value || 0, fixed_delta: f.fixed.value || 0,
      refundable: f.refundable.checked, breakfast: f.breakfast.checked, active: f.active.checked };
    try {
      if (plan) await api('PATCH', `/api/plans/${plan.id}`, payload); else await api('POST', `/api/room-types/${typeId}/plans`, payload);
      closeModal(); toast('Тариф сохранён'); onDone?.();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  } }, 'Сохранить');
  openModal(plan ? 'Тариф' : 'Новый тариф', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Название'), f.name), h('label', { class: 'field' }, h('span', {}, 'Описание'), f.description),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Изменение цены, %'), f.percent), h('label', { class: 'field' }, h('span', {}, 'Изменение, ₽ за ночь'), f.fixed)),
    h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Отрицательное число — скидка: −10 даёт цену на 10% ниже. Применяется к цене каждой ночи.'),
    h('label', { class: 'check' }, f.refundable, 'Бесплатная отмена'), h('label', { class: 'check' }, f.breakfast, 'Завтрак включён'),
    h('label', { class: 'check' }, f.active, 'Показывать гостям на сайте')),
  [plan ? h('button', { class: 'btn ghost danger', onclick: async () => { if (confirm('Удалить тариф? В созданных бронях он останется.')) { await api('DELETE', `/api/plans/${plan.id}`); closeModal(); onDone?.(); } } }, 'Удалить') : null,
    h('span', { class: 'spacer' }), h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), save]);
}

// ---------- настройки ----------
async function viewSettings(main) {
  const content = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Настройки')), content);
  async function load() {
    const [prop, users] = await Promise.all([api('GET', `/api/properties/${state.propertyId}`), api('GET', '/api/users')]);
    content.innerHTML = '';
    const bookingUrl = `${location.origin}/book/${prop.public_slug}`;
    const f = {};
    const field = (key, label, attrs = {}) => h('label', { class: 'field' }, h('span', {}, label), f[key] = h('input', { class: 'input', value: prop[key] ?? '', ...attrs }));
    f.booking_enabled = h('input', { type: 'checkbox', checked: prop.booking_enabled });
    content.append(h('div', { class: 'card' },
      h('div', { class: 'card-head' }, h('h2', {}, 'Объекты'),
        h('button', { class: 'btn small', onclick: addPropertyDrawer }, icon('plus'), 'Добавить объект')),
      h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {},
        state.me.properties.map((p) => h('tr', { class: 'click', onclick: () => switchProperty(p.id) },
          h('td', {}, p.id === state.propertyId ? h('b', {}, p.name) : p.name),
          h('td', { style: { textAlign: 'right' } }, p.id === state.propertyId ? h('span', { class: 'pill ok' }, 'выбран') : null))))))));
    content.append(h('div', { class: 'grid-2' },
      h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '14px' } }, 'Объект'),
        field('name', 'Название'), field('address', 'Адрес'), field('phone', 'Телефон для гостей', { type: 'tel' }),
        h('div', { class: 'row2' }, field('check_in_time', 'Заезд с', { type: 'time', value: prop.check_in_time.slice(0, 5) }), field('check_out_time', 'Выезд до', { type: 'time', value: prop.check_out_time.slice(0, 5) })),
        h('button', { class: 'btn primary', onclick: async () => {
          try {
            await api('PATCH', `/api/properties/${prop.id}`, { name: f.name.value, address: f.address.value, phone: f.phone.value, check_in_time: f.check_in_time.value, check_out_time: f.check_out_time.value });
            state.me = await api('GET', '/api/me'); toast('Сохранено'); render();
          } catch (ex) { toast(ex.message, true); }
        } }, 'Сохранить')),
      h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '8px' } }, 'Бронирование на сайте'),
        h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Страница, где гость сам выбирает даты и отправляет заявку. Заявки появляются в шахматке со статусом «Заявка» (штриховка) — подтвердите или отклоните их в разделе «Брони». Неподтверждённая заявка сама снимается через 48 часов.'),
        h('label', { class: 'check', style: { marginBottom: '12px' } }, f.booking_enabled, 'Принимать заявки', h('span', { class: 'muted small' }, ''),),
        h('div', { class: 'field' }, h('span', {}, 'Ссылка для гостей и соцсетей'), h('div', { class: 'copy-line' }, h('input', { class: 'input', readonly: true, value: bookingUrl }),
          h('a', { class: 'btn small', href: bookingUrl, target: '_blank' }, 'Открыть'))),
        h('div', { class: 'field' }, h('span', {}, 'Код для вставки на ваш сайт'),
          h('textarea', { class: 'input', readonly: true, style: { fontSize: '12px', minHeight: '64px' } }, `<iframe src="${bookingUrl}?embed=1" style="width:100%;min-height:720px;border:0" loading="lazy"></iframe>`)),
        h('p', { class: 'muted small', style: { marginBottom: 0 } }, 'Онлайн-оплату (ЮKassa и т.п.) подключим следующим шагом вместе с чеками по 54-ФЗ.'))));
    f.booking_enabled.addEventListener('change', async () => {
      await api('PATCH', `/api/properties/${prop.id}`, { booking_enabled: f.booking_enabled.checked });
      toast(f.booking_enabled.checked ? 'Приём заявок включён' : 'Приём заявок выключен');
    });

    // категории и номера
    const typesCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Категории и номера'),
      h('button', { class: 'btn small', onclick: () => typeDrawer({ property_id: prop.id }) }, icon('plus'), 'Категория')));
    const typeDrawer = (t) => {
      const g = {};
      const fld = (k, l, a = {}) => h('label', { class: 'field' }, h('span', {}, l), g[k] = h('input', { class: 'input', value: t[k] ?? '', ...a }));
      openDrawer(t.id ? t.name : 'Новая категория', h('div', {},
        fld('name', 'Название'), fld('description', 'Описание для гостей'),
        h('div', { class: 'row3' }, fld('capacity', 'Гостей', { money: true, type: 'number', min: 1, value: t.capacity ?? 2 }), fld('base_price', 'Цена, ₽', { type: 'number', min: 0, value: t.base_price != null ? Math.round(t.base_price) : '' }), fld('min_stay', 'Мин. ночей', { type: 'number', min: 1, value: t.min_stay ?? 1 })),
        h('h3', { style: { margin: '14px 0 6px' } }, 'Доплаты и скидки'),
        h('div', { class: 'row2' }, fld('included_guests', 'Гостей в цене', { money: true, type: 'number', min: 0, value: t.included_guests || '', placeholder: 'все' }), fld('extra_guest_price', 'Доплата за гостя, ₽/ночь', { type: 'number', min: 0, value: t.extra_guest_price ? Math.round(t.extra_guest_price) : '', placeholder: '0' })),
        h('div', { class: 'row2' }, fld('week_discount_percent', 'Скидка от 7 ночей, %', { type: 'number', min: 0, max: 90, value: Number(t.week_discount_percent) || '', placeholder: '0' }), fld('month_discount_percent', 'Скидка от 28 ночей, %', { type: 'number', min: 0, max: 90, value: Number(t.month_discount_percent) || '', placeholder: '0' })),
        t.id ? plansManager(t.id) : null,
        t.id ? photoManager(t.id) : h('p', { class: 'muted small' }, 'Фото и тарифы можно добавить после сохранения категории.')),
      [t.id ? h('button', { class: 'btn ghost danger', onclick: async () => { try { await api('DELETE', `/api/room-types/${t.id}`); closeDrawer(); load(); } catch (ex) { toast(ex.message, true); } } }, 'Удалить') : null,
        h('span', { class: 'spacer' }),
        h('button', { class: 'btn primary', onclick: async () => {
          const payload = Object.fromEntries(Object.entries(g).map(([k, el]) => [k, el.value]));
          try { if (t.id) await api('PATCH', `/api/room-types/${t.id}`, payload); else await api('POST', '/api/room-types', { ...payload, property_id: prop.id }); closeDrawer(); toast('Сохранено'); load(); }
          catch (ex) { toast(ex.message, true); }
        } }, 'Сохранить')]);
    };
    typesCard.append(h('table', { class: 'list' }, h('tbody', {}, prop.room_types.map((t) => h('tr', {},
      h('td', { style: { width: '32%' } }, h('b', {}, t.name), h('div', { class: 'muted small' }, `до ${t.capacity} гостей · ${fmtMoney(t.base_price)} · от ${t.min_stay} ${nightsWord(t.min_stay)}`)),
      h('td', {}, h('div', { style: { display: 'flex', gap: '6px', flexWrap: 'wrap' } },
        t.rooms.map((r) => h('button', { class: 'btn small', title: 'Переименовать или удалить', onclick: async () => {
          const name = prompt(`Номер ${r.name}: новое название (оставьте пустым, чтобы удалить номер)`, r.name);
          if (name === null) return;
          try {
            if (name.trim() === '') { if (confirm(`Удалить номер ${r.name}?`)) await api('DELETE', `/api/rooms/${r.id}`); }
            else await api('PATCH', `/api/rooms/${r.id}`, { name });
            load();
          } catch (ex) { toast(ex.message, true); }
        } }, r.name)),
        h('button', { class: 'btn small ghost', onclick: async () => {
          const name = prompt('Название или номер комнаты'); if (!name) return;
          try { await api('POST', '/api/rooms', { room_type_id: t.id, name }); load(); } catch (ex) { toast(ex.message, true); }
        } }, icon('plus'), 'номер'))),
      h('td', { style: { textAlign: 'right' } }, h('button', { class: 'btn small ghost', onclick: () => typeDrawer(t) }, 'Изменить')))))));
    content.append(typesCard);

    // сотрудники
    const staffCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Сотрудники'),
      h('button', { class: 'btn small', onclick: () => {
        const g = {};
        const fld = (k, l, a = {}) => h('label', { class: 'field' }, h('span', {}, l), g[k] = h('input', { class: 'input', ...a }));
        g.role = h('select', { class: 'input', onchange: () => { propBox.style.display = g.role.value === 'landlord' ? '' : 'none'; } }, h('option', { value: 'manager' }, 'Администратор — брони, цены, площадки'), h('option', { value: 'housekeeper' }, 'Горничная — уборка, шахматка и заезды'), h('option', { value: 'landlord' }, 'Собственник — только чтение своих объектов и отчёт'));
        const propChecks = state.me.properties.map((pr) => [pr.id, h('input', { type: 'checkbox' }), pr.name]);
        const propBox = h('div', { class: 'field', style: { display: 'none' } }, h('span', {}, 'Какие объекты видит собственник'), propChecks.map(([, cb, name]) => h('label', { class: 'check' }, cb, name)));
        openDrawer('Новый сотрудник', h('div', {}, fld('name', 'Имя'), fld('email', 'Email для входа', { type: 'email' }), fld('password', 'Временный пароль', { type: 'text' }),
          h('label', { class: 'field' }, h('span', {}, 'Доступ'), g.role), propBox),
        [h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
          try { await api('POST', '/api/users', { name: g.name.value, email: g.email.value, password: g.password.value, role: g.role.value, property_ids: propChecks.filter(([, cb]) => cb.checked).map(([id]) => id) }); closeDrawer(); toast('Сотрудник добавлен'); load(); }
          catch (ex) { toast(ex.message, true); }
        } }, 'Добавить')]);
      } }, icon('plus'), 'Сотрудник')),
    h('table', { class: 'list' }, h('tbody', {}, users.map((u) => h('tr', {},
      h('td', {}, h('b', {}, u.name), h('div', { class: 'muted small' }, u.email)), h('td', {}, ROLE[u.role], u.role === 'landlord' ? h('div', { class: 'muted small' }, state.me.properties.filter((pr) => (u.property_ids || []).includes(pr.id)).map((pr) => pr.name).join(', ') || 'объекты не выбраны') : null),
      h('td', { style: { textAlign: 'right' } }, u.role !== 'owner' ? h('button', { class: 'btn small ghost danger', onclick: async () => {
        if (!confirm(`Удалить доступ для ${u.name}?`)) return;
        await api('DELETE', `/api/users/${u.id}`); load();
      } }, 'Удалить') : null))))));
    content.append(staffCard);

    // комиссии площадок — используются в финансовых отчётах
    const CHANNEL_LIST = ['avito', 'yandex', 'sutochno', 'ostrovok', 'other'];
    const commissions = await api('GET', '/api/channel-commissions');
    const cf = {};
    const commissionsCard = h('div', { class: 'card card-pad' },
      h('h2', { style: { marginBottom: '6px' } }, 'Комиссии площадок'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Учитываются в отчётах: чистая выручка по источнику = выручка минус комиссия.'),
      h('div', { class: 'row3' }, CHANNEL_LIST.map((ch) => {
        const row = commissions.find((x) => x.channel === ch) || { percent: 0 };
        return h('label', { class: 'field' }, h('span', {}, SOURCE[ch]),
          cf[ch] = h('input', { class: 'input', type: 'number', min: 0, max: 100, step: '0.1', value: Number(row.percent) }));
      })),
      h('button', { class: 'btn primary', onclick: async () => {
        try {
          await api('PUT', '/api/channel-commissions', { items: CHANNEL_LIST.map((ch) => ({ channel: ch, percent: cf[ch].value })) });
          toast('Сохранено');
        } catch (ex) { toast(ex.message, true); }
      } }, 'Сохранить'));
    content.append(commissionsCard);

    content.append(servicesCard(), templatesCard());

    // данные аккаунта: выгрузка и удаление
    content.append(h('div', { class: 'card card-pad' },
      h('h2', { style: { marginBottom: '6px' } }, 'Данные аккаунта'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Вы вправе в любой момент забрать все свои данные или удалить аккаунт целиком — со всеми объектами, бронями, расходами и сотрудниками. Удаление необратимо.'),
      h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap' } },
        h('button', { class: 'btn', onclick: () => downloadCsv('/api/account/export', 'fligel_data.json') }, icon('download'), 'Скачать все данные (JSON)'),
        h('button', { class: 'btn danger', onclick: deleteAccountDialog }, icon('trash'), 'Удалить аккаунт'))));
  }
  load().catch((ex) => content.append(h('div', { class: 'card empty' }, ex.message)));
}

function deleteAccountDialog() {
  const pass = h('input', { class: 'input', type: 'password', autocomplete: 'current-password' });
  const word = h('input', { class: 'input', placeholder: 'УДАЛИТЬ' });
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const go = h('button', { class: 'btn primary', disabled: true, style: { background: 'var(--clay)', borderColor: 'var(--clay)' }, onclick: async () => {
    go.disabled = true;
    try {
      await api('POST', '/api/account/delete', { password: pass.value });
      closeModal(); store.set('token', null); state.me = null; location.hash = ''; render(); toast('Аккаунт удалён');
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; go.disabled = false; }
  } }, 'Удалить навсегда');
  word.addEventListener('input', () => { go.disabled = word.value.trim().toUpperCase() !== 'УДАЛИТЬ'; });
  openModal('Удалить аккаунт навсегда?', h('div', {}, err,
    h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Будут удалены все объекты, номера, брони, расходы, доходы, сотрудники и настройки. Отменить это нельзя — сначала скачайте данные, если они могут понадобиться.'),
    h('label', { class: 'field' }, h('span', {}, 'Ваш пароль'), pass),
    h('label', { class: 'field' }, h('span', {}, 'Для подтверждения введите слово УДАЛИТЬ'), word)),
  [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), go]);
}

// ---------- уведомления в Telegram ----------
async function viewNotifications(main) {
  const content = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Уведомления')), content);
  async function load() {
    content.innerHTML = '';
    const s = await api('GET', '/api/telegram/status');
    if (!s.enabled) {
      content.append(h('div', { class: 'card card-pad' },
        h('h2', { style: { marginBottom: '6px' } }, 'Telegram-уведомления'),
        h('p', { class: 'muted small', style: { marginTop: 0 } },
          'Не настроены на сервере: администратору нужно создать бота через @BotFather и указать',
          h('code', {}, ' TELEGRAM_BOT_TOKEN '), 'в файле .env (см. deploy/DEPLOY.md).')));
      return;
    }
    const card = h('div', { class: 'card card-pad' });
    card.append(h('h2', { style: { marginBottom: '6px' } }, 'Telegram-уведомления'),
      h('p', { class: 'muted small', style: { marginTop: 0 } },
        'Каждый сотрудник подключает свой личный чат и сам выбирает, какие уведомления получать.'));
    if (s.linked) {
      card.append(h('p', {}, h('span', { class: 'pill ok' }, 'Подключено'),
        s.linked_at ? ` · с ${fmtDateTime(s.linked_at)}` : ''),
        h('button', { class: 'btn small ghost danger', onclick: async () => {
          if (!confirm('Отключить уведомления в этом чате?')) return;
          await api('POST', '/api/telegram/unlink'); load();
        } }, 'Отвязать чат'));
    } else {
      const codeBox = h('div');
      const draw = () => {
        codeBox.innerHTML = '';
        if (s.pending_code) {
          codeBox.append(
            h('p', {}, 'Напишите боту в Telegram сообщение:'),
            h('div', { class: 'copy-line' },
              h('input', { class: 'input', readonly: true, value: `/start ${s.pending_code}` }),
              h('button', { class: 'btn small', onclick: () => navigator.clipboard?.writeText(`/start ${s.pending_code}`).then(() => toast('Скопировано')) }, icon('copy'))),
            h('p', { class: 'muted small' }, `Код действует 30 минут (до ${fmtDateTime(s.pending_code_expires_at)}). Обновите страницу после отправки, чтобы увидеть статус.`));
        }
      };
      draw();
      card.append(codeBox, h('button', { class: 'btn primary', style: { marginTop: '8px' }, onclick: async () => {
        const r = await api('POST', '/api/telegram/link'); Object.assign(s, r); draw();
      } }, s.pending_code ? 'Получить новый код' : 'Подключить Telegram'));
    }
    content.append(card);

    const eventsCard = h('div', { class: 'card card-pad' },
      h('h2', { style: { marginBottom: '10px' } }, 'Какие события присылать мне'));
    const boxes = {};
    s.available_events.forEach((e) => {
      eventsCard.append(h('label', { class: 'check', style: { display: 'block', marginBottom: '8px' } },
        boxes[e.key] = h('input', { type: 'checkbox', checked: s.events.includes(e.key) }), ' ' + e.label));
    });
    eventsCard.append(h('button', { class: 'btn primary', onclick: async () => {
      const events = Object.entries(boxes).filter(([, el]) => el.checked).map(([k]) => k);
      try { await api('PUT', '/api/telegram/events', { events }); toast('Сохранено'); } catch (ex) { toast(ex.message, true); }
    } }, 'Сохранить'));
    content.append(eventsCard);
  }
  load().catch((ex) => content.append(h('div', { class: 'card empty' }, ex.message)));
}

// ---------- профиль ----------
// Шапка печатных документов: знак, название объекта, адрес и телефон
const letterhead = (name, line2) => h('div', { class: 'letterhead' }, h('span', { class: 'lh-mark' }, '◆'),
  h('div', {}, h('b', {}, name), line2 ? h('div', { class: 'lh-sub' }, line2) : null));

// Печать выбранного блока страницы: копия кладётся в #print-sheet, остальное приложение при печати скрыто
function printNode(node) {
  document.getElementById('print-sheet')?.remove();
  const sheet = h('div', { id: 'print-sheet' }, node.cloneNode(true));
  document.body.append(sheet);
  window.addEventListener('afterprint', () => sheet.remove(), { once: true });
  window.print();
}

// ---------- отчёт собственнику ----------
async function viewOwnerReport(main) {
  const landlord = state.me.role === 'landlord';
  const props = await api('GET', '/api/landlord/properties');
  const now = new Date();
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const monthInput = h('input', { class: 'input', type: 'month', value: store.get('or_month') || `${prev.getFullYear()}-${pad(prev.getMonth() + 1)}`, style: { width: '170px' } });
  const sel = h('select', { class: 'input', style: { width: '240px' } }, props.map((p) => h('option', { value: p.id, selected: p.id === state.propertyId }, p.name)));
  const box = h('div', { class: 'stack' });
  const csvBtn = h('button', { class: 'btn', onclick: () => downloadCsv('/api/landlord/report?' + qs({ property_id: sel.value, month: monthInput.value, format: 'csv' }), `owner_report_${monthInput.value}.csv`) }, icon('download'), 'CSV');
  const printBtn = h('button', { class: 'btn', onclick: () => printNode(box) }, icon('print'), 'Печать');
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Отчёт собственнику'), csvBtn, printBtn),
    h('div', { class: 'board-tools no-print', style: { marginBottom: '14px' } }, props.length > 1 ? sel : null, monthInput), box);
  if (!props.length) { box.append(h('div', { class: 'card empty' }, h('h3', {}, 'Нет доступных объектов'), landlord ? 'Попросите владельца сервиса открыть вам доступ к объекту.' : 'Добавьте объект в «Настройках».')); return; }
  const line = (label, value, cls, hint) => h('div', { class: 'or-line ' + (cls || '') }, h('span', {}, label, hint ? h('small', {}, hint) : null), h('b', {}, value));
  async function load() {
    store.set('or_month', monthInput.value);
    box.innerHTML = '';
    box.append(h('div', { class: 'card empty' }, h('span', { class: 'spin' }), 'Считаю…'));
    let r;
    try { r = await api('GET', '/api/landlord/report?' + qs({ property_id: sel.value, month: monthInput.value })); }
    catch (ex) { box.innerHTML = ''; box.append(h('div', { class: 'card empty' }, ex.message)); return; }
    box.innerHTML = '';
    const mcLabel = `Комиссия управляющей компании ${Number(r.mc_percent)}%`;
    box.append(
      h('div', { class: 'or-head print-only' }, h('h2', {}, r.property.name), h('div', { class: 'muted' }, `${r.property.address || ''} · отчёт за ${monthInput.value}`)),
      h('div', { class: 'kpis' }, kpiCard('К выплате собственнику', fmtMoney(r.payout)), kpiCard('Загрузка', `${r.occupancy}%`), kpiCard('Ночей продано', String(r.sold_nights)), kpiCard('Средняя цена ночи', fmtMoney(r.adr))),
      h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '10px' } }, 'Как получилась сумма'),
        line('Выручка от проживания', fmtMoney(r.revenue), '', 'по ночам месяца'),
        line('− Комиссии площадок', `−${fmtMoney(r.platform_commission)}`),
        line('= Чистая выручка', fmtMoney(r.net_revenue), 'sub'),
        Number(r.other_incomes) ? line('+ Прочие доходы объекта', fmtMoney(r.other_incomes)) : null,
        line('− Расходы объекта', `−${fmtMoney(r.expenses_total)}`, '', 'общие расходы компании сюда не входят'),
        Number(r.mc_percent) ? line(`− ${mcLabel}`, `−${fmtMoney(r.mc_commission)}`, '', r.mc_base === 'gross' ? 'от выручки' : 'от чистой выручки') : null,
        line('К выплате', fmtMoney(r.payout), 'total')),
      r.expenses.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Расходы объекта')),
        h('table', { class: 'list' }, h('tbody', {}, r.expenses.map((e) => h('tr', {}, h('td', {}, h('i', { class: 'dot', style: { background: e.color, marginRight: '8px' } }), e.name), h('td', { class: 'num' }, fmtMoney(e.amount))))))) : null,
      r.by_source.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'По источникам')),
        h('table', { class: 'list' }, h('thead', {}, h('tr', {}, ['Источник', 'Броней', 'Ночей', 'Выручка', 'Комиссия'].map((t) => h('th', {}, t)))),
          h('tbody', {}, r.by_source.map((x) => h('tr', {}, h('td', {}, x.label), h('td', { class: 'num' }, x.bookings), h('td', { class: 'num' }, x.nights), h('td', { class: 'num' }, fmtMoney(x.revenue)), h('td', { class: 'num' }, fmtMoney(x.commission))))))) : null,
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Проживания в месяце'), h('span', { class: 'pill none num' }, r.stays.length)),
        r.stays.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' }, h('thead', {}, h('tr', {}, ['Заезд', 'Выезд', 'Номер', 'Гость', 'Источник', 'Ночей', 'Выручка'].map((t) => h('th', {}, t)))),
          h('tbody', {}, r.stays.map((x) => h('tr', {}, h('td', { 'data-l': 'Заезд' }, fmtShort(x.check_in)), h('td', { 'data-l': 'Выезд' }, fmtShort(x.check_out)), h('td', { 'data-l': 'Номер' }, x.room_name),
            h('td', { 'data-l': 'Гость' }, x.guest), h('td', { 'data-l': 'Источник' }, SOURCE[x.source]), h('td', { class: 'num', 'data-l': 'Ночей' }, x.nights_in), h('td', { class: 'num', 'data-l': 'Выручка' }, fmtMoney(x.revenue)))))))
          : h('div', { class: 'empty' }, 'В этом месяце проживаний не было.')));
    if (can('owner')) {
      const pct = h('input', { class: 'input', type: 'number', min: 0, max: 100, step: '0.5', value: Number(r.mc_percent), style: { width: '110px' } });
      const base = h('select', { class: 'input', style: { width: '260px' } }, h('option', { value: 'net', selected: r.mc_base === 'net' }, 'от чистой выручки (после комиссий площадок)'), h('option', { value: 'gross', selected: r.mc_base === 'gross' }, 'от выручки (до комиссий площадок)'));
      box.append(h('div', { class: 'card card-pad no-print' }, h('h2', { style: { marginBottom: '6px' } }, 'Комиссия управляющей компании'),
        h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Если вы управляете чужими объектами: процент, который удерживает управляющая компания, и от какой суммы он считается. Собственники видят это в своём отчёте.'),
        h('div', { class: 'money-actions' }, pct, '%', base, h('button', { class: 'btn primary', onclick: async () => {
          try { await api('PUT', `/api/properties/${sel.value}/commission`, { percent: pct.value || 0, base: base.value }); toast('Сохранено'); load(); } catch (ex) { toast(ex.message, true); }
        } }, 'Сохранить'))));
    }
  }
  sel.addEventListener('change', load); monthInput.addEventListener('change', load);
  load();
}

// ---------- справка ----------
const HELP = [
  ['Шахматка: брони и перенос', null, [
    'Нажмите на пустую клетку, чтобы создать бронь, или протяните мышью по нескольким дням — даты подставятся сами.',
    'Бронь можно перетащить на другие даты или в другой номер (на телефоне — нажать и подержать). Перед сохранением откроется окно: даты, номер и цену можно поправить.',
    'Красным подсвечиваются конфликты — например, когда площадка прислала бронь на уже занятые даты.',
    'Брони с площадок (Авито, Яндекс и др.) приходят автоматически. Их даты меняются только на самой площадке.',
    'Клавиши на компьютере: ← → — неделя, T — сегодня, N — новая бронь, / — поиск гостя, ? — полный список. Любое удаление или перенос можно отменить кнопкой «Отменить» в уведомлении внизу.']],
  ['Заявки с вашего сайта', null, [
    'Гость заполняет форму на странице бронирования — заявка появляется в «Бронях» с оранжевым значком. Номер на эти даты сразу блокируется.',
    'Нажмите «Подтвердить» (после звонка гостю и оплаты) или «Отклонить». Если не ответить вовремя, заявка снимется сама — срок задаёт администратор сервера (по умолчанию 48 часов).',
    'Новые заявки приходят на почту и в Telegram, если вы их подключили (раздел «Уведомления» и «Профиль»).']],
  ['Цены и минимальный срок', 'manager', [
    'Базовая цена и минимальное число ночей задаются в «Настройках» для категории номеров.',
    'В разделе «Цены» можно поставить свою цену на выбранные даты, закрыть продажи или задать минимальный срок на сезон.']],
  ['Подключение площадок (Авито, Яндекс, Суточно, Островок)', 'manager', [
    'В разделе «Площадки» создайте подключение: система покажет ссылку на наш календарь — вставьте её в личном кабинете площадки, чтобы она знала о занятых датах.',
    'Ссылку календаря площадки вставьте в наш кабинет — тогда её брони попадут в шахматку. Обновление происходит каждые несколько минут.',
    'Через календарь передаётся только занятость. Цены и данные гостей с площадок не приходят.']],
  ['Финансы и отчёты', 'manager', [
    'В «Финансах» записывайте расходы и доходы — общие по объекту или по конкретному номеру. Категории можно создавать свои.',
    'В «Отчётах» — выручка, загрузка, структура по источникам, расходы и прибыль по номерам. Данные можно выгрузить в CSV.',
    'Оплату брони отмечайте в карточке брони (кнопка «Оплачено полностью»).']],
  ['Фото номеров на странице бронирования', 'owner', [
    'Откройте «Настройки» → «Изменить» у категории номеров. Там можно загрузить до 8 фото — первое будет главным. Фото сжимаются автоматически.']],
  ['Перенос данных из Excel или другой системы', 'manager', [
    'Раздел «Брони» → «Импорт». Сохраните свою таблицу как CSV, выберите файл: система сначала проверит его и покажет, что загрузится, а какие строки пропущены. Образец файла скачивается там же.']],
  ['Сотрудники и доступ', 'owner', [
    'В «Настройках» можно добавить администраторов и горничных. Администратор видит брони, цены и финансы; горничная — только шахматку и страницу «Сегодня» с отметкой об уборке.']],
  ['Резервные копии и ваши данные', 'owner', [
    'Данные хранятся на сервере в России. В «Настройках» → «Данные аккаунта» можно скачать всё одним файлом или удалить аккаунт.']],
];

function viewHelp(main) {
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Справка')));
  const shown = HELP.filter(([, role]) => !role || can(role));
  main.append(h('div', { class: 'stack' },
    h('div', { class: 'card card-pad' }, h('p', { style: { margin: 0 } },
      'Коротко о главном. Если что-то непонятно — напишите нам, подскажем и поправим интерфейс.')),
    shown.map(([title, , items], i) => h('details', { class: 'card help-item', open: i === 0 },
      h('summary', {}, title), h('ul', {}, items.map((t) => h('li', {}, t)))))));
}

async function viewProfile(main) {
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Профиль')));
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const ok = h('div', { class: 'note ok', style: { display: 'none' } });
  const current = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', required: true });
  const next = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', required: true });
  const emailBox = h('input', { type: 'checkbox', checked: state.me.notify_email !== false, onchange: async () => {
    try { await api('PATCH', '/api/me/preferences', { notify_email: emailBox.checked }); state.me.notify_email = emailBox.checked; toast('Сохранено'); }
    catch (ex) { emailBox.checked = !emailBox.checked; toast(ex.message, true); }
  } });
  const submit = h('button', { class: 'btn primary', type: 'submit' }, 'Сменить пароль');
  const form = h('form', { onsubmit: async (e) => {
    e.preventDefault(); submit.disabled = true; err.style.display = 'none'; ok.style.display = 'none';
    try {
      const r = await api('POST', '/api/auth/change-password', { current_password: current.value, new_password: next.value });
      ok.textContent = r.message; ok.style.display = 'block'; current.value = ''; next.value = '';
    } catch (ex) { err.textContent = ex.message; err.style.display = 'block'; } finally { submit.disabled = false; }
  } },
  h('label', { class: 'field' }, h('span', {}, 'Текущий пароль'), current),
  h('label', { class: 'field' }, h('span', {}, 'Новый пароль (не короче 8 символов)'), next),
  submit);
  main.append(
    h('div', { class: 'card card-pad', style: { marginBottom: '16px' } },
      h('h2', { style: { marginBottom: '6px' } }, state.me.name),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, state.me.email, ' · ', ROLE[state.me.role], ' · ', state.me.account_name),
      can('owner') ? h('p', { class: 'small', style: { marginBottom: 0 } }, 'Тариф: ',
        h('b', {}, state.me.plan_label || state.me.plan),
        state.me.trial_ends ? ` · пробный период до ${fmtDate(state.me.trial_ends)}` : (state.me.paid_until ? ` · оплачен до ${fmtDate(state.me.paid_until)}` : ''),
        ` · объектов ${state.me.properties.length} из ${state.me.properties_limit}`) : null),
    h('div', { class: 'card card-pad', style: { marginBottom: '16px' } }, h('h2', { style: { marginBottom: '8px' } }, 'Оформление'),
      h('div', { class: 'seg' }, [['auto', 'Как в системе'], ['light', 'Светлая'], ['dark', 'Тёмная']].map(([k, l]) => h('button', { type: 'button', class: (store.get('theme', 'auto') === k) ? 'on' : '', onclick: (e) => {
        store.set('theme', k); applyTheme(); e.currentTarget.parentNode.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === e.currentTarget));
      } }, l)))),
    can('manager') ? h('div', { class: 'card card-pad', style: { marginBottom: '16px' } },
      h('h2', { style: { marginBottom: '8px' } }, 'Письма о новых заявках'),
      h('label', { class: 'check' }, emailBox, ' Присылать на почту письмо, когда гость оставил заявку на сайте'),
      h('p', { class: 'muted small', style: { marginBottom: 0 } }, 'Работает, когда на сервере настроена почта (SMTP). Уведомления в Telegram настраиваются в разделе «Уведомления».')) : null,
    h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '14px' } }, 'Сменить пароль'), err, ok, form));
}

boot();
