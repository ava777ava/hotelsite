// Панель оператора сервиса: клиенты, тарифы, счета и оплата вручную. Отдельный вход (токен хранится под своим ключом).
import { $app, fmtDate, fmtDateTime, fmtMoney, h, openDrawer, closeDrawer, openModal, closeModal, toast } from '/static/admin/core.js';
import { printInvoiceDoc } from '/static/admin/invoice.js';

const KEY = 'op_token';
const tok = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const setTok = (v) => { try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); } catch { /* без хранилища — войти придётся заново */ } };

async function api(method, path, body) {
  const res = await fetch(path, { method, headers: { 'Content-Type': 'application/json', ...(tok() ? { Authorization: `Bearer ${tok()}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && tok()) { setTok(null); render(); }
  if (!res.ok) throw new Error(data.error || `Ошибка ${res.status}`);
  return data;
}

const STATUS = { active: ['ok', 'активен'], suspended: ['bad', 'приостановлен'] };
const INV = { issued: ['warn', 'ждёт оплаты'], paid: ['ok', 'оплачен'], cancelled: ['none', 'отменён'] };
const field = (label, el) => h('label', { class: 'field' }, h('span', {}, label), el);

function login() {
  const email = h('input', { class: 'input', type: 'email', name: 'email', autocomplete: 'username' });
  const pass = h('input', { class: 'input', type: 'password', name: 'password', autocomplete: 'current-password' });
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const go = async (e) => {
    e.preventDefault();
    try { const r = await api('POST', '/api/operator/login', { email: email.value, password: pass.value }); setTok(r.token); render(); }
    catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  };
  return h('div', { class: 'auth-wrap' }, h('form', { class: 'card card-pad auth-form', onsubmit: go, style: { maxWidth: '380px', margin: '10vh auto' } },
    h('h1', {}, 'Панель оператора'), h('p', { class: 'muted' }, 'Вход для сотрудников сервиса. Клиентские логины здесь не работают.'), err,
    field('Email', email), field('Пароль', pass), h('button', { class: 'btn primary', type: 'submit', style: { width: '100%' } }, 'Войти'),
    h('p', { class: 'muted small' }, 'Оператора заводит администратор сервера: python -m app.admin create-operator <email>')));
}

async function accountDrawer(id, reload) {
  let d;
  try { d = await api('GET', `/api/operator/accounts/${id}`); } catch (ex) { toast(ex.message, true); return; }
  const a = d.account;
  const plans = (await api('GET', '/api/operator/accounts')).plans;
  const plan = h('select', { class: 'input' }, plans.map((p) => h('option', { value: p.key, selected: p.key === a.plan }, p.label)));
  const until = h('input', { class: 'input', type: 'date', value: a.paid_until ? String(a.paid_until).slice(0, 10) : '' });
  const notes = h('textarea', { class: 'input', rows: 4, placeholder: 'Что обсуждали, о чём договорились' }, a.notes || '');
  const save = async (patch, msg) => { try { await api('PATCH', `/api/operator/accounts/${id}`, patch); toast(msg || 'Сохранено'); closeDrawer(); reload(); } catch (ex) { toast(ex.message, true); } };
  const invPlan = h('select', { class: 'input' }, plans.filter((p) => ['start', 'business', 'pro'].includes(p.key)).map((p) => h('option', { value: p.key }, p.label)));
  const invMonths = h('input', { class: 'input', type: 'number', min: 1, max: 36, value: 1 });
  const invAmount = h('input', { class: 'input', type: 'number', min: 0, placeholder: 'по прайсу' });
  const invoiceRow = (i) => h('div', { class: 'move-row small', style: { gridTemplateColumns: '1fr auto' } },
    h('div', {}, h('b', {}, `№ ${i.number}`), ` · ${i.plan}, ${i.months} мес. · ${fmtMoney(i.amount)} · от ${fmtDate(i.issued_on)} `, h('span', { class: `pill ${INV[i.status][0]}` }, INV[i.status][1])),
    h('div', { style: { display: 'flex', gap: '6px', flexWrap: 'wrap' } },
      h('button', { class: 'btn small', onclick: async () => { try { printInvoiceDoc(await api('GET', `/api/operator/invoices/${i.id}`)); } catch (ex) { toast(ex.message, true); } } }, 'Печать'),
      i.status === 'issued' ? h('button', { class: 'btn small primary', onclick: async () => { if (!confirm('Отметить счёт оплаченным и продлить доступ?')) return; try { await api('POST', `/api/operator/invoices/${i.id}/paid`, {}); toast('Оплата отмечена, доступ продлён'); closeDrawer(); reload(); } catch (ex) { toast(ex.message, true); } } }, 'Оплачен') : null,
      i.status === 'issued' ? h('button', { class: 'btn small ghost', onclick: async () => { try { await api('POST', `/api/operator/invoices/${i.id}/cancel`, {}); closeDrawer(); reload(); } catch (ex) { toast(ex.message, true); } } }, 'Отменить') : null));
  openDrawer(a.name, h('div', {},
    h('div', { class: 'muted small' }, `Владелец: ${a.owner_email || '—'} · создан ${fmtDate(a.created_at)} · последний вход ${fmtDateTime(a.last_login)}`),
    h('div', { class: 'muted small', style: { marginBottom: '12px' } }, `Объектов ${a.properties}, номеров ${a.rooms}, броней за 30 дней ${a.bookings_30d}`),
    h('h3', {}, 'Тариф и доступ'),
    h('div', { class: 'row2' }, field('Тариф', plan), field('Оплачен до', until)),
    h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' } },
      h('button', { class: 'btn small primary', onclick: () => save({ plan: plan.value, paid_until: until.value || null }) }, 'Сохранить тариф'),
      a.status === 'active' ? h('button', { class: 'btn small danger', onclick: () => confirm('Приостановить доступ клиента?') && save({ status: 'suspended' }, 'Доступ приостановлен') }, 'Приостановить')
        : h('button', { class: 'btn small primary', onclick: () => save({ status: 'active' }, 'Доступ включён') }, 'Включить доступ')),
    h('h3', {}, 'Заметки'), notes, h('button', { class: 'btn small', style: { margin: '6px 0 14px' }, onclick: () => save({ notes: notes.value }) }, 'Сохранить заметку'),
    h('h3', {}, 'Счета'), d.invoices.length ? d.invoices.map(invoiceRow) : h('div', { class: 'muted small' }, 'Счетов нет'),
    h('div', { class: 'row3', style: { marginTop: '10px' } }, field('Тариф', invPlan), field('Месяцев', invMonths), field('Сумма, ₽', invAmount)),
    h('button', { class: 'btn small primary', onclick: async () => {
      try { const r = await api('POST', `/api/operator/accounts/${id}/invoices`, { plan: invPlan.value, months: invMonths.value, amount: invAmount.value }); toast(`Счёт № ${r.number} выставлен`); closeDrawer(); accountDrawer(id, reload); reload(); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Выставить счёт'),
    h('h3', { style: { marginTop: '18px' } }, 'Сотрудники клиента'),
    d.users.map((u) => h('div', { class: 'small' }, `${u.role}: ${u.name} <${u.email}> · вход ${fmtDateTime(u.last_login_at)}`)),
    h('button', { class: 'btn small ghost', style: { marginTop: '10px' }, onclick: async () => {
      const email = prompt('Для кого выдать новый временный пароль (email сотрудника)?', a.owner_email || ''); if (!email) return;
      try { const r = await api('POST', '/api/operator/reset-password', { email }); openModal('Новый пароль', h('div', {}, h('p', {}, `Временный пароль для ${email}:`), h('code', { style: { fontSize: '18px', userSelect: 'all' } }, r.password), h('p', { class: 'muted small' }, 'Передайте его владельцу и попросите сменить в «Профиле». Повторно пароль не показывается.')), [h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: () => closeModal() }, 'Готово')]); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Выдать новый пароль')));
}

async function panel() {
  const root = h('div', { class: 'stack', style: { maxWidth: '1200px', margin: '0 auto', padding: '18px 16px 40px' } });
  const q = h('input', { class: 'input', placeholder: 'Поиск по названию или email', style: { maxWidth: '320px' }, oninput: () => draw() });
  let data = null;
  const table = h('div', { class: 'card' });
  const kpis = h('div', { class: 'kpis' });
  const load = async () => { data = await api('GET', '/api/operator/accounts'); draw(); };
  function draw() {
    const s = data.stats;
    kpis.innerHTML = '';
    kpis.append(...[['Аккаунтов', s.accounts], ['Активных', s.active], ['На пробном', s.trial], ['Номеров', s.rooms], ['Броней за 30 дней', s.bookings_30d]].map(([l, v]) => h('div', { class: 'kpi' }, h('div', { class: 'l' }, l), h('div', { class: 'v' }, v))));
    const needle = q.value.trim().toLowerCase();
    const items = data.items.filter((r) => !needle || r.name.toLowerCase().includes(needle) || (r.owner_email || '').toLowerCase().includes(needle));
    table.innerHTML = '';
    table.append(h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' },
      h('thead', {}, h('tr', {}, ['Клиент', 'Тариф', 'Оплачен до / пробный до', 'Объектов', 'Номеров', 'Брони 30д', 'Последний вход', 'Статус'].map((x) => h('th', {}, x)))),
      h('tbody', {}, items.map((r) => {
        const end = r.plan === 'trial' ? r.trial_ends : r.paid_until;
        const left = end ? Math.round((new Date(String(end).slice(0, 10) + 'T00:00') - new Date(new Date().toDateString())) / 86400000) : null;
        return h('tr', { class: 'click', onclick: () => accountDrawer(r.id, load) },
          h('td', { class: 'wide' }, h('b', {}, r.name), r.is_demo ? h('span', { class: 'pill none', style: { marginLeft: '6px' } }, 'демо') : null, h('div', { class: 'muted small' }, r.owner_email || '')),
          h('td', { 'data-l': 'Тариф' }, r.plan_label, r.open_invoices ? h('span', { class: 'pill warn', style: { marginLeft: '6px' } }, `счёт: ${r.open_invoices}`) : null),
          h('td', { 'data-l': 'Оплачен до', class: left != null && left < 0 ? 'down' : '' }, end ? fmtDate(end) : '—', left != null ? h('span', { class: 'muted small' }, left < 0 ? ` (просрочено ${-left} дн.)` : ` (${left} дн.)`) : null),
          h('td', { 'data-l': 'Объектов' }, r.properties), h('td', { 'data-l': 'Номеров' }, r.rooms), h('td', { 'data-l': 'Брони за 30 дней' }, r.bookings_30d), h('td', { 'data-l': 'Последний вход', class: 'small' }, r.last_login ? fmtDateTime(r.last_login) : '—'),
          h('td', { 'data-l': 'Статус' }, h('span', { class: `pill ${STATUS[r.status][0]}` }, STATUS[r.status][1])));
      })))));
    if (!items.length) table.append(h('div', { class: 'card-pad muted' }, 'Ничего не найдено'));
  }
  root.append(h('div', { class: 'page-head' }, h('h1', {}, 'Панель оператора'), q,
    h('button', { class: 'btn', title: 'Разослать напоминания об окончании тарифа сейчас (обычно это делает планировщик)', onclick: async () => { try { const r = await api('POST', '/api/operator/reminders', {}); toast(`Отправлено напоминаний: ${r.sent}`); } catch (ex) { toast(ex.message, true); } } }, 'Напомнить об оплате'),
    h('button', { class: 'btn ghost', onclick: () => { setTok(null); render(); } }, 'Выйти')), kpis, table);
  await load();
  return root;
}

async function render() {
  $app.innerHTML = '';
  if (!tok()) { $app.append(login()); return; }
  try { $app.append(await panel()); } catch (ex) { $app.append(h('div', { class: 'card empty' }, ex.message)); }
}
render();
