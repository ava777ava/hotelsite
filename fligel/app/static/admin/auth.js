// Флигель — интерфейс администратора (раздел «вход и регистрация»). ES-модуль без сборки.
import { currentRoute, render } from './app.js';
import { api, h, icon, openDrawer, pad, state, store, toast } from './core.js';
import { count } from './ui.js';

// ---------- вход и регистрация ----------
export function viewAuth() {
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
    mode === 'login' ? h('div', { class: 'auth-switch' },
      h('button', { type: 'button', onclick: () => forgotPasswordDrawer(f.email?.value) }, 'Забыли пароль?')) : null,
    h('div', { class: 'auth-switch' }, mode === 'login' ? 'Ещё нет аккаунта? ' : 'Уже есть аккаунт? ',
      h('button', { type: 'button', onclick: () => { mode = mode === 'login' ? 'register' : 'login'; draw(); } },
        mode === 'login' ? 'Зарегистрироваться' : 'Войти')));
    formBox.append(h('div', {}, h('div', { class: 'brand auth-mobile-brand' }, h('div', { class: 'brand-mark' }), h('div', { class: 'brand-name' }, 'Флигель')), form));
  };
  draw();
  wrap.append(art, formBox);
  return wrap;
}

export function forgotPasswordDrawer(prefillEmail) {
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

export function viewResetPassword() {
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
export function viewWizard() {
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
