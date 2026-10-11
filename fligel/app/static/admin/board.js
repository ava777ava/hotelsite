// Флигель — интерфейс администратора (раздел «шахматка»). ES-модуль без сборки.
import { autoRefresh } from './app.js';
import { allRooms, bookingDrawer, ensureBoardData } from './booking.js';
import { HK } from './cleaning.js';
import { G, MONTHS_SHORT, SOURCE, STATUS, WD, addDays, api, can, closeModal, diffDays, fmtDate, fmtMoney, fmtPriceCell, fmtShort, h, icon, nightsWord, openModal, pad, parseISO, qs, state, store, toast, toastUndo, todayISO } from './core.js';
import { rateDrawer } from './rates.js';
import { count, holidayName, skeleton, SOURCE_ABBR } from './ui.js';

// «Быстрый старт»: чек-лист для нового аккаунта на шахматке, пока не всё настроено
export async function drawOnboarding(box) {
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
export function applyZoom() {
  const narrow = window.innerWidth < 860;
  const w = { 14: narrow ? 46 : 60, 31: narrow ? 38 : 44, 92: narrow ? 20 : 26 }[state.boardDays] || 44;
  document.documentElement.style.setProperty('--cell', `${w}px`);
}
export const hiddenTypes = () => { try { return new Set(JSON.parse(store.get('board_hidden', '[]'))); } catch { return new Set(); } };

export async function viewBoard(main) {
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
  G.boardActions = { shift, today: () => { state.boardFrom = addDays(todayISO(), -2); load(); } };
  const load = async () => {
    dateIn.value = state.boardFrom;
    try {
      G.boardData = await api('GET', (state.me.role === 'landlord' ? '/api/landlord/board?' : '/api/board?') + qs({ property_id: state.propertyId, from: state.boardFrom, days: state.boardDays }));
      state.conflicts = G.boardData.open_conflicts;
      banner.innerHTML = '';
      if (G.boardData.open_conflicts) {
        banner.append(h('div', { class: 'banner' }, h('b', {}, '!'),
          h('div', {}, `С площадок пришли брони на уже занятые даты: ${G.boardData.open_conflicts}. `,
            h('a', { href: '#/channels' }, 'Разобрать конфликты'))));
      }
      // при автообновлении не сбрасываем прокрутку шахматки
      const old = card.querySelector('.board-scroll');
      const pos = old ? [old.scrollLeft, old.scrollTop] : null;
      card.innerHTML = '';
      const hidden = hiddenTypes();
      typeFilter.innerHTML = '';
      if (G.boardData.room_types.length > 1) {
        typeFilter.append(h('span', { class: 'muted small' }, 'Категории:'), ...G.boardData.room_types.map((t) => h('button', { type: 'button', class: 'chip' + (hidden.has(t.id) ? '' : ' on'), onclick: () => {
          const hs = hiddenTypes(); if (hs.has(t.id)) hs.delete(t.id); else hs.add(t.id);
          if (hs.size >= G.boardData.room_types.length) hs.clear();
          store.set('board_hidden', JSON.stringify([...hs])); load();
        } }, t.name)));
      }
      card.append(drawBoard({ ...G.boardData, room_types: G.boardData.room_types.filter((t) => !hidden.has(t.id)) }, load));
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
export function bindBarDrag(bar, b, room, draggable, ctx) {
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

// Подтверждение переноса брони: новые даты и номер можно поправить, цена пересчитывается по тарифам
// (или остаётся прежней / вводится вручную) — и только после «Подтвердить» уходит на сервер.
export async function moveDialog(b, change, reload) {
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
      await api('PATCH', `/api/bookings/${b.id}`, { ...payload, expected_updated_at: b.updated_at });
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

export function drawBoard(data, reload) {
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

export function dateNoteDialog(day, text, reload) {
  const input = h('textarea', { class: 'input', placeholder: 'Например: День города — цены выше, ждём много заездов' }, text || '');
  openModal(`Заметка на ${fmtDate(day)}`, h('div', {}, h('label', { class: 'field' }, h('span', {}, 'Видят все сотрудники'), input)),
    [text ? h('button', { class: 'btn ghost danger', onclick: async () => { await api('PUT', '/api/date-notes', { day, text: '', property_id: state.propertyId }); closeModal(); reload(); } }, 'Удалить') : null, h('span', { class: 'spacer' }),
      h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'),
      h('button', { class: 'btn primary', onclick: async () => { try { await api('PUT', '/api/date-notes', { day, text: input.value, property_id: state.propertyId }); closeModal(); reload(); } catch (ex) { toast(ex.message, true); } } }, 'Сохранить')]);
}
