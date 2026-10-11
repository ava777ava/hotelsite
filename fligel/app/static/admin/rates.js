// Флигель — интерфейс администратора (раздел «цены»). ES-модуль без сборки.
import { MONTHS_NOM, WD, addDays, api, closeDrawer, fmtDate, fmtMoney, fmtPriceCell, h, iso, openDrawer, pad, parseISO, qs, state, store, toast, todayISO } from './core.js';
import { plural, count, holidayName } from './ui.js';

// ---------- цена на дату из шахматки ----------
export function rateDrawer(t, day, reload) {
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

// ---------- цены ----------
// Календарь цен на 3 месяца: выделите даты (клик, Shift — диапазон) и измените цену / минимум ночей / закрытие сразу
export async function priceCalendar(card, prop) {
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
export async function viewRates(main) {
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
