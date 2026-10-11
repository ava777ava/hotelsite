// Флигель — интерфейс администратора (раздел «главный модуль: маршруты и каркас»). ES-модуль без сборки.
import { viewAnalytics } from './analytics.js';
import { viewAutoprice } from './autoprice.js';
import { viewAutopilot } from './autopilot.js';
import { viewAuth, viewResetPassword, viewWizard } from './auth.js';
import { viewBoard } from './board.js';
import { bookingDrawer, ensureBoardData } from './booking.js';
import { viewBilling } from './billing.js';
import { viewBookings } from './bookings.js';
import { viewChannels } from './channels.js';
import { viewCleaning } from './cleaning.js';
import { $app, G, ROLE, SOURCE, addDays, api, applyTheme, can, closeDrawer, closeModal, fmtShort, h, icon, openDrawer, openModal, qs, setOffline, state, store, todayISO } from './core.js';
import { viewExpenses } from './finance.js';
import { viewGuests } from './guests.js';
import { viewHousehold } from './household.js';
import { viewHelp } from './help.js';
import { bellDrawer, viewNotifications } from './notifications.js';
import { viewAudit, viewOwnerReport } from './owner.js';
import { viewProfile } from './profile.js';
import { viewRates } from './rates.js';
import { viewReviews } from './reviews.js';
import { viewStats } from './reports.js';
import { viewSettings } from './settings.js';
import { viewTasks } from './tasks.js';
import { viewToday } from './today.js';
import { hooks } from './core.js';

export const ROUTES = {
  board: { title: 'Шахматка', icon: 'board', view: viewBoard, landlord: true },
  today: { title: 'Сегодня', icon: 'today', view: viewToday },
  cleaning: { title: 'Уборка', icon: 'clean', view: viewCleaning },
  tasks: { title: 'Задачи', icon: 'tasks', view: viewTasks },
  household: { title: 'Хозяйство', icon: 'box', view: viewHousehold },
  bookings: { title: 'Брони', icon: 'list', view: viewBookings, role: 'manager' },
  guests: { title: 'Гости', icon: 'users', view: viewGuests, role: 'manager' },
  reviews: { title: 'Отзывы', icon: 'stats', view: viewReviews, role: 'manager' },
  rates: { title: 'Цены', icon: 'rates', view: viewRates, role: 'manager' },
  autoprice: { title: 'Автоцены', icon: 'rates', view: viewAutoprice, role: 'manager' },
  channels: { title: 'Площадки', icon: 'channels', view: viewChannels, role: 'manager' },
  expenses: { title: 'Финансы', icon: 'expenses', view: viewExpenses, role: 'manager' },
  analytics: { title: 'Аналитика', icon: 'trend', view: viewAnalytics, role: 'manager' },
  stats: { title: 'Отчёты', icon: 'stats', view: viewStats, role: 'manager' },
  notifications: { title: 'Уведомления', icon: 'bell', view: viewNotifications, role: 'manager' },
  autopilot: { title: 'Автопилот', icon: 'bolt', view: viewAutopilot, role: 'owner' },
  billing: { title: 'Тариф и счета', icon: 'expenses', view: viewBilling, role: 'owner' },
  settings: { title: 'Настройки', icon: 'settings', view: viewSettings, role: 'owner' },
  profile: { title: 'Профиль', icon: 'user', view: viewProfile, landlord: true },
  audit: { title: 'Журнал действий', icon: 'list', view: viewAudit, role: 'owner' },
  ownerreport: { title: 'Отчёт собственнику', icon: 'stats', view: viewOwnerReport, roles: ['landlord', 'manager', 'owner'] },
  help: { title: 'Справка', icon: 'help', view: viewHelp, landlord: true },
};
// Собственник видит только шахматку (чтение), свой отчёт, справку и профиль; остальные — по ролям
export const routeVisible = (d) => (d.roles ? d.roles.includes(state.me.role) : (state.me.role === 'landlord' ? !!d.landlord : (!d.role || can(d.role))));
export const MOBILE_ORDER = ['board', 'today', 'cleaning', 'bookings', 'tasks', 'household', 'guests', 'reviews', 'autopilot', 'expenses', 'channels', 'notifications', 'settings', 'billing', 'rates', 'autoprice', 'analytics', 'stats', 'ownerreport', 'audit', 'help', 'profile'];
export const LANDLORD_ORDER = ['ownerreport', 'board', 'help', 'profile'];
export const currentRoute = () => { const home = { housekeeper: 'cleaning', landlord: 'ownerreport' }[state.me?.role] || (window.innerWidth < 860 && can('manager') ? 'today' : 'board'); const r = location.hash.replace(/^#\/?/, '').split('?')[0] || home; return ROUTES[r] ? r : home; };

window.addEventListener('hashchange', () => render());

// Горячие клавиши: работают, когда курсор не в поле ввода и не открыто окно
export const HOTKEYS = [['← →', 'Шахматка: неделя назад / вперёд'], ['T', 'Шахматка: перейти к сегодняшнему дню'], ['N', 'Новая бронь'],
  ['/', 'Поиск гостя'], ['G, затем Ш / С / Б / У', 'Перейти: шахматка / сегодня / брони / уборка'], ['?', 'Показать эту подсказку'], ['Esc', 'Закрыть окно']];
export function hotkeysDialog() {
  openModal('Горячие клавиши', h('table', { class: 'list' }, h('tbody', {}, HOTKEYS.map(([k, t]) => h('tr', {}, h('td', {}, h('kbd', {}, k)), h('td', {}, t))))),
    [h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: () => closeModal(true) }, 'Понятно')]);
}
document.addEventListener('keydown', (e) => {
  if (!state.me || e.ctrlKey || e.metaKey || e.altKey) return;
  const t = e.target;
  if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
  if (G.modalEl || G.drawerEl) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (G.goPending) {
    G.goPending = false;
    const to = { 'ш': 'board', 'п': 'today', 'с': 'today', 'б': 'bookings', 'у': 'cleaning', b: 'board', t: 'today', k: 'bookings', c: 'cleaning' }[k];
    if (to && ROUTES[to] && routeVisible(ROUTES[to])) { e.preventDefault(); location.hash = `#/${to}`; }
    return;
  }
  if (k === '?' ) { e.preventDefault(); hotkeysDialog(); }
  else if (k === 'g' || k === 'п') G.goPending = true, setTimeout(() => { G.goPending = false; }, 1500);
  else if (G.boardActions && k === 'ArrowLeft') { e.preventDefault(); G.boardActions.shift(-7); }
  else if (G.boardActions && k === 'ArrowRight') { e.preventDefault(); G.boardActions.shift(7); }
  else if (G.boardActions && (k === 't' || k === 'е')) G.boardActions.today();
  else if (can('manager') && (k === 'n' || k === 'т')) { e.preventDefault(); bookingDrawer({}, () => render()); }
  else if (can('manager') && (k === '/' || k === '.')) { e.preventDefault(); guestSearchDrawer(); }
});

