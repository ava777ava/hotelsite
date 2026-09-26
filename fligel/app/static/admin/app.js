// Флигель — интерфейс администратора. Без сборки и зависимостей.

// ---------- утилиты ----------
const $app = document.getElementById('app');

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') el.innerHTML = v;
    else if (k in el && typeof v !== 'string') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
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
  download: '<path d="M12 3v13M7 11l5 5 5-5M4 20h16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
};
const icon = (name) => { const s = h('span'); s.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`; return s.firstChild; };

const WD = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const SOURCE = {
  manual: 'Вручную', direct: 'Сайт', avito: 'Авито', yandex: 'Яндекс', sutochno: 'Суточно', ostrovok: 'Островок', other: 'Другое',
};
const STATUS = { confirmed: 'Подтверждена', pending: 'Ждёт оплаты', blocked: 'Даты закрыты', cancelled: 'Отменена' };
const ROLE = { owner: 'Владелец', manager: 'Администратор', housekeeper: 'Горничная' };

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

function toast(msg, bad = false) {
  const t = h('div', { class: 'toast' + (bad ? ' bad' : '') }, msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), bad ? 5000 : 2800);
}

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
  boardDays: window.innerWidth < 860 ? 14 : 31,
  conflicts: 0,
};

const ROUTES = {
  board: { title: 'Шахматка', icon: 'board', view: viewBoard },
  today: { title: 'Сегодня', icon: 'today', view: viewToday },
  bookings: { title: 'Брони', icon: 'list', view: viewBookings, role: 'manager' },
  rates: { title: 'Цены', icon: 'rates', view: viewRates, role: 'manager' },
  channels: { title: 'Площадки', icon: 'channels', view: viewChannels, role: 'manager' },
  expenses: { title: 'Расходы', icon: 'expenses', view: viewExpenses, role: 'manager' },
  stats: { title: 'Отчёты', icon: 'stats', view: viewStats, role: 'manager' },
  settings: { title: 'Настройки', icon: 'settings', view: viewSettings, role: 'owner' },
};
const RANK = { housekeeper: 0, manager: 1, owner: 2 };
const MOBILE_ORDER = ['board', 'today', 'bookings', 'expenses', 'channels', 'settings', 'rates', 'stats'];
const can = (role) => state.me && RANK[state.me.role] >= RANK[role];
const currentRoute = () => { const r = location.hash.replace(/^#\/?/, '').split('?')[0] || 'board'; return ROUTES[r] ? r : 'board'; };

window.addEventListener('hashchange', () => render());

async function boot() {
  if (store.get('token')) {
    try { state.me = await api('GET', '/api/me'); } catch { state.me = null; }
  }
  render();
}

function render() {
  closeDrawer();
  $app.innerHTML = '';
  if (!state.me) return $app.append(viewAuth());
  if (!state.me.properties.length) return $app.append(viewWizard());
  if (!state.me.properties.find((p) => p.id === state.propertyId)) state.propertyId = state.me.properties[0].id;
  const route = currentRoute();
  const def = ROUTES[route];
  const main = h('main', { class: 'main' });
  $app.append(layout(route, main));
  if (def.role && !can(def.role)) {
    main.append(h('div', { class: 'card empty' }, h('h3', {}, 'Раздел недоступен'), 'Попросите владельца расширить ваши права.'));
    return;
  }
  def.view(main);
}

function layout(route, main) {
  const visible = Object.entries(ROUTES).filter(([, d]) => !d.role || can(d.role));
  const link = ([key, d]) => h('a', { href: `#/${key}`, class: key === route ? 'active' : '' }, icon(d.icon), h('span', {}, d.title),
    key === 'channels' && state.conflicts ? h('span', { class: 'badge' }, state.conflicts) : null);
  const prop = state.me.properties.find((p) => p.id === state.propertyId);
  return h('div', { class: 'shell' },
    h('aside', { class: 'side' },
      h('div', { class: 'brand' }, h('div', { class: 'brand-mark' }),
        h('div', {}, h('div', { class: 'brand-name' }, 'Флигель'),
        propertySwitcher('prop-switch') || h('div', { class: 'brand-sub' }, prop ? prop.name : ''))),
      h('nav', { class: 'nav' }, visible.map(link)),
      h('div', { class: 'side-foot' }, h('b', {}, state.me.name), ROLE[state.me.role],
        h('br'), h('button', { onclick: logout }, 'Выйти'))),
    h('div', {},
      h('div', { class: 'mobile-top' }, h('div', { class: 'brand-mark' }),
        propertySwitcher('prop-switch') || h('div', { class: 'brand-name' }, prop ? prop.name : 'Флигель'),
        h('button', { class: 'btn small ghost', style: { marginLeft: 'auto', color: '#fff' }, onclick: logout }, 'Выйти')),
      main),
    h('nav', { class: 'mobile-nav' }, MOBILE_ORDER.map((k) => visible.find(([v]) => v === k)).filter(Boolean).slice(0, 5).map(link)));
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
  const btnCurrent = h('button', {
    type: 'button', class: scope.value === 'current' ? 'on' : '',
    onclick: () => { scope.value = 'current'; btnCurrent.classList.add('on'); btnAll.classList.remove('on'); onChange(); },
  }, 'Этот объект');
  const btnAll = h('button', {
    type: 'button', class: scope.value === 'all' ? 'on' : '',
    onclick: () => { scope.value = 'all'; btnAll.classList.add('on'); btnCurrent.classList.remove('on'); onChange(); },
  }, 'Все объекты');
  return h('div', { class: 'seg' }, btnCurrent, btnAll);
}

