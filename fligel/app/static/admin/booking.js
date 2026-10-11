// Флигель — интерфейс администратора (раздел «карточка брони»). ES-модуль без сборки.
import { render } from './app.js';
import { G, SOURCE, addDays, api, can, closeDrawer, closeModal, copyText, diffDays, fmtDate, fmtDateTime, fmtMoney, fmtShort, h, icon, letterhead, nightsWord, openDrawer, openModal, parseISO, qs, requestCloseDrawer, state, toast, toastUndo, todayISO } from './core.js';
import { bindPhone, guestDrawer, messageDialog, phoneActions, phoneDigits } from './guests.js';
import { plural, count, humanDay, dateRange } from './ui.js';

// ---------- анкета гостя и отзыв ----------
// Гость отвечает по секретной ссылке (без входа): время приезда, число гостей, машина, пожелания. Паспортные данные не собираем.
function guestAnswers(b) {
  const box = h('div', { class: 'answers-box' });
  const canReview = b.check_in <= todayISO();
  async function load() {
    let info;
    try { info = await api('GET', `/api/bookings/${b.id}/form`); } catch { return; }
    const link = async (kind) => {
      try { const r = await api('POST', `/api/bookings/${b.id}/link`, { kind }); copyText(r.url, 'Ссылка скопирована — отправьте её гостю'); load(); }
      catch (ex) { toast(ex.message, true); }
    };
    const f = info.form;
    const rv = info.review;
    box.innerHTML = '';
    box.append(
      h('div', { class: 'answers-head' }, h('b', {}, 'Анкета гостя'),
        h('button', { type: 'button', class: 'link', onclick: () => link('form') }, f ? 'Скопировать ссылку' : 'Получить ссылку для гостя')),
      f && f.filled_at ? h('div', { class: 'answers' },
        h('div', {}, `Приедет: ${f.arrival_time || 'время не указал'} · гостей: ${f.guests_count || '—'}${f.car_number ? ` · машина ${f.car_number}` : ''}`),
        f.wishes ? h('div', { class: 'muted' }, `Пожелания: ${f.wishes}`) : null)
        : h('div', { class: 'muted small' }, f ? 'Гость пока не заполнил анкету.' : 'Отправьте гостю ссылку — он сообщит время приезда, число гостей и пожелания.'),
      canReview ? h('div', { class: 'answers-head', style: { marginTop: '8px' } }, h('b', {}, 'Отзыв'),
        h('button', { type: 'button', class: 'link', onclick: () => link('review') }, rv ? 'Скопировать ссылку' : 'Получить ссылку на отзыв')) : null,
      rv && rv.submitted_at ? h('div', { class: 'answers' }, h('span', { class: `pill ${rv.rating <= 3 ? 'bad' : 'ok'}` }, `${rv.rating} из 5`),
        rv.comment ? h('span', { class: 'muted' }, ` ${rv.comment}`) : null) : null);
  }
  load();
  return box;
}

// ---------- карточка брони ----------
export function allRooms() {
  if (!G.boardData) return [];
  return G.boardData.room_types.flatMap((t) => t.rooms.map((r) => ({ ...r, type: t.name })));
}

export async function ensureBoardData() {
  if (!G.boardData || G.boardData.property.id !== state.propertyId) {
    G.boardData = await api('GET', '/api/board?' + qs({ property_id: state.propertyId, from: todayISO(), days: 1 }));
  }
}

// После создания брони по телефону — сразу предложить отправить гостю подтверждение
export function offerSendConfirmation(created) {
  openModal('Бронь создана', h('div', {}, h('p', { style: { marginTop: 0 } }, 'Отправить гостю подтверждение? Подставим даты, цену и адрес из шаблона.')),
    [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Позже'), h('span', { class: 'spacer' }),
      h('button', { class: 'btn primary', onclick: () => { closeModal(); messageDialog(created); } }, 'Написать гостю')]);
}