export async function boot() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => { /* без офлайн-режима тоже работаем */ });
  if (store.get('token')) {
    try { state.me = await api('GET', '/api/me'); } catch { state.me = null; }
  }
  render();
}

// Счётчики в меню (заявки с сайта, конфликты площадок) и автообновление экранов: два сотрудника
// работают одновременно, и новая бронь/заявка должна появиться у другого без перезагрузки страницы.
export async function refreshBadges() {
  if (!state.me || state.me.role === 'landlord') return;
  try {
    const b = await api('GET', '/api/badges');
    state.requests = b.requests; state.conflicts = b.conflicts; state.tasks = b.tasks || 0; updateTitle();
    if (can('manager')) try { state.bell = (await api('GET', '/api/notifications')).unread; } catch { /* колокольчик необязателен */ }
    document.querySelectorAll('[data-bell]').forEach((el) => { el.textContent = state.bell || ''; el.style.display = state.bell ? '' : 'none'; });
    document.querySelectorAll('[data-badge]').forEach((el) => {
      const n = state[el.dataset.badge] || 0;
      el.textContent = n; el.style.display = n ? '' : 'none';
    });
  } catch { /* сеть пропала — попробуем в следующий раз */ }
}
export function autoRefresh(fn, seconds = 45) {
  clearInterval(G.autoTimer);
  G.autoFn = fn;
  G.autoTimer = setInterval(() => {
    // не мешаем, пока человек что-то делает: открыто окно/панель, идёт перетаскивание, вкладка скрыта
    if (document.hidden || G.drawerEl || G.modalEl || document.querySelector('.bar.dragging, .bar.lifted')) return;
    fn();
  }, seconds * 1000);
}
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && state.me) { refreshBadges(); if (G.autoFn && !G.drawerEl && !G.modalEl) G.autoFn(); }
});
setInterval(() => { if (!document.hidden) refreshBadges(); }, 60000);