// ---------- вход и регистрация ----------
function viewAuth() {
  let mode = 'login';
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
          location.hash = '#/board';
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
    h('div', { class: 'switch' }, mode === 'login' ? 'Ещё нет аккаунта? ' : 'Уже есть аккаунт? ',
      h('button', { type: 'button', onclick: () => { mode = mode === 'login' ? 'register' : 'login'; draw(); } },
        mode === 'login' ? 'Зарегистрироваться' : 'Войти')));
    formBox.append(h('div', {}, h('div', { class: 'brand auth-mobile-brand' }, h('div', { class: 'brand-mark' }), h('div', { class: 'brand-name' }, 'Флигель')), form));
  };
  draw();
  wrap.append(art, formBox);
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
        h('button', { class: 'btn icon ghost del', type: 'button', title: 'Убрать категорию', style: { marginBottom: '10px' }, disabled: types.length === 1,
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
function closeDrawer() { if (drawerEl) { drawerEl.remove(); drawerEl = null; document.removeEventListener('keydown', escClose); } }
function escClose(e) { if (e.key === 'Escape') closeDrawer(); }
function openDrawer(title, body, foot) {
  closeDrawer();
  drawerEl = h('div', {},
    h('div', { class: 'drawer-back', onclick: closeDrawer }),
    h('div', { class: 'drawer', role: 'dialog', 'aria-label': title },
      h('div', { class: 'drawer-head' }, h('h2', {}, title), h('button', { class: 'btn icon ghost', onclick: closeDrawer, 'aria-label': 'Закрыть' }, icon('close'))),
      h('div', { class: 'drawer-body' }, body),
      foot ? h('div', { class: 'drawer-foot' }, foot) : null));
  document.body.append(drawerEl);
  document.addEventListener('keydown', escClose);
  setTimeout(() => drawerEl?.querySelector('input:not([type=hidden]):not([readonly]), select')?.focus(), 50);
}

// ---------- шахматка ----------
let boardData = null;

async function viewBoard(main) {
  if (!state.boardFrom) state.boardFrom = addDays(todayISO(), -2);
  const head = h('div', { class: 'page-head' }, h('h1', {}, 'Шахматка'));
  const tools = h('div', { class: 'board-tools' },
    h('button', { class: 'btn icon', title: 'Раньше', onclick: () => shift(-7) }, icon('left')),
    h('button', { class: 'btn', onclick: () => { state.boardFrom = addDays(todayISO(), -2); load(); } }, 'Сегодня'),
    h('button', { class: 'btn icon', title: 'Позже', onclick: () => shift(7) }, icon('right')),
    h('input', { class: 'input', type: 'date', style: { width: '150px' }, value: state.boardFrom, onchange: (e) => { if (e.target.value) { state.boardFrom = e.target.value; load(); } } }),
    can('manager') ? h('button', { class: 'btn primary', onclick: () => bookingDrawer({}) }, icon('plus'), 'Бронь') : null);
  head.append(tools);
  const banner = h('div');
  const card = h('div', { class: 'card board-card' }, h('div', { class: 'empty' }, 'Загружаю…'));
  main.append(head, banner, card);

  const shift = (n) => { state.boardFrom = addDays(state.boardFrom, n); load(); };
  const load = async () => {
    try {
      boardData = await api('GET', '/api/board?' + qs({ property_id: state.propertyId, from: state.boardFrom, days: state.boardDays }));
      state.conflicts = boardData.open_conflicts;
      banner.innerHTML = '';
      if (boardData.open_conflicts) {
        banner.append(h('div', { class: 'banner' }, h('b', {}, '!'),
          h('div', {}, `С площадок пришли брони на уже занятые даты: ${boardData.open_conflicts}. `,
            h('a', { href: '#/channels' }, 'Разобрать конфликты'))));
      }
      card.innerHTML = '';
      card.append(drawBoard(boardData, load));
    } catch (ex) { card.innerHTML = ''; card.append(h('div', { class: 'empty' }, ex.message)); }
  };
  load();
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
    return c.join(' ');
  };
  const board = h('div', { class: 'board' });
  // заголовок с датами
  const headRow = h('div', { class: 'b-row b-head' }, h('div', { class: 'b-side' }, 'Номер'));
  days.forEach((d, i) => {
    const dt = parseISO(d);
    headRow.append(h('div', { class: 'b-day ' + dayClass(d, i) },
      dt.getDate() === 1 || i === 0 ? h('span', { class: 'b-month' }, MONTHS_SHORT[dt.getMonth()]) : null,
      h('span', { class: 'n' }, dt.getDate()), h('span', { class: 'w' }, WD[dt.getDay()])));
  });
  board.append(headRow);

  const byRoom = {};
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
        title: `${fmtDate(d)}: ${fmtMoney(price)}${rate?.min_stay ? `, от ${rate.min_stay} ноч.` : ''}${rate?.closed ? ', продажи закрыты' : ''}. Свободно: ${free}`,
        onclick: () => can('manager') && rateDrawer(t, d, reload),
      }, fmtPriceCell(price), h('span', { class: 'free' + (free <= 0 ? ' zero' : '') }, free)));
    });
    board.append(typeRow);

    t.rooms.forEach((room) => {
      const track = h('div', { class: 'b-track' });
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
        const bar = h('div', {
          class: `bar ${b.status}${cutL ? ' cut-left' : ''}${cutR ? ' cut-right' : ''}`,
          style: { left: `${left + 2}px`, width: `${Math.max(right - left - 4, 12)}px`, background: `var(--src-${b.source})` },
          title: `${label} · ${SOURCE[b.source]} · ${STATUS[b.status]}\n${fmtDate(b.check_in)} — ${fmtDate(b.check_out)}, ${nights} ${nightsWord(nights)}`,
          onpointerdown: (ev) => ev.stopPropagation(),
          onclick: () => bookingDrawer(b, reload),
        }, h('span', { class: 'ttl' }, label),
        b.status !== 'blocked' && b.guest_name && right - left > 120 ? h('span', { class: 'src' }, SOURCE[b.source]) : null);
        track.append(bar);
      });
      board.append(h('div', { class: 'b-row b-room' },
        h('div', { class: 'b-side' }, h('span', {}, room.name), h('span', { class: 'rt' }, t.name)), track));
    });
  });

  if (!data.room_types.length) board.append(h('div', { class: 'empty' }, 'Номеров пока нет. Добавьте их в настройках.'));

  const legend = h('div', { class: 'legend' },
    ['direct', 'manual', 'avito', 'yandex', 'sutochno', 'ostrovok'].map((s) => h('span', {}, h('i', { class: 'dot', style: { background: `var(--src-${s})` } }), SOURCE[s])),
    h('span', {}, h('i', { class: 'dot', style: { background: 'repeating-linear-gradient(135deg,#9AA296 0 3px,#C9CEC5 3px 6px)' } }), 'Даты закрыты'),
    h('span', {}, 'Штриховка — ждёт оплаты'),
    can('manager') ? h('span', { style: { marginLeft: 'auto' } }, 'Протяните по свободным клеткам, чтобы создать бронь') : null);
  const scroll = h('div', { class: 'board-scroll' }, board);
  // прокрутить к сегодняшнему дню на узких экранах
  requestAnimationFrame(() => {
    const idx = days.indexOf(today);
    if (idx > 2 && scroll.scrollLeft === 0) scroll.scrollLeft = (idx - 1) * cellW;
  });
  return h('div', {}, scroll, legend);
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

