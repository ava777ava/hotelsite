// Флигель — интерфейс администратора (раздел «гости»). ES-модуль без сборки.
import { bookingDrawer } from './booking.js';
import { api, closeDrawer, closeModal, copyText, fmtMoney, fmtShort, h, icon, openDrawer, openModal, pad, qs, requestCloseDrawer, store, toast } from './core.js';

// ---------- телефоны ----------
export function formatPhone(raw) {
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
export function bindPhone(input) {
  input.addEventListener('input', () => {
    if (input.selectionStart === input.value.length && !(input.inputType === 'deleteContentBackward')) input.value = formatPhone(input.value);
  });
  input.addEventListener('blur', () => { input.value = formatPhone(input.value); });
  return input;
}
export const phoneDigits = (p) => String(p || '').replace(/\D/g, '');
// Позвонить, написать в Telegram, скопировать номер для MAX
export function phoneActions(phone) {
  const d = phoneDigits(phone);
  if (d.length < 10) return null;
  const intl = (d.length === 11 && d[0] === '8' ? '7' + d.slice(1) : d);
  return h('span', { class: 'phone-actions' },
    h('a', { class: 'btn small ghost', href: `tel:+${intl}`, title: 'Позвонить' }, icon('phone'), 'Позвонить'),
    h('a', { class: 'btn small ghost', href: `https://t.me/+${intl}`, target: '_blank', rel: 'noopener', title: 'Открыть чат в Telegram' }, 'Telegram'),
    h('button', { class: 'btn small ghost', type: 'button', title: 'Скопировать номер для поиска в MAX', onclick: () => copyText('+' + intl, 'Номер скопирован — вставьте его в поиск MAX') }, 'MAX'));
}

// ---------- гости ----------
export async function viewGuests(main) {
  const q = h('input', { class: 'input search-field', placeholder: 'Имя, телефон или тег', style: { width: '260px' }, value: store.get('guests_q', '') });
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
export async function guestDrawer(phone, name, onChange) {
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
export async function messageDialog(b) {
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

// Шаблоны сообщений гостю — правка в настройках
export function templatesCard() {
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