// Число новых заявок видно прямо во вкладке браузера: «(3) Брони — Флигель»
export function updateTitle() { document.title = (state.requests ? `(${state.requests}) ` : '') + G.baseTitle; }

export function render() {
  closeDrawer();
  closeModal();
  clearInterval(G.autoTimer); G.autoFn = null; G.boardActions = null;
  $app.innerHTML = '';
  if (location.hash.startsWith('#/reset-password')) return $app.append(viewResetPassword());
  if (!state.me) return $app.append(viewAuth());
  if (!state.me.properties.length) return $app.append(viewWizard());
  if (!state.me.properties.find((p) => p.id === state.propertyId)) state.propertyId = state.me.properties[0].id;
  const route = currentRoute();
  const def = ROUTES[route];
  G.baseTitle = `${def.title} — Флигель`;
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
export async function jumpToBooking(b) {
  closeDrawer();
  state.propertyId = b.property_id; store.set('propertyId', b.property_id);
  state.boardFrom = addDays(b.check_in, -2);
  location.hash = '#/board';
  render();
  G.boardData = null;
  try { await ensureBoardData(); } catch { /* карточка всё равно откроется */ }
  bookingDrawer(b, () => render());
}

export function guestSearchDrawer() {
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

export function layout(route, main) {
  const visible = Object.entries(ROUTES).filter(([, d]) => routeVisible(d));
  if (state.me.role === 'landlord') visible.sort((a, b2) => LANDLORD_ORDER.indexOf(a[0]) - LANDLORD_ORDER.indexOf(b2[0]));
  const BADGE = { bookings: 'requests', channels: 'conflicts', tasks: 'tasks' };
  const link = ([key, d]) => h('a', { href: `#/${key}`, class: key === route ? 'active' : '' }, icon(d.icon), h('span', {}, d.title),
    BADGE[key] ? h('span', { class: 'badge', 'data-badge': BADGE[key], style: { display: state[BADGE[key]] ? '' : 'none' } }, state[BADGE[key]] || 0) : null);
  const prop = state.me.properties.find((p) => p.id === state.propertyId);
  const bellBtn = (cls, color) => (can('manager') ? h('button', { class: `btn icon ghost bell-btn ${cls}`, title: 'Уведомления', 'aria-label': 'Уведомления', style: { color }, onclick: bellDrawer },
    icon('bell'), h('span', { class: 'bell-dot', 'data-bell': '1', style: { display: state.bell ? '' : 'none' } }, state.bell || '')) : null);
  const sideSearchBtn = can('manager') ? h('button', { class: 'btn icon ghost', title: 'Поиск гостя', 'aria-label': 'Поиск гостя', style: { color: '#C3CCC0' }, onclick: guestSearchDrawer }, icon('search')) : null;
  const mobileSearchBtn = can('manager') ? h('button', { class: 'btn icon ghost', title: 'Поиск гостя', 'aria-label': 'Поиск гостя', style: { color: '#fff' }, onclick: guestSearchDrawer }, icon('search')) : null;
  // На телефоне в нижней панели помещается 5 пунктов: четыре главных и «Ещё» со всеми остальными разделами.
  // горничной задачи важнее броней: они идут сразу после уборки
  const order = state.me.role === 'landlord' ? LANDLORD_ORDER : (state.me.role === 'housekeeper' ? MOBILE_ORDER.filter((k) => k !== 'tasks').flatMap((k) => (k === 'cleaning' ? [k, 'tasks'] : [k])) : MOBILE_ORDER);
  const ordered = order.map((k) => visible.find(([v]) => v === k)).filter(Boolean);
  const mainItems = ordered.length <= 5 ? ordered : ordered.slice(0, 4);
  const rest = ordered.slice(mainItems.length);
  const moreBtn = rest.length ? h('button', { class: 'more-btn' + (rest.some(([k]) => k === route) ? ' active' : ''), onclick: () => moreSheet(rest, route) },
    icon('more'), h('span', {}, 'Ещё')) : null;
  return h('div', { class: 'shell' },
    h('aside', { class: 'side' },
      h('div', { class: 'brand' }, h('div', { class: 'brand-mark' }),
        h('div', { style: { flex: 1, minWidth: 0 } }, h('div', { class: 'brand-name' }, 'Флигель'),
        propertySwitcher('prop-switch') || h('div', { class: 'brand-sub' }, prop ? prop.name : '')),
        bellBtn('', '#C3CCC0'), sideSearchBtn),
      h('nav', { class: 'nav' }, visible.map(link)),
      h('div', { class: 'side-foot' }, h('b', {}, state.me.name), ROLE[state.me.role],
        h('br'), h('button', { onclick: logout }, 'Выйти'), ' · ', h('button', { class: 'desk-only', title: 'Горячие клавиши', onclick: hotkeysDialog }, '⌨'), ' · ', h('button', { title: 'Светлая / тёмная тема', onclick: () => { const dark = getComputedStyle(document.documentElement).colorScheme === 'dark'; store.set('theme', dark ? 'light' : 'dark'); applyTheme(); } }, 'Тема'))),
    h('div', {},
      h('div', { class: 'mobile-top' }, h('div', { class: 'brand-mark' }),
        propertySwitcher('prop-switch') || h('div', { class: 'brand-name' }, prop ? prop.name : 'Флигель'),
        bellBtn('', '#fff'), mobileSearchBtn,
        h('button', { class: 'btn small ghost', style: { color: '#fff' }, onclick: logout }, 'Выйти')),
      topBanner(), main),
    h('nav', { class: 'mobile-nav', 'aria-label': 'Разделы' }, mainItems.map(link), moreBtn));
}

// Полоса сверху: демо-версия или напоминание о тарифе (мягкое — работу не блокирует; «скрыть» действует до завтра)
function topBanner() {
  const m = state.me;
  const n = m.is_demo ? { level: 'info', text: 'Это демо-версия с вымышленными данными: можно нажимать всё подряд. Данные сбрасываются каждую ночь; пароль, удаление аккаунта и подключение площадок отключены.', demo: true } : m.billing_notice;
  if (!n || store.get('banner_hidden') === `${n.kind || 'demo'}:${todayISO()}`) return null;
  const el = h('div', { class: `top-banner ${n.level || ''}`, role: 'status' }, h('span', {}, n.text),
    n.demo ? null : h('a', { href: '#/billing', class: 'btn small' }, 'Тариф и счета'),
    h('button', { class: 'btn small ghost', 'aria-label': 'Скрыть до завтра', onclick: () => { store.set('banner_hidden', `${n.kind || 'demo'}:${todayISO()}`); el.remove(); } }, '×'));
  return el;
}

// Все разделы, не поместившиеся в нижнюю панель телефона
export function moreSheet(items, route) {
  openModal('Разделы', h('div', { class: 'more-grid' },
    items.map(([key, d]) => h('a', { href: `#/${key}`, class: key === route ? 'active' : '', onclick: () => closeModal() }, icon(d.icon), d.title))),
  [h('button', { class: 'btn', onclick: () => closeModal() }, 'Закрыть'), h('span', { class: 'spacer' }),
    h('span', { class: 'muted small' }, `${state.me.name} · ${ROLE[state.me.role]}`)]);
}

export function logout() {
  store.set('token', null); state.me = null; location.hash = '';
  try { caches.delete('fligel-api-v1'); } catch { /* нет кэша */ }
  setOffline(false); render();
}

export function switchProperty(id) {
  if (id === state.propertyId) return;
  state.propertyId = id; store.set('propertyId', id);
  G.boardData = null;
  render();
}

export function propertySwitcher(cls) {
  if (state.me.properties.length < 2) return null;
  return h('select', { class: cls, onchange: (e) => switchProperty(e.target.value), 'aria-label': 'Объект' },
    state.me.properties.map((p) => h('option', { value: p.id, selected: p.id === state.propertyId }, p.name)));
}

// Список объектов для выбора «Этот объект / Все объекты» на страницах, где это уместно.
export function scopeSeg(scope, onChange) {
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

hooks.logout = logout;
window.addEventListener('online', () => { setOffline(false); if (state.me) render(); });
window.addEventListener('offline', () => setOffline(true));

boot();
