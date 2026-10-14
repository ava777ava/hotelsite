// Флигель — интерфейс администратора (раздел «общие помощники»). ES-модуль без сборки.
import { moneyize, skeleton } from './ui.js';

export const G = {
  netBanner: null,
  reloginPromise: null,
  goPending: false,
  autoTimer: null,
  autoFn: null,
  baseTitle: 'Флигель',
  drawerEl: null,
  drawerDirty: false,
  drawerOnDismiss: null,
  boardData: null,
  boardActions: null,
  modalEl: null,
  modalOnDismiss: null,
  scopeCache: null,
};

// Хуки: core не импортирует app (иначе цикл); app кладёт сюда выход при старте
export const hooks = {};

// ---------- утилиты ----------
// Защита от частой ошибки: нативный append() превращает null и массивы в текст «null» / «[object HTMLDivElement]».
// Здесь пустые значения пропускаются, а вложенные массивы раскрываются — как это делает h().
export const nativeAppend = Element.prototype.append;
Element.prototype.append = function append(...nodes) {
  return nativeAppend.apply(this, nodes.flat(Infinity).filter((n) => n !== null && n !== undefined && n !== false));
};
export const $app = document.getElementById('app');

export function h(tag, attrs = {}, ...children) {
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

export const ICONS = {
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
  tasks: '<rect x="4" y="4" width="16" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M8.5 12.5l2.5 2.5 4.5-5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>',
  bolt: '<path d="M13 3 5 13.5h5.5L10 21l8-10.5h-5.5z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
  trend: '<path d="M3 17l6-6 4 4 8-9M15 6h6v6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  box: '<path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z M3.5 7.5 12 12l8.5-4.5 M12 12v9" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  user: '<circle cx="12" cy="8" r="3.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M4.5 20c1.2-4 4-6 7.5-6s6.3 2 7.5 6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
};
export const icon = (name) => { const s = h('span'); s.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`; return s.firstChild; };

export const WD = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
export const MONTHS_NOM = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
export const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
export const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
export const SOURCE = {
  manual: 'Вручную', direct: 'Сайт', avito: 'Авито', yandex: 'Яндекс', sutochno: 'Суточно', ostrovok: 'Островок', other: 'Другое',
};
export const STATUS = { confirmed: 'Подтверждена', pending: 'Заявка', blocked: 'Даты закрыты', cancelled: 'Отменена' };
export const ROLE = { owner: 'Владелец', manager: 'Администратор', housekeeper: 'Горничная', landlord: 'Собственник' };

export const pad = (n) => String(n).padStart(2, '0');
export const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const parseISO = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
export const addDays = (s, n) => { const d = parseISO(s); d.setDate(d.getDate() + n); return iso(d); };
export const diffDays = (a, b) => Math.round((parseISO(b) - parseISO(a)) / 86400000);
export const todayISO = () => iso(new Date());
export const fmtDate = (s) => { const d = parseISO(s); return `${d.getDate()} ${MONTHS[d.getMonth()]}`; };
export const fmtShort = (s) => { const d = parseISO(s); return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}`; };
export const fmtMoney = (v) => `${Math.round(Number(v || 0)).toLocaleString('ru-RU')} ₽`;
export const fmtPriceCell = (v) => { const n = Math.round(Number(v || 0)); return n >= 10000 ? `${(n / 1000).toFixed(n % 1000 ? 1 : 0).replace('.', ',')}к` : n.toLocaleString('ru-RU'); };
export const nightsWord = (n) => { const m10 = n % 10, m100 = n % 100; if (m10 === 1 && m100 !== 11) return 'ночь'; if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return 'ночи'; return 'ночей'; };
export const fmtDateTime = (s) => { if (!s) return '—'; const d = new Date(s); return `${pad(d.getDate())}.${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
export const ago = (s) => {
  if (!s) return 'ещё не было';
  const min = Math.round((Date.now() - new Date(s)) / 60000);
  if (min < 1) return 'только что'; if (min < 60) return `${min} мин назад`;
  const hr = Math.round(min / 60); if (hr < 24) return `${hr} ч назад`;
  return fmtDateTime(s);
};

export const loadingBox = () => h('div', { class: 'card' }, skeleton(5));

export function toast(msg, bad = false) {
  const t = h('div', { class: 'toast' + (bad ? ' bad' : ''), title: 'Нажмите, чтобы закрыть', onclick: () => t.remove() }, msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), bad ? 5000 : 2800);
}

// Уведомление с кнопкой «Отменить»: действие уже выполнено, но его можно вернуть в течение нескольких секунд
export function toastUndo(msg, undo, after, seconds = 8) {
  const t = h('div', { class: 'toast with-undo' }, h('span', {}, msg),
    h('button', { class: 'toast-undo', type: 'button', onclick: async () => {
      t.remove();
      try { await undo(); toast('Возвращено'); after?.(); } catch (ex) { toast(ex.message, true); }
    } }, 'Отменить'));
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), seconds * 1000);
}

// Тема оформления: «как в системе» / светлая / тёмная (хранится в браузере)
export function applyTheme() {
  const t = (() => { try { return localStorage.getItem('theme') || 'auto'; } catch { return 'auto'; } })();
  if (t === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', t);
}
applyTheme();

export const store = {
  get(k, def = null) { try { return localStorage.getItem(k) ?? def; } catch { return def; } },
  set(k, v) { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* приватный режим */ } },
};

// ---------- API ----------
export class ApiError extends Error { constructor(msg, status, data) { super(msg); this.status = status; this.data = data; } }

export function setOffline(on, cachedAt) {
  if (!on) { G.netBanner?.remove(); G.netBanner = null; return; }
  if (!G.netBanner) { G.netBanner = h('div', { class: 'net-banner', role: 'status' }); document.body.append(G.netBanner); }
  G.netBanner.textContent = cachedAt
    ? `Нет связи с сервером. Показаны данные на ${fmtDateTime(Number(cachedAt))} — только для чтения. Как только связь появится, всё обновится само.`
    : 'Нет связи с сервером. Проверьте интернет — введённое не потеряно, действие можно повторить.';
}

export function relogin() {
  if (G.reloginPromise) return G.reloginPromise;
  G.reloginPromise = new Promise((resolve) => {
    const pass = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', placeholder: 'Пароль' });
    const err = h('div', { class: 'note bad', style: { display: 'none' } });
    const done = (ok) => { box.remove(); G.reloginPromise = null; resolve(ok); };
    const go = async () => {
      try {
        const res = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: state.me.email, password: pass.value }) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || 'Не получилось войти');
        store.set('token', data.token); done(true);
      } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
    };
    pass.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
    const box = h('div', { class: 'relogin-wrap' }, h('div', { class: 'relogin', role: 'dialog', 'aria-label': 'Сессия истекла' },
      h('h2', {}, 'Сессия истекла'), h('p', { class: 'muted small' }, `Введите пароль для ${state.me.email}, чтобы продолжить. Всё, что вы набрали на экране, сохранится.`), err, pass,
      h('div', { style: { display: 'flex', gap: '10px', marginTop: '12px' } }, h('button', { class: 'btn primary', onclick: go }, 'Продолжить'),
        h('span', { class: 'spacer' }), h('button', { class: 'btn ghost', onclick: () => done(false) }, 'Выйти'))));
    document.body.append(box);
    setTimeout(() => pass.focus(), 30);
  });
  return G.reloginPromise;
}

export async function api(method, path, body, retried = false) {
  const headers = { 'Content-Type': 'application/json' };
  const token = store.get('token');
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    setOffline(true);
    throw new ApiError(method === 'GET' ? 'Нет связи с сервером. Проверьте интернет' : 'Нет связи с сервером — действие не выполнено. Введённое осталось на экране: повторите, когда появится интернет', 0, {});
  }
  if (res.headers.get('X-From-Cache')) setOffline(true, res.headers.get('X-Cached-At')); else if (G.netBanner && res.ok) setOffline(false);
  const data = await res.json().catch(() => ({}));
  // 401 с полем (неверный текущий пароль и т. п.) — ошибка формы, а не конец сессии
  const sessionLost = res.status === 401 && token && !data.field && !path.startsWith('/api/auth/');
  if (sessionLost && !retried && state.me) {
    if (await relogin()) return api(method, path, body, true);
  }
  if (sessionLost) { hooks.logout(); }
  if (!res.ok) throw new ApiError(data.error || (res.status >= 500 ? 'Сервер не отвечает. Попробуйте через минуту — данные не потеряны' : `Ошибка ${res.status}`), res.status, data);
  return data;
}
export const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString();

// ---------- состояние и маршруты ----------
export const state = {
  me: null,
  propertyId: store.get('propertyId'),
  boardFrom: null,
  boardDays: parseInt(store.get('board_days', ''), 10) || (window.innerWidth < 860 ? 14 : 31),
  conflicts: 0, exportStale: 0, channelIssues: 0,
  requests: 0,
  tasks: 0,
  financeKind: store.get('finance_kind', 'expense'),
  bell: 0,
};

export const RANK = { landlord: -1, housekeeper: 0, manager: 1, owner: 2 };
export const can = (role) => state.me && RANK[state.me.role] >= RANK[role];
export function closeDrawer() { if (G.drawerEl) { G.drawerEl.remove(); G.drawerEl = null; G.drawerDirty = false; G.drawerOnDismiss = null; document.removeEventListener('keydown', escClose); } }
// Закрытие по желанию человека (крестик, фон, Esc, «Закрыть»): если в форме есть несохранённые правки — переспросить
export function requestCloseDrawer() {
  if (G.drawerDirty && !(G.drawerOnDismiss ? G.drawerOnDismiss() : confirm('У вас есть несохранённые изменения. Закрыть без сохранения?'))) return false;
  closeDrawer();
  return true;
}
export function escClose(e) { if (e.key === 'Escape') requestCloseDrawer(); }
// opts.guard — следить за несохранёнными правками; opts.onDismiss — свой вопрос при закрытии (true = закрывать)
export function openDrawer(title, body, foot, opts = {}) {
  closeDrawer();
  G.drawerDirty = false;
  G.drawerOnDismiss = opts.onDismiss || null;
  G.drawerEl = h('div', {},
    h('div', { class: 'drawer-back', onclick: requestCloseDrawer }),
    h('div', { class: 'drawer', role: 'dialog', 'aria-label': title },
      h('div', { class: 'drawer-head' }, h('h2', {}, title), h('button', { class: 'btn icon ghost', onclick: requestCloseDrawer, 'aria-label': 'Закрыть' }, icon('close'))),
      h('div', { class: 'drawer-body' }, body),
      foot ? h('div', { class: 'drawer-foot' }, foot) : null));
  if (opts.guard) {
    const mark = (e) => { if (!e.target.closest?.('.money-box')) G.drawerDirty = true; };
    G.drawerEl.addEventListener('input', mark);
    G.drawerEl.addEventListener('change', mark);
  }
  document.body.append(G.drawerEl);
  document.addEventListener('keydown', escClose);
  setTimeout(() => G.drawerEl?.querySelector('input:not([type=hidden]):not([readonly]), select')?.focus(), 50);
}

export function closeModal(dismissed = false) {
  if (!G.modalEl) return;
  const cb = dismissed ? G.modalOnDismiss : null;
  G.modalEl.remove(); G.modalEl = null; G.modalOnDismiss = null;
  document.removeEventListener('keydown', escModal);
  if (cb) cb();
}
export function escModal(e) { if (e.key === 'Escape') closeModal(true); }
export function openModal(title, body, foot, onDismiss) {
  closeModal();
  G.modalOnDismiss = onDismiss || null;
  G.modalEl = h('div', { class: 'modal-wrap' },
    h('div', { class: 'modal-back', onclick: () => closeModal(true) }),
    h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
      h('div', { class: 'modal-head' }, h('h2', {}, title)),
      h('div', { class: 'modal-body' }, body),
      foot ? h('div', { class: 'modal-foot' }, foot) : null));
  document.body.append(G.modalEl);
  document.addEventListener('keydown', escModal);
  if (!matchMedia('(pointer: coarse)').matches) setTimeout(() => G.modalEl?.querySelector('input:not([type=hidden]), select, button.primary')?.focus(), 50);
}

export async function copyText(text, okMsg = 'Скопировано') {
  try { await navigator.clipboard.writeText(text); toast(okMsg); }
  catch { toast('Не удалось скопировать — выделите текст и скопируйте вручную', true); }
}
// ---------- расходы ----------
export async function downloadCsv(path, filename) {
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

// ---------- профиль ----------
// Шапка печатных документов: знак, название объекта, адрес и телефон
export const letterhead = (name, line2) => h('div', { class: 'letterhead' }, h('span', { class: 'lh-mark' }, '◆'),
  h('div', {}, h('b', {}, name), line2 ? h('div', { class: 'lh-sub' }, line2) : null));

// Печать выбранного блока страницы: копия кладётся в #print-sheet, остальное приложение при печати скрыто
export function printNode(node) {
  document.getElementById('print-sheet')?.remove();
  const sheet = h('div', { id: 'print-sheet' }, node.cloneNode(true));
  document.body.append(sheet);
  window.addEventListener('afterprint', () => sheet.remove(), { once: true });
  window.print();
}

// Доступность: у каждого поля ввода должна быть подпись для экранного диктора. Если разработчик не дал aria-label,
// берём заголовок рядом (.field > span), подсказку внутри поля или текст перед полем. Срабатывает после любой перерисовки.
function nameField(el) {
  const near = el.closest('.field')?.querySelector(':scope > span')?.textContent
    || el.closest('label')?.textContent
    || el.previousElementSibling?.textContent
    || el.parentElement?.previousElementSibling?.textContent;
  return (el.getAttribute('placeholder') || el.title || near || '').trim().slice(0, 60);
}
function labelFields() {
  document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([aria-label]), select:not([aria-label]), textarea:not([aria-label])').forEach((el) => {
    if (el.closest('label') || el.getAttribute('aria-labelledby') || (el.id && document.querySelector(`label[for="${el.id}"]`))) return;
    el.setAttribute('aria-label', nameField(el) || (el.tagName === 'SELECT' ? 'Выбор' : 'Поле ввода'));
  });
}
let labelTimer = 0;
new MutationObserver(() => { clearTimeout(labelTimer); labelTimer = setTimeout(labelFields, 30); })
  .observe(document.body, { childList: true, subtree: true });