async function bookingDrawer(b, onSaved) {
  await ensureBoardData();
  const isNew = !b.id;
  const imported = !!b.feed_id;
  const readOnly = !can('manager');
  const rooms = allRooms();
  const f = {};
  let priceTouched = !isNew;
  const status = { value: b.status || 'confirmed' };
  const note = h('div', { class: 'note', style: { display: 'none' } });
  const totalEl = h('b');
  const nightsEl = h('span', { class: 'muted' });

  const inp = (key, label, attrs = {}) => h('label', { class: 'field' }, h('span', {}, label),
    f[key] = h('input', { class: 'input', value: b[key] ?? '', disabled: readOnly, ...attrs }));

  const statusSeg = h('div', { class: 'seg', style: { marginBottom: '14px', width: '100%' } });
  const guestBox = h('div');
  const drawSeg = () => {
    statusSeg.innerHTML = '';
    [['confirmed', 'Подтверждена'], ['pending', 'Ждёт оплаты'], ['blocked', 'Закрыть даты']].forEach(([k, l]) => {
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
  f.notes = h('textarea', { class: 'input', disabled: readOnly }, b.notes || '');

  let quoteTimer;
  async function requote() {
    clearTimeout(quoteTimer);
    quoteTimer = setTimeout(async () => {
      if (!f.check_in.value || !f.check_out.value || f.check_out.value <= f.check_in.value) return;
      try {
        const q = await api('GET', '/api/bookings/quote?' + qs({ room_id: f.room_id.value, check_in: f.check_in.value, check_out: f.check_out.value, exclude: b.id }));
        nightsEl.textContent = `${q.nights} ${nightsWord(q.nights)}, ${fmtDate(f.check_in.value)} — ${fmtDate(f.check_out.value)}`;
        if (!priceTouched && status.value !== 'blocked') f.total_price.value = Math.round(q.total);
        updateTotal();
        const warn = [];
        if (q.busy) warn.push(q.busy);
        if (q.closed_dates.length && status.value !== 'blocked') warn.push('Продажи на часть дат закрыты');
        if (q.nights < q.min_stay && status.value !== 'blocked') warn.push(`Минимальный срок — ${q.min_stay} ${nightsWord(q.min_stay)}`);
        if (warn.length) { note.className = 'note bad'; note.textContent = warn.join('. '); note.style.display = ''; }
        else if (!imported) note.style.display = 'none';
      } catch { /* покажем при сохранении */ }
    }, 200);
  }
  const updateTotal = () => {
    const total = Number(f.total_price.value || 0); const paid = Number(f.paid_amount.value || 0);
    totalEl.textContent = fmtMoney(total);
    totalEl.title = paid ? `Оплачено ${fmtMoney(paid)}, к оплате ${fmtMoney(total - paid)}` : '';
  };

  if (imported) {
    note.className = 'note';
    note.textContent = `Бронь пришла с площадки «${SOURCE[b.source]}» через синхронизацию календаря. Даты и номер меняются на самой площадке. Имя гостя, телефон и сумму можно дописать здесь.`;
    note.style.display = '';
  }

  const body = h('div', {},
    note,
    statusSeg,
    h('label', { class: 'field' }, h('span', {}, 'Номер'), f.room_id),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Заезд'), f.check_in), h('label', { class: 'field' }, h('span', {}, 'Выезд'), f.check_out)),
    guestBox,
    h('label', { class: 'field' }, h('span', {}, 'Комментарий'), f.notes));
  guestBox.append(
    inp('guest_name', 'Гость', { autocomplete: 'off', placeholder: 'Имя и фамилия' }),
    h('div', { class: 'row2' }, inp('guest_phone', 'Телефон', { type: 'tel', placeholder: '+7' }), inp('guest_email', 'Email', { type: 'email' })),
    h('div', { class: 'row3' },
      inp('guests_count', 'Гостей', { type: 'number', min: 1, value: b.guests_count || 1 }),
      inp('total_price', 'Стоимость, ₽', { type: 'number', min: 0, value: b.total_price != null ? Math.round(b.total_price) : '', oninput: () => { priceTouched = true; updateTotal(); } }),
      inp('paid_amount', 'Оплачено, ₽', { type: 'number', min: 0, value: b.paid_amount != null ? Math.round(b.paid_amount) : 0, oninput: updateTotal })),
    h('label', { class: 'field' }, h('span', {}, 'Источник'), f.source),
    h('div', { class: 'summary' }, nightsEl, totalEl));
  guestBox.style.display = status.value === 'blocked' ? 'none' : '';

  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true;
    const payload = {
      room_id: f.room_id.value, check_in: f.check_in.value, check_out: f.check_out.value, status: status.value,
      notes: f.notes.value,
    };
    if (status.value !== 'blocked') Object.assign(payload, {
      guest_name: f.guest_name.value, guest_phone: f.guest_phone.value, guest_email: f.guest_email.value,
      guests_count: f.guests_count.value || 1, total_price: f.total_price.value, paid_amount: f.paid_amount.value || 0, source: f.source.value,
    });
    if (imported) { delete payload.room_id; delete payload.check_in; delete payload.check_out; delete payload.source; }
    try {
      if (isNew) await api('POST', '/api/bookings', payload);
      else await api('PATCH', `/api/bookings/${b.id}`, payload);
      toast(isNew ? (status.value === 'blocked' ? 'Даты закрыты' : 'Бронь создана') : 'Изменения сохранены');
      closeDrawer(); onSaved ? onSaved() : render();
    } catch (ex) {
      note.className = 'note bad'; note.textContent = ex.message; note.style.display = '';
      if (ex.data?.field && f[ex.data.field]) f[ex.data.field].classList.add('invalid');
    } finally { save.disabled = false; }
  } }, isNew ? 'Создать' : 'Сохранить');

  const remove = !isNew && can('manager') ? h('button', { class: 'btn danger ghost', onclick: async () => {
    const blocked = b.status === 'blocked' && !imported;
    if (!confirm(blocked ? 'Открыть эти даты для продажи?' : 'Отменить бронь? Номер освободится на всех площадках при следующей синхронизации.')) return;
    try { await api('DELETE', `/api/bookings/${b.id}`); toast(blocked ? 'Даты открыты' : 'Бронь отменена'); closeDrawer(); onSaved ? onSaved() : render(); }
    catch (ex) { toast(ex.message, true); }
  } }, b.status === 'blocked' && !imported ? 'Открыть даты' : 'Отменить бронь') : null;

  const title = isNew ? 'Новая бронь' : (b.status === 'blocked' ? 'Закрытые даты' : (b.guest_name || `Бронь ${SOURCE[b.source]}`));
  openDrawer(title, body, readOnly ? null : [remove, h('span', { class: 'spacer' }), h('button', { class: 'btn foot-close', onclick: closeDrawer }, 'Закрыть'), save]);
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
  f.price = h('input', { class: 'input', type: 'number', min: 0, value: rate.price != null ? Math.round(rate.price) : '', placeholder: `Базовая: ${Math.round(t.base_price)}` });
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

// ---------- сегодня ----------
async function viewToday(main) {
  let day = todayISO();
  const scope = { value: 'current' };
  const content = h('div');
  const dateInput = h('input', { class: 'input', type: 'date', value: day, style: { width: '160px' }, onchange: (e) => { day = e.target.value || todayISO(); load(); } });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Заезды и выезды'),
    h('button', { class: 'btn icon', onclick: () => { day = addDays(day, -1); dateInput.value = day; load(); } }, icon('left')),
    dateInput,
    h('button', { class: 'btn icon', onclick: () => { day = addDays(day, 1); dateInput.value = day; load(); } }, icon('right')),
    scopeSeg(scope, () => load())), content);
  const item = (b, kind) => {
    const due = Number(b.total_price) - Number(b.paid_amount);
    return h('div', { class: 'item', onclick: () => bookingDrawer(b, load) },
      h('div', { class: 'room-chip' }, b.room_name),
      h('div', { style: { flex: 1, minWidth: 0 } },
        h('div', { style: { fontWeight: 600 } }, b.guest_name || `Гость с площадки ${SOURCE[b.source]}`,
          scope.value === 'all' ? h('span', { class: 'muted small', style: { fontWeight: 400 } }, ' · ', b.property_name) : null),
        h('div', { class: 'muted small' }, `${fmtShort(b.check_in)} — ${fmtShort(b.check_out)} · ${b.guests_count} гост. · ${SOURCE[b.source]}`,
          b.guest_phone ? [' · ', h('a', { href: `tel:${b.guest_phone}`, onclick: (e) => e.stopPropagation() }, b.guest_phone)] : null)),
      kind !== 'staying' && due > 0 && can('manager') ? h('span', { class: 'pill warn num' }, `к оплате ${fmtMoney(due)}`) : null,
      b.status === 'pending' ? h('span', { class: 'pill warn' }, 'ждёт оплаты') : null);
  };
  const block = (title, list, kind, emptyText) => h('div', { class: 'card' },
    h('div', { class: 'card-head' }, h('h2', {}, title), h('span', { class: 'pill none num' }, list.length)),
    list.length ? h('div', { class: 'day-list' }, list.map((b) => item(b, kind))) : h('div', { class: 'empty' }, emptyText));
  const load = async () => {
    try {
      const d = await api('GET', '/api/today?' + qs({ date: day, property_id: scope.value === 'current' ? state.propertyId : undefined }));
      content.innerHTML = '';
      content.append(
        h('p', { class: 'muted', style: { marginTop: '-6px' } }, `${fmtDate(day)}, ${WD[parseISO(day).getDay()].toLowerCase()}`),
        h('div', { class: 'grid-2' },
          block('Заезды', d.arrivals, 'in', 'Заездов нет'),
          block('Выезды', d.departures, 'out', 'Выездов нет'),
          block('Проживают', d.staying, 'staying', 'Сейчас никто не проживает')));
    } catch (ex) { content.innerHTML = ''; content.append(h('div', { class: 'card empty' }, ex.message)); }
  };
  load();
}