// Переселение посреди проживания: до выбранной даты гость остаётся в прежнем номере, дальше — в новом
export function relocateDialog(b, rooms, onSaved) {
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

// ---------- деньги в брони: платежи, услуги, скидка, залог ----------
export const PAY_METHOD = { cash: 'Наличные', card: 'Карта', transfer: 'Перевод', online: 'Онлайн', other: 'Другое' };
export const DEPOSIT = { none: 'Без залога', expected: 'Ожидается', held: 'Внесён', returned: 'Возвращён', kept: 'Удержан' };

export function moneyBlock(b, onChange) {
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

export async function printInvoice(b) {
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

export const DRAFT_KEY = 'draft_booking';
export function loadDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
    if (!d || Date.now() - d.at > 3 * 3600 * 1000 || d.property !== state.propertyId) return null;
    return d.data;
  } catch { return null; }
}
export const clearDraft = () => { try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ } };

export async function bookingDrawer(b, onSaved) {
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
    f.check_out.min = addDays(f.check_in.value, 1);
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
    inp('guest_name', 'Гость', { autocomplete: 'off', autocapitalize: 'words', placeholder: 'Имя и фамилия' }),
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
    isNew || readOnly || !can('manager') ? null : guestAnswers(b),
    h('div', { class: 'row3' },
      inp('guests_count', 'Гостей', { type: 'number', min: 1, value: b.guests_count || 1, oninput: () => requote() }),
      inp('total_price', 'Стоимость, ₽', { money: true, type: 'number', min: 0, value: b.total_price != null ? Math.round(b.total_price) : '', oninput: () => { priceTouched = true; updateTotal(); } }),
      isNew ? inp('paid_amount', 'Предоплата, ₽', { money: true, type: 'number', min: 0, value: 0, oninput: updateTotal }) : h('div')),
    isNew ? h('label', { class: 'field', style: { display: 'none' }, 'data-prepay': '1' }, h('span', {}, 'Как оплачена предоплата'), f.pay_method = h('select', { class: 'input' }, Object.entries(PAY_METHOD).map(([k, l]) => h('option', { value: k }, l)))) : null,
    h('label', { class: 'field' }, h('span', {}, 'Источник'), f.source),
    inp('door_code', 'Код двери или сейфа для гостя', { maxlength: 100, autocomplete: 'off', placeholder: 'Подставляется в сообщения как {код двери}' }),
    planField,
    h('div', { class: 'summary' }, nightsEl, totalEl), breakdownEl,
    isNew || status.value === 'blocked' ? null : moneyBlock(b, (m) => { b.total_price = m.total; b.paid_amount = m.paid; b.updated_at = m.updated_at; f.total_price.value = Math.round(Number(m.total)); priceTouched = true; updateTotal(); }));
  guestBox.style.display = status.value === 'blocked' ? 'none' : '';
  bindPhone(f.guest_phone);
  let hintTimer;
  const checkGuest = async () => {
    guestHint.innerHTML = '';
    if (readOnly || phoneDigits(f.guest_phone.value).length < 10) return;
    guestHint.append(h('div', { style: { marginBottom: '6px' } }, phoneActions(f.guest_phone.value)));
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
      guests_count: f.guests_count.value || 1, total_price: f.total_price.value, source: f.source.value, door_code: f.door_code.value,
    });
    if (isNew && f.paid_amount) { payload.paid_amount = f.paid_amount.value || 0; payload.payment_method = f.pay_method.value; }
    if (isNew && f.rate_plan_id.value && status.value !== 'blocked') payload.rate_plan_id = f.rate_plan_id.value;
    if (isNew && extra.size) payload.extra_room_ids = [...extra];
    if (imported) { delete payload.room_id; delete payload.check_in; delete payload.check_out; delete payload.source; }
    try {
      let created = null;
      if (isNew) created = await api('POST', '/api/bookings', payload);
      else await api('PATCH', `/api/bookings/${b.id}`, { ...payload, expected_updated_at: b.updated_at });
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
  // Enter в обычном поле сохраняет бронь (в заметке и в блоке платежей — нет)
  if (!readOnly) body.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && !e.target.closest('.money-box') && e.target.type !== 'checkbox') { e.preventDefault(); save.click(); }
  });
  if (restored) {
    note.className = 'note'; note.style.display = '';
    note.append('Восстановлен черновик брони, который вы не успели сохранить. ', h('button', { type: 'button', class: 'link', onclick: () => { clearDraft(); closeDrawer(); bookingDrawer({}, onSaved); } }, 'Начать заново'));
  }
  updateTotal();
  requote();
}