// ---------- список броней ----------
async function viewBookings(main) {
  const scope = { value: 'current' };
  const f = {
    q: h('input', { class: 'input', placeholder: 'Имя, телефон или email', style: { width: '240px' } }),
    from: h('input', { class: 'input', type: 'date', value: addDays(todayISO(), -7), style: { width: '150px' } }),
    to: h('input', { class: 'input', type: 'date', value: addDays(todayISO(), 60), style: { width: '150px' } }),
    status: h('select', { class: 'input', style: { width: '170px' } }, h('option', { value: '' }, 'Все активные'),
      Object.entries(STATUS).map(([k, l]) => h('option', { value: k }, l))),
  };
  const table = h('div', { class: 'card' });
  let timer;
  Object.values(f).forEach((el) => el.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 250); }));
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Брони'),
    h('button', { class: 'btn primary', onclick: () => bookingDrawer({}, load) }, icon('plus'), 'Бронь')),
  h('div', { class: 'board-tools', style: { marginBottom: '14px' } }, f.q, f.from, '—', f.to, f.status, scopeSeg(scope, () => load())), table);
  async function load() {
    try {
      const rows = await api('GET', '/api/bookings?' + qs({
        q: f.q.value, from: f.from.value, to: f.to.value, status: f.status.value,
        property_id: scope.value === 'current' ? state.propertyId : undefined,
      }));
      table.innerHTML = '';
      if (!rows.length) { table.append(h('div', { class: 'empty' }, h('h3', {}, 'Броней не найдено'), 'Измените период или поиск.')); return; }
      table.append(h('div', { class: 'table-wrap' }, h('table', { class: 'list' },
        h('thead', {}, h('tr', {}, [scope.value === 'all' ? 'Объект' : null, 'Заезд', 'Выезд', 'Номер', 'Гость', 'Источник', 'Статус', 'Сумма', 'Оплачено'].filter(Boolean).map((t) => h('th', {}, t)))),
        h('tbody', {}, rows.map((b) => h('tr', { class: 'click', onclick: () => bookingDrawer(b, load) },
          scope.value === 'all' ? h('td', { class: 'muted small' }, b.property_name) : null,
          h('td', { class: 'num' }, fmtShort(b.check_in)), h('td', { class: 'num' }, fmtShort(b.check_out)),
          h('td', { class: 'num' }, b.room_name),
          h('td', {}, b.status === 'blocked' ? h('span', { class: 'muted' }, 'Закрыто') : (b.guest_name || h('span', { class: 'muted' }, '—')),
            b.guest_phone ? h('div', { class: 'muted small' }, b.guest_phone) : null),
          h('td', {}, h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: '6px' } }, h('i', { class: 'dot', style: { background: `var(--src-${b.source})` } }), SOURCE[b.source])),
          h('td', {}, h('span', { class: 'pill ' + ({ confirmed: 'ok', pending: 'warn', blocked: 'none', cancelled: 'bad' }[b.status]) }, STATUS[b.status])),
          h('td', { class: 'num' }, b.status === 'blocked' ? '' : fmtMoney(b.total_price)),
          h('td', { class: 'num' }, b.status === 'blocked' ? '' : fmtMoney(b.paid_amount))))))));
    } catch (ex) { table.innerHTML = ''; table.append(h('div', { class: 'empty' }, ex.message)); }
  }
  load();
}

// ---------- цены ----------
async function viewRates(main) {
  const content = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Цены и ограничения')), content);
  const prop = await api('GET', `/api/properties/${state.propertyId}`);
  const f = { types: {}, days: {} };
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  f.from = h('input', { class: 'input', type: 'date', value: todayISO() });
  f.to = h('input', { class: 'input', type: 'date', value: addDays(todayISO(), 30) });
  f.price = h('input', { class: 'input', type: 'number', min: 0, placeholder: 'Не менять' });
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
  content.append(h('div', { class: 'card card-pad' },
    h('h2', { style: { marginBottom: '14px' } }, 'Изменить сразу на период'), err,
    h('div', { class: 'field' }, h('span', {}, 'Категории'), h('div', { style: { display: 'flex', gap: '16px', flexWrap: 'wrap' } },
      prop.room_types.map((t) => h('label', { class: 'check' }, f.types[t.id] = h('input', { type: 'checkbox', checked: true }), `${t.name} (${t.rooms.length})`)))),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'С'), f.from), h('label', { class: 'field' }, h('span', {}, 'По (включительно)'), f.to)),
    h('div', { class: 'field' }, h('span', {}, 'Дни недели'), h('div', {}, daySeg)),
    h('div', { class: 'row3' }, h('label', { class: 'field' }, h('span', {}, 'Цена за ночь, ₽'), f.price), h('label', { class: 'field' }, h('span', {}, 'Минимум ночей'), f.min), h('label', { class: 'field' }, h('span', {}, 'Продажи'), f.closed)),
    h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap' } },
      h('button', { class: 'btn primary', onclick: () => send(false) }, 'Применить'),
      h('button', { class: 'btn ghost', onclick: () => confirm('Вернуть базовые цены и снять ограничения на выбранный период?') && send(true) }, 'Сбросить к базовым')),
    h('p', { class: 'muted small', style: { marginBottom: 0 } }, 'Пример: выходные подороже — оставьте только Пт и Сб и укажите цену. Базовые цены категорий — в настройках.')),
  preview);
  async function drawPreview() {
    const data = await api('GET', '/api/board?' + qs({ property_id: state.propertyId, from: todayISO(), days: 21 }));
    preview.innerHTML = '';
    preview.append(h('div', { class: 'card-head' }, h('h2', {}, 'Ближайшие 3 недели'), h('span', { class: 'muted small' }, 'нажмите на цену, чтобы поменять одну дату')),
      h('div', { class: 'table-wrap' }, h('div', { class: 'board', style: { minWidth: 'max-content' } },
        h('div', { class: 'b-row b-head', style: { position: 'static' } }, h('div', { class: 'b-side' }, 'Категория'),
          data.days.map((d) => { const dt = parseISO(d); return h('div', { class: 'b-day' + ((dt.getDay() % 6 === 0) ? ' we' : '') }, h('span', { class: 'n' }, dt.getDate()), h('span', { class: 'w' }, WD[dt.getDay()])); })),
        data.room_types.map((t) => h('div', { class: 'b-row b-type' }, h('div', { class: 'b-side' }, t.name),
          data.days.map((d) => { const r = t.rates[d]; return h('div', { class: 'b-price' + (r?.price != null ? ' custom' : '') + (r?.closed ? ' closed' : ''), title: r?.min_stay ? `от ${r.min_stay} ноч.` : '', onclick: () => rateDrawer(t, d, drawPreview) }, fmtPriceCell(r?.price ?? t.base_price)); }))))));
  }
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
      h('td', {}, level === 'type'
        ? [h('b', {}, item.name), h('div', { class: 'muted small' }, `${item.rooms_count} ${item.rooms_count === 1 ? 'номер' : 'номеров'}`)]
        : [h('b', { class: 'num' }, item.name), h('div', { class: 'muted small' }, item.room_type)]),
      h('td', { class: 'ch-cell' },
        h('div', { class: 'copy-line' }, h('input', { class: 'input', readonly: true, value: ch.export_url, onclick: (e) => e.target.select() }),
          h('button', { class: 'btn small icon', title: 'Копировать', onclick: () => copy(ch.export_url) }, icon('copy'))),
        h('div', { class: 'muted small', style: { marginTop: '4px' } }, 'площадка забирала: ', ago(ch.export_last_fetched_at)),
        modeSel),
      h('td', { class: 'ch-cell' }, h('div', { class: 'copy-line' }, input, saveBtn),
        feed?.last_status === 'error' ? h('div', { class: 'small', style: { color: 'var(--clay)', marginTop: '4px' } }, feed.last_error) : null),
      h('td', {}, h('div', { class: 'state' }, status),
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
      h('div', { class: 'card' }, h('div', { class: 'table-wrap' }, h('table', { class: 'list ch-table' },
        h('thead', {}, h('tr', {}, [level === 'type' ? 'Категория' : 'Номер', 'Ссылка для площадки (наш календарь)', 'Ссылка с площадки (их календарь)', 'Состояние'].map((t) => h('th', {}, t)))),
        h('tbody', {}, items.map((it) => row(it, level, data.labels)))))));
  }
  load().catch((ex) => content.append(h('div', { class: 'card empty' }, ex.message)));
}

// ---------- отчёты: графики (свой SVG, без библиотек) ----------
function svgEl(markup) {
  const wrap = document.createElement('div');
  wrap.innerHTML = markup.trim();
  return wrap.firstChild;
}

const CHART_COLORS = ['#2F5D50', '#B7791F', '#6E4A93', '#23767E', '#B4562E', '#4A5A6A', '#5E6B5A', '#7A3418', '#8A5A12', '#69755F'];

function monthlyChart(monthly) {
  const W = 720, H = 220, padL = 0, padB = 24, plotH = H - padB;
  const vals = monthly.flatMap((m) => [Number(m.revenue), Number(m.expenses), Math.abs(Number(m.profit))]);
  const max = Math.max(1, ...vals);
  const n = monthly.length;
  const colW = (W - padL) / n;
  const barW = Math.min(16, colW * 0.32);
  let bars = '';
  let points = '';
  monthly.forEach((m, i) => {
    const cx = padL + colW * (i + 0.5);
    const rev = Number(m.revenue), exp = Number(m.expenses), profit = Number(m.profit);
    const revH = (rev / max) * plotH, expH = (exp / max) * plotH;
    bars += `<rect x="${cx - barW - 2}" y="${plotH - revH}" width="${barW}" height="${revH}" fill="${CHART_COLORS[0]}" rx="2"/>`;
    bars += `<rect x="${cx + 2}" y="${plotH - expH}" width="${barW}" height="${expH}" fill="${CHART_COLORS[4]}" rx="2"/>`;
    const py = Math.max(-20, Math.min(plotH, plotH - (profit / max) * plotH));
    points += `${cx},${py} `;
    const dt = parseISO(m.month + '-01');
    bars += `<text x="${cx}" y="${H - 6}" font-size="10.5" fill="var(--muted)" text-anchor="middle">${MONTHS_SHORT[dt.getMonth()]}</text>`;
  });
  return svgEl(`<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;display:block;overflow:visible">
    <line x1="0" y1="${plotH}" x2="${W}" y2="${plotH}" stroke="var(--border)"/>
    ${bars}
    <polyline points="${points.trim()}" fill="none" stroke="${CHART_COLORS[1]}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`);
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
    circles += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${x.color}" stroke-width="22"` +
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

function kpiCard(label, value, unit, compare) {
  const v = h('div', { class: 'v' }, value, unit ? h('small', {}, ` ${unit}`) : null);
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
  let current = 0;
  const custom = { from: addDays(t, -30), to: t };
  const scope = { value: 'current' };
  const content = h('div', { class: 'stack' });
  const customBox = h('div', { class: 'board-tools', style: { display: 'none' } });
  const seg = h('div', { class: 'seg', style: { flexWrap: 'wrap' } });
  const drawSeg = () => {
    seg.innerHTML = '';
    periods.forEach(([l], i) => seg.append(h('button', { class: i === current ? 'on' : '', onclick: () => { current = i; drawSeg(); customBox.style.display = i === periods.length - 1 ? 'flex' : 'none'; if (i !== periods.length - 1) load(); } }, l)));
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
      kpiCard('Выручка', money(tt.revenue), null, { period: cmp.period.revenue_delta, year: cmp.year.revenue_delta }),
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
      h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, 'Выручка, расходы и прибыль по месяцам'),
        monthlyChart(r.monthly),
        h('div', { class: 'legend', style: { padding: '10px 0 0', border: 0 } },
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[0] } }), 'Выручка'),
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[4] } }), 'Расходы'),
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[1] } }), 'Прибыль (линия)'))),
      h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, 'Загрузка по дням недели'),
        weekdayChart(r.weekday_occupancy)));
    content.append(chartsRow);

    const expenseCard = h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, 'Структура расходов'));
    if (r.by_expense_category.length) {
      const donutBox = h('div', { style: { display: 'flex', gap: '20px', alignItems: 'center', flexWrap: 'wrap' } });
      donutBox.append(expenseDonut(r.by_expense_category),
        h('div', { style: { flex: 1, minWidth: '220px' } }, r.by_expense_category.map((x) => h('div', {
          style: { display: 'flex', justifyContent: 'space-between', gap: '10px', padding: '4px 0' },
        }, h('span', {}, h('i', { class: 'dot', style: { background: x.color } }), ' ', x.name), h('b', { class: 'num' }, money(x.amount))))));
      expenseCard.append(donutBox);
    } else {
      expenseCard.append(h('div', { class: 'empty' }, 'Расходов за период нет'));
    }
    content.append(expenseCard);

    if (r.by_property && r.by_property.length) {
      content.append(h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', {}, 'По объектам')),
        h('table', { class: 'list' },
          h('thead', {}, h('tr', {}, ['Объект', 'Номеров', 'Выручка', 'Расходы', 'Прибыль', 'Загрузка'].map((x) => h('th', {}, x)))),
          h('tbody', {}, r.by_property.map((p) => h('tr', {},
            h('td', {}, p.property_name), h('td', { class: 'num' }, p.rooms),
            h('td', { class: 'num' }, money(p.revenue)), h('td', { class: 'num' }, money(p.expenses)),
            h('td', { class: 'num' }, money(p.profit)), h('td', { class: 'num' }, `${String(p.occupancy).replace('.', ',')}%`)))))));
    }

    if (r.by_room_type.length) {
      content.append(h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', {}, 'По категориям номеров')),
        h('table', { class: 'list' },
          h('thead', {}, h('tr', {}, ['Категория', 'Номеров', 'Ночей', 'Выручка'].map((x) => h('th', {}, x)))),
          h('tbody', {}, r.by_room_type.map((x) => h('tr', {},
            h('td', {}, x.room_type_name), h('td', { class: 'num' }, x.rooms),
            h('td', { class: 'num' }, x.nights), h('td', { class: 'num' }, money(x.revenue))))))));
    }

    let roomSort = { key: 'revenue', dir: -1 };
    const roomCard = h('div', { class: 'card' });
    const drawRoomTable = () => {
      const rows = [...r.by_room].sort((a, b) => (a[roomSort.key] > b[roomSort.key] ? 1 : a[roomSort.key] < b[roomSort.key] ? -1 : 0) * roomSort.dir);
      const th = (key, label) => h('th', { style: { cursor: 'pointer' }, onclick: () => { roomSort.dir = roomSort.key === key ? -roomSort.dir : -1; roomSort.key = key; drawRoomTable(); } },
        label, roomSort.key === key ? (roomSort.dir === -1 ? ' ↓' : ' ↑') : '');
      roomCard.innerHTML = '';
      roomCard.append(h('div', { class: 'card-head' }, h('h2', {}, 'По номерам'), h('span', { class: 'muted small' }, 'нажмите на заголовок для сортировки')),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' },
          h('thead', {}, h('tr', {}, th('room_name', 'Номер'), th('room_type_name', 'Категория'),
            state.me.properties.length > 1 ? th('property_name', 'Объект') : null, th('nights', 'Ночей продано'),
            th('occupancy', 'Загрузка'), th('revenue', 'Выручка'))),
          h('tbody', {}, rows.map((x) => h('tr', {},
            h('td', {}, x.room_name), h('td', { class: 'muted small' }, x.room_type_name),
            state.me.properties.length > 1 ? h('td', { class: 'muted small' }, x.property_name) : null,
            h('td', { class: 'num' }, x.nights), h('td', { class: 'num' }, `${String(x.occupancy).replace('.', ',')}%`),
            h('td', { class: 'num' }, money(x.revenue))))))));
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
      return h('tr', {}, h('td', {}, label), h('td', { class: 'num' }, x.bookings), h('td', { class: 'num' }, x.nights),
        h('td', { class: 'num' }, money(x.revenue)), h('td', { class: 'num muted small' }, commission),
        h('td', { class: 'num' }, money(x.net_revenue)), h('td', { style: { width: '25%' } }, bar));
    };
    const sourceHead = h('thead', {}, h('tr', {}, ['Источник', 'Броней', 'Ночей', 'Выручка', 'Комиссия', 'Чистая выручка', ''].map((x) => h('th', {}, x))));
    const sourceBody = r.by_source.length
      ? h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, sourceHead, h('tbody', {}, r.by_source.map(sourceRow))))
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

function categoryDrawer(cat) {
  const g = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const COLORS = ['#23767E', '#4A5A6A', '#6E4A93', '#B4562E', '#B7791F', '#2F5D50', '#5E6B5A', '#7A3418', '#8A5A12', '#69755F'];
  let color = cat.color || COLORS[0];
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
      if (cat.id) await api('PATCH', `/api/expense-categories/${cat.id}`, payload);
      else await api('POST', '/api/expense-categories', payload);
      closeDrawer(); toast('Сохранено'); cat.onSaved?.();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, 'Сохранить');
  const foot = [h('span', { class: 'spacer' }), save];
  if (cat.id) {
    foot.unshift(h('button', { class: 'btn ghost danger', onclick: async () => {
      if (!confirm(`Архивировать категорию «${cat.name}»? Старые расходы останутся, но выбрать её для новых будет нельзя.`)) return;
      try { await api('PATCH', `/api/expense-categories/${cat.id}`, { archived: true }); closeDrawer(); toast('Категория архивирована'); cat.onSaved?.(); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Архивировать'));
  }
  openDrawer(cat.id ? 'Категория расходов' : 'Новая категория', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Название'), g.name = h('input', { class: 'input', value: cat.name || '', required: true })),
    h('div', { class: 'field' }, h('span', {}, 'Цвет'), swatches)), foot);
}

function recurringDrawer(cats, rule, propertyOptions, onSaved) {
  const g = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  g.category_id = h('select', { class: 'input' }, cats.map((c) => h('option', { value: c.id, selected: c.id === rule.category_id }, c.name)));
  g.amount = h('input', { class: 'input', type: 'number', min: 0, value: rule.amount ? Math.round(rule.amount) : '' });
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

function expenseDrawer(cats, propertyOptions, exp, onSaved) {
  const readOnly = !can('manager');
  const g = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  g.date = h('input', { class: 'input', type: 'date', value: exp.date || todayISO(), disabled: readOnly });
  g.amount = h('input', { class: 'input', type: 'number', min: 0, value: exp.amount != null ? Math.round(exp.amount) : '', disabled: readOnly });
  g.category_id = h('select', { class: 'input', disabled: readOnly }, cats.map((c) => h('option', { value: c.id, selected: c.id === exp.category_id }, c.name)));
  g.property_id = h('select', { class: 'input', disabled: readOnly }, h('option', { value: '' }, 'Общий — по всем объектам'),
    propertyOptions.map((p) => h('option', { value: p.id, selected: p.id === exp.property_id }, p.name)));
  g.comment = h('textarea', { class: 'input', disabled: readOnly }, exp.comment || '');
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; err.style.display = 'none';
    try {
      const payload = { date: g.date.value, amount: g.amount.value, category_id: g.category_id.value,
        property_id: g.property_id.value || null, comment: g.comment.value };
      if (exp.id) await api('PATCH', `/api/expenses/${exp.id}`, payload);
      else await api('POST', '/api/expenses', payload);
      closeDrawer(); toast(exp.id ? 'Сохранено' : 'Расход добавлен'); onSaved();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, exp.id ? 'Сохранить' : 'Добавить');
  const foot = readOnly ? null : [h('span', { class: 'spacer' }), save];
  if (exp.id && can('owner')) {
    foot.unshift(h('button', { class: 'btn ghost danger', onclick: async () => {
      if (!confirm('Удалить расход?')) return;
      try { await api('DELETE', `/api/expenses/${exp.id}`); closeDrawer(); toast('Удалено'); onSaved(); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Удалить'));
  }
  openDrawer(exp.id ? 'Расход' : 'Новый расход', h('div', {}, err,
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Дата'), g.date),
      h('label', { class: 'field' }, h('span', {}, 'Сумма, ₽'), g.amount)),
    h('label', { class: 'field' }, h('span', {}, 'Категория'), g.category_id),
    h('label', { class: 'field' }, h('span', {}, 'Объект'), g.property_id),
    h('label', { class: 'field' }, h('span', {}, 'Комментарий'), g.comment)),
  foot);
}

async function viewExpenses(main) {
  const filters = { from: addDays(todayISO(), -30), to: addDays(todayISO(), 1), property_id: state.propertyId, category_id: '' };
  let cats = [];
  let quickCat = null;
  const content = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Расходы'),
    h('button', { class: 'btn', onclick: () => downloadCsv('/api/expenses/export.csv?' + qs(filters), `expenses_${filters.from}_${filters.to}.csv`) },
      icon('download'), 'Выгрузить CSV')), content);

  async function load() {
    const [catsData, data] = await Promise.all([
      api('GET', '/api/expense-categories'), api('GET', '/api/expenses?' + qs(filters))]);
    cats = catsData;
    content.innerHTML = '';

    // быстрое добавление: сумма → категория → сохранить
    const amountInp = h('input', { class: 'input', type: 'number', min: 0, placeholder: 'Сумма, ₽', style: { width: '160px' } });
    const dateInp = h('input', { class: 'input', type: 'date', value: todayISO(), style: { width: '150px' } });
    const chips = h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } });
    const quickSave = h('button', { class: 'btn primary', disabled: true, onclick: async () => {
      quickSave.disabled = true;
      try {
        await api('POST', '/api/expenses', {
          amount: amountInp.value, category_id: quickCat, date: dateInp.value,
          property_id: filters.property_id && filters.property_id !== 'none' ? filters.property_id : null,
        });
        amountInp.value = ''; quickCat = null; drawChips(); toast('Расход добавлен'); load();
      } catch (ex) { toast(ex.message, true); } finally { quickSave.disabled = false; }
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
        h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '10px' } }, amountInp, dateInp, quickSave),
        chips));
    }

    // фильтры
    const propSel = h('select', { class: 'input', style: { width: '190px' } },
      h('option', { value: '', selected: !filters.property_id }, 'Все объекты'),
      state.me.properties.map((p) => h('option', { value: p.id, selected: p.id === filters.property_id }, p.name)),
      h('option', { value: 'none', selected: filters.property_id === 'none' }, 'Общие (без объекта)'));
    propSel.addEventListener('change', () => { filters.property_id = propSel.value; load(); });
    const catSel = h('select', { class: 'input', style: { width: '190px' } }, h('option', { value: '' }, 'Все категории'),
      cats.map((c) => h('option', { value: c.id, selected: c.id === filters.category_id }, c.name)));
    catSel.addEventListener('change', () => { filters.category_id = catSel.value; load(); });
    const fromInp = h('input', { class: 'input', type: 'date', value: filters.from, style: { width: '150px' } });
    const toInp = h('input', { class: 'input', type: 'date', value: filters.to, style: { width: '150px' } });
    fromInp.addEventListener('change', () => { filters.from = fromInp.value; load(); });
    toInp.addEventListener('change', () => { filters.to = toInp.value; load(); });
    content.append(h('div', { class: 'board-tools' }, fromInp, '—', toInp, propSel, catSel,
      can('manager') ? h('button', { class: 'btn primary', style: { marginLeft: 'auto' },
        onclick: () => expenseDrawer(cats, state.me.properties, {}, load) }, icon('plus'), 'Расход') : null));

    // список
    const table = h('div', { class: 'card' });
    if (!data.rows.length) {
      table.append(h('div', { class: 'empty' }, h('h3', {}, 'Расходов не найдено'), 'Измените период или фильтры.'));
    } else {
      table.append(h('div', { class: 'card-head' }, h('h2', {}, 'Расходы за период'), h('b', {}, fmtMoney(data.total))),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' },
          h('thead', {}, h('tr', {}, ['Дата', 'Категория', 'Объект', 'Сумма', 'Комментарий', 'Добавил'].map((t) => h('th', {}, t)))),
          h('tbody', {}, data.rows.map((r) => h('tr', { class: 'click', onclick: () => expenseDrawer(cats, state.me.properties, r, load) },
            h('td', { class: 'num' }, fmtShort(r.date)),
            h('td', {}, h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, h('i', { class: 'dot', style: { background: r.category_color } }), r.category_name)),
            h('td', { class: 'muted small' }, r.property_name || 'Общий', r.room_name ? ` · ${r.room_name}` : ''),
            h('td', { class: 'num' }, fmtMoney(r.amount)),
            h('td', { class: 'muted small' }, r.comment),
            h('td', { class: 'muted small' }, r.created_by_name || '—')))))));
    }
    content.append(table);

    // итоги по категориям
    if (data.by_category.length) {
      const maxAmt = Math.max(1, ...data.by_category.map((x) => Number(x.amount)));
      const catRow = (x) => {
        const dot = h('i', { class: 'dot', style: { background: x.category_color } });
        const label = h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, dot, x.category_name);
        const barFill = h('i', { style: { width: `${(Number(x.amount) / maxAmt) * 100}%`, background: x.category_color } });
        const bar = h('div', { class: 'bar-h' }, barFill);
        return h('tr', {}, h('td', {}, label), h('td', { class: 'num' }, x.count),
          h('td', { class: 'num' }, fmtMoney(x.amount)), h('td', { style: { width: '35%' } }, bar));
      };
      const rows = data.by_category.map(catRow);
      const tbody = h('tbody', {}, rows);
      const table = h('table', { class: 'list' }, tbody);
      const head = h('div', { class: 'card-head' }, h('h2', {}, 'По категориям'));
      content.append(h('div', { class: 'card' }, head, table));
    }

    // категории (владелец управляет, остальные видят список)
    const catsCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Категории расходов'),
      can('owner') ? h('button', { class: 'btn small', onclick: () => categoryDrawer({ onSaved: load }) }, icon('plus'), 'Категория') : null),
      h('div', { class: 'card-pad', style: { display: 'flex', gap: '8px', flexWrap: 'wrap', paddingTop: '10px' } },
        cats.map((c) => h('button', { class: 'btn small' + (can('owner') ? '' : ' ghost'), style: { borderColor: c.color, color: c.color },
          onclick: () => can('owner') && categoryDrawer({ ...c, onSaved: load }) }, h('i', { class: 'dot', style: { background: c.color } }), c.name))));
    content.append(catsCard);

    // повторяющиеся расходы
    {
      const recurring = await api('GET', '/api/expense-recurring');
      const recCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Повторяющиеся расходы'),
        can('owner') ? h('button', { class: 'btn small', onclick: () => recurringDrawer(cats, {}, state.me.properties, load) }, icon('plus'), 'Добавить') : null));
      if (!recurring.length) {
        recCard.append(h('div', { class: 'empty' }, 'Пока нет ни одного шаблона. Например: аренда 1-го числа или интернет 10-го.'));
      } else {
        recCard.append(h('table', { class: 'list' }, h('tbody', {}, recurring.map((r) => h('tr', { class: can('owner') ? 'click' : '', onclick: () => can('owner') && recurringDrawer(cats, r, state.me.properties, load) },
          h('td', {}, h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, h('i', { class: 'dot', style: { background: r.category_color } }), r.category_name),
            !r.active ? h('span', { class: 'pill none', style: { marginLeft: '8px' } }, 'выключен') : null),
          h('td', { class: 'muted small' }, r.property_name || 'Общий'),
          h('td', { class: 'num' }, fmtMoney(r.amount)),
          h('td', { class: 'muted small' }, `${r.day_of_month}-го числа`),
          h('td', { class: 'muted small' }, r.comment))))));
      }
      content.append(recCard);
    }
  }
  load().catch((ex) => content.append(h('div', { class: 'card empty' }, ex.message)));
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
        h('button', { class: 'btn icon ghost del', type: 'button', title: 'Убрать категорию', disabled: types.length === 1,
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
        h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Страница, где гость сам выбирает даты и отправляет заявку. Заявки появляются в шахматке со статусом «Ждёт оплаты».'),
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
        h('div', { class: 'row3' }, fld('capacity', 'Гостей', { type: 'number', min: 1, value: t.capacity ?? 2 }), fld('base_price', 'Цена, ₽', { type: 'number', min: 0, value: t.base_price != null ? Math.round(t.base_price) : '' }), fld('min_stay', 'Мин. ночей', { type: 'number', min: 1, value: t.min_stay ?? 1 }))),
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
        g.role = h('select', { class: 'input' }, h('option', { value: 'manager' }, 'Администратор — брони, цены, площадки'), h('option', { value: 'housekeeper' }, 'Горничная — только шахматка и заезды'));
        openDrawer('Новый сотрудник', h('div', {}, fld('name', 'Имя'), fld('email', 'Email для входа', { type: 'email' }), fld('password', 'Временный пароль', { type: 'text' }),
          h('label', { class: 'field' }, h('span', {}, 'Доступ'), g.role)),
        [h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
          try { await api('POST', '/api/users', { name: g.name.value, email: g.email.value, password: g.password.value, role: g.role.value }); closeDrawer(); toast('Сотрудник добавлен'); load(); }
          catch (ex) { toast(ex.message, true); }
        } }, 'Добавить')]);
      } }, icon('plus'), 'Сотрудник')),
    h('table', { class: 'list' }, h('tbody', {}, users.map((u) => h('tr', {},
      h('td', {}, h('b', {}, u.name), h('div', { class: 'muted small' }, u.email)), h('td', {}, ROLE[u.role]),
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
  }
  load().catch((ex) => content.append(h('div', { class: 'card empty' }, ex.message)));
}

boot();
