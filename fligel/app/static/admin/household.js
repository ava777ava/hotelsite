// Флигель — интерфейс администратора (раздел «хозяйство»: склад, счётчики, инвентарь номеров). ES-модуль без сборки.
import { api, can, closeModal, fmtDate, fmtDateTime, fmtMoney, h, icon, openModal, qs, state, store, todayISO, toast } from './core.js';

const TABS = [['stock', 'Склад'], ['meters', 'Счётчики'], ['inventory', 'Инвентарь']];
const KIND = { in: 'Приход', out: 'Расход', writeoff: 'Списание', cleaning: 'При уборке', correction: 'Пересчёт' };
const qtyFmt = (v) => String(Number(v)).replace('.', ',');
const unitQty = (v, unit) => `${qtyFmt(v)} ${unit}`;

const row2 = (...c) => h('div', { class: 'row2' }, ...c);
const field = (label, el) => h('label', { class: 'field' }, h('span', {}, label), el);

// ---------- проверка инвентаря номера после выезда (горничная; открывается и со страницы «Уборка») ----------
export async function inventoryCheckDialog(room, booking) {
  let inv;
  try { inv = await api('GET', `/api/rooms/${room.id}/inventory`); } catch (ex) { toast(ex.message, true); return; }
  if (!inv.items.length) {
    openModal(`Инвентарь номера ${room.name}`, h('div', {}, h('p', {}, 'Список вещей в номере не задан.'), h('p', { class: 'muted small' }, 'Администратор может составить его в разделе «Хозяйство → Инвентарь» (чайник, фен, полотенца…) — тогда после выезда останется пройтись по списку.')),
      [h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: () => closeModal() }, 'Понятно')]);
    return;
  }
  const states = {};
  const notes = {};
  const rows = inv.items.map((it) => {
    states[it.id] = 'ok';
    const note = h('input', { class: 'input', placeholder: 'Что именно (необязательно)', style: { display: 'none', marginTop: '6px' }, oninput: () => { notes[it.id] = note.value; } });
    const seg = h('div', { class: 'seg inv-seg' });
    const draw = () => {
      seg.innerHTML = '';
      [['ok', 'На месте'], ['missing', 'Нет'], ['broken', 'Сломано']].forEach(([k, l]) => seg.append(h('button', { type: 'button', class: `${states[it.id] === k ? 'on' : ''} inv-${k}`, onclick: () => { states[it.id] = k; note.style.display = k === 'ok' ? 'none' : ''; draw(); } }, l)));
    };
    draw();
    return h('div', { class: 'inv-row' }, h('div', { class: 'inv-name' }, h('b', {}, it.name), it.qty > 1 ? h('span', { class: 'muted' }, ` × ${it.qty}`) : null, it.note ? h('div', { class: 'muted small' }, it.note) : null), seg, note);
  });
  openModal(`Проверка номера ${room.name}`, h('div', {}, h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Отметьте, чего не хватает или что сломано, — администратору придёт задача.'), ...rows),
    [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
      try {
        const r = await api('POST', `/api/rooms/${room.id}/inventory-check`, { booking_id: booking?.id, items: inv.items.map((it) => ({ item_id: it.id, state: states[it.id], note: notes[it.id] || '' })) });
        closeModal(); toast(r.problems ? `Передано администратору: ${r.problems}` : 'Всё на месте — спасибо!');
      } catch (ex) { toast(ex.message, true); }
    } }, 'Готово')]);
}

export async function viewHousehold(main) {
  const manager = can('manager');
  const tabs = manager ? TABS : TABS.slice(0, 1);
  let tab = tabs.some(([k]) => k === store.get('hh_tab')) ? store.get('hh_tab') : 'stock';
  const body = h('div', { class: 'stack' });
  const seg = h('div', { class: 'seg' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Хозяйство')), manager ? h('div', { class: 'seg-scroll' }, seg) : null, body);
  const drawSeg = () => { seg.innerHTML = ''; tabs.forEach(([k, l]) => seg.append(h('button', { type: 'button', class: tab === k ? 'on' : '', onclick: () => { tab = k; store.set('hh_tab', k); load(); } }, l))); };
  const bad = (ex) => toast(ex.message, true);

  // ---------------- склад ----------------
  async function drawStock() {
    const d = await api('GET', '/api/stock?' + qs({ property_id: state.propertyId }));
    const moveDialog = (it, kind) => {
      const title = { out: `Взять со склада: ${it.name}`, in: `Приход: ${it.name}`, writeoff: `Списать: ${it.name}`, correction: `Пересчёт: ${it.name}` }[kind];
      const amount = h('input', { class: 'input', type: 'number', min: 0, step: 'any', value: kind === 'correction' ? Number(it.quantity) : '', inputmode: 'decimal' });
      const note = h('input', { class: 'input', placeholder: kind === 'writeoff' ? 'Причина: брак, потеряли…' : 'Комментарий (необязательно)' });
      const err = h('div', { class: 'note bad', style: { display: 'none' } });
      openModal(title, h('div', {}, err, field(kind === 'correction' ? `Сколько на самом деле (${it.unit})` : `Сколько (${it.unit})`, amount), field('Комментарий', note),
        kind === 'correction' ? h('div', { class: 'muted small' }, `Сейчас по учёту: ${unitQty(it.quantity, it.unit)}`) : null),
      [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
        try { await api('POST', `/api/stock/items/${it.id}/move`, { kind, amount: amount.value, note: note.value }); closeModal(); toast('Записано'); load(); }
        catch (ex) { err.textContent = ex.message; err.style.display = ''; }
      } }, 'Записать')]);
      setTimeout(() => amount.focus(), 60);
    };
    const itemDialog = (it) => {
      const isNew = !it.id;
      const f = {
        name: h('input', { class: 'input', value: it.name || '', maxlength: 120, placeholder: 'Например: шампунь, пакеты для мусора' }),
        unit: h('input', { class: 'input', value: it.unit || 'шт', maxlength: 20 }),
        quantity: h('input', { class: 'input', type: 'number', min: 0, step: 'any', value: 0 }),
        min_quantity: h('input', { class: 'input', type: 'number', min: 0, step: 'any', value: Number(it.min_quantity || 0) }),
        norm_per_cleaning: h('input', { class: 'input', type: 'number', min: 0, step: 'any', value: Number(it.norm_per_cleaning || 0) }),
      };
      const err = h('div', { class: 'note bad', style: { display: 'none' } });
      openModal(isNew ? 'Новая позиция на складе' : it.name, h('div', {}, err, field('Название', f.name), row2(field('Единица', f.unit), isNew ? field('Сейчас на складе', f.quantity) : h('div')),
        row2(field('Предупредить, когда останется не больше', f.min_quantity), field('Списывать при каждой уборке номера', f.norm_per_cleaning)),
        h('div', { class: 'muted small' }, 'Норма на уборку: сколько уходит на один номер (например, 2 мыла). Когда горничная отмечает номер убранным, остаток уменьшается сам.')),
      [isNew ? null : h('button', { class: 'btn danger', onclick: async () => { if (!confirm('Убрать позицию со склада? История движений сохранится.')) return; try { await api('PATCH', `/api/stock/items/${it.id}`, { archived: true }); closeModal(); load(); } catch (ex) { bad(ex); } } }, 'Убрать'),
        h('span', { class: 'spacer' }), h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('button', { class: 'btn primary', onclick: async () => {
          const payload = { name: f.name.value, unit: f.unit.value, min_quantity: f.min_quantity.value, norm_per_cleaning: f.norm_per_cleaning.value };
          try { if (isNew) await api('POST', '/api/stock/items', { ...payload, quantity: f.quantity.value, property_id: state.propertyId }); else await api('PATCH', `/api/stock/items/${it.id}`, payload); closeModal(); toast('Сохранено'); load(); }
          catch (ex) { err.textContent = ex.message; err.style.display = ''; }
        } }, 'Сохранить')]);
    };
    const itemRow = (it) => h('div', { class: `stock-row${it.low ? ' low' : ''}` },
      h('div', { class: 'stock-name' }, h('b', {}, it.name), it.low ? h('span', { class: 'pill bad' }, 'заканчивается') : null,
        h('div', { class: 'muted small' }, [Number(it.min_quantity) ? `минимум ${qtyFmt(it.min_quantity)}` : null, Number(it.norm_per_cleaning) ? `на уборку ${qtyFmt(it.norm_per_cleaning)}` : null].filter(Boolean).join(' · '))),
      h('div', { class: 'stock-qty' }, qtyFmt(it.quantity), h('small', {}, ` ${it.unit}`)),
      h('div', { class: 'stock-act' }, h('button', { class: 'btn small', onclick: () => moveDialog(it, 'out') }, 'Взять'),
        d.can_edit ? h('button', { class: 'btn small', onclick: () => moveDialog(it, 'in') }, 'Приход') : null,
        d.can_edit ? h('button', { class: 'btn small ghost', onclick: () => moveDialog(it, 'writeoff') }, 'Списать') : null,
        d.can_edit ? h('button', { class: 'btn small ghost', onclick: () => moveDialog(it, 'correction') }, 'Пересчитать') : null,
        d.can_edit ? h('button', { class: 'btn small ghost', 'aria-label': 'Настроить', onclick: () => itemDialog(it) }, icon('settings')) : null));
    body.append(
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Расходники'), d.can_edit ? h('button', { class: 'btn small', onclick: () => itemDialog({}) }, icon('plus'), 'Позиция') : null),
        d.items.length ? h('div', { class: 'card-pad' }, d.items.map(itemRow))
          : h('div', { class: 'card-pad muted' }, 'Склад пуст. Добавьте мыло, шампунь, пакеты, бумагу — система будет списывать их при уборке и предупредит, когда пора докупить.')),
      d.moves.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Последние движения')),
        h('div', { class: 'card-pad' }, d.moves.map((m) => h('div', { class: 'move-row small' }, h('span', { class: 'muted' }, fmtDateTime(m.created_at)), h('b', {}, m.item_name),
          h('span', { class: Number(m.delta) < 0 ? 'down' : 'up' }, `${Number(m.delta) > 0 ? '+' : ''}${qtyFmt(m.delta)} ${m.unit}`), h('span', { class: 'muted' }, [KIND[m.kind], m.note, m.user_name].filter(Boolean).join(' · ')))))) : null);
  }

  // ---------------- счётчики ----------------
  async function drawMeters() {
    const d = await api('GET', '/api/meters?' + qs({ property_id: state.propertyId }));
    const readingDialog = (m) => {
      const last = m.last;
      const date = h('input', { class: 'input', type: 'date', value: todayISO() });
      const value = h('input', { class: 'input', type: 'number', step: 'any', min: 0, inputmode: 'decimal', placeholder: last ? `Было ${qtyFmt(last.value)}` : 'Текущее показание' });
      const replaced = h('input', { type: 'checkbox' });
      const preview = h('div', { class: 'muted small' });
      const err = h('div', { class: 'note bad', style: { display: 'none' } });
      const upd = () => {
        if (!last || value.value === '') { preview.textContent = last ? '' : 'Первое показание — точка отсчёта, расход начнёт считаться со следующего.'; return; }
        const cons = replaced.checked ? 0 : Number(value.value) - Number(last.value);
        preview.textContent = cons < 0 ? 'Меньше предыдущего — если счётчик заменили, отметьте это ниже.' : `Расход: ${qtyFmt(Math.round(cons * 1000) / 1000)} ${m.unit} · ${fmtMoney(cons * Number(m.tariff))} по тарифу ${qtyFmt(m.tariff)} ₽`;
      };
      value.addEventListener('input', upd); replaced.addEventListener('change', upd);
      openModal(`Показание: ${m.label}${m.room_name ? `, номер ${m.room_name}` : ''}`, h('div', {}, err, row2(field('Дата', date), field(`Показание (${m.unit})`, value)), preview,
        last ? h('label', { class: 'check', style: { marginTop: '8px' } }, replaced, ' Счётчик заменён (новое показание меньше прежнего)') : null,
        h('div', { class: 'muted small', style: { marginTop: '8px' } }, 'Расход по тарифу сам попадёт в «Финансы» → расходы («Коммунальные услуги»).'),
      ),
      [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
        try { const r = await api('POST', `/api/meters/${m.id}/readings`, { date: date.value, value: value.value, replaced: replaced.checked }); closeModal(); toast(Number(r.cost) ? `Записано. Расход ${fmtMoney(r.cost)} добавлен в финансы` : 'Записано'); load(); }
        catch (ex) { err.textContent = ex.message; err.style.display = ''; }
      } }, 'Записать')]);
      setTimeout(() => value.focus(), 60);
    };
    const historyDialog = async (m) => {
      const r = await api('GET', `/api/meters/${m.id}/readings`).catch((ex) => { bad(ex); return null; });
      if (!r) return;
      const list = r.readings.map((x, i) => h('div', { class: 'move-row small' }, h('span', { class: 'muted' }, fmtDate(x.date)), h('b', {}, `${qtyFmt(x.value)} ${r.meter.unit}`),
        h('span', {}, x.replaced ? 'счётчик заменён' : (Number(x.consumption) ? `+${qtyFmt(x.consumption)}` : '—')), h('span', { class: 'muted' }, Number(x.cost) ? fmtMoney(x.cost) : ''),
        i === 0 ? h('button', { class: 'link', onclick: async () => { if (!confirm('Удалить последнее показание? Созданный им расход тоже удалится.')) return; try { await api('DELETE', `/api/meter-readings/${x.id}`); closeModal(); load(); } catch (ex) { bad(ex); } } }, 'удалить') : h('span')));
      openModal(`История: ${m.label}`, h('div', {}, list.length ? list : h('div', { class: 'muted' }, 'Показаний пока нет.')), [h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: () => closeModal() }, 'Закрыть')]);
    };
    const meterDialog = (m) => {
      const isNew = !m.id;
      const kind = h('select', { class: 'input', disabled: !isNew, onchange: () => { if (!tariff.value) unit.textContent = d.kinds[kind.value].unit; } }, Object.entries(d.kinds).map(([k, v]) => h('option', { value: k, selected: m.kind === k }, `${v.label}, ${v.unit}`)));
      const room = h('select', { class: 'input', disabled: !isNew }, h('option', { value: '' }, 'Общий счётчик объекта'), d.rooms.map((r) => h('option', { value: r.id, selected: r.id === m.room_id }, `Номер ${r.name}`)));
      const name = h('input', { class: 'input', value: m.name || '', maxlength: 80, placeholder: 'Например: ванная, кухня (необязательно)' });
      const tariff = h('input', { class: 'input', type: 'number', min: 0, step: 'any', value: m.tariff != null ? Number(m.tariff) : '', placeholder: '₽ за единицу' });
      const unit = h('span', { class: 'hidden' });
      const err = h('div', { class: 'note bad', style: { display: 'none' } });
      openModal(isNew ? 'Новый счётчик' : `Счётчик: ${m.label}`, h('div', {}, err, field('Тип', kind), field('Где стоит', room), field('Название', name), field('Тариф, ₽ за единицу', tariff),
        h('div', { class: 'muted small' }, 'Тариф можно менять — старые показания не пересчитываются.')),
      [isNew ? null : h('button', { class: 'btn danger', onclick: async () => { if (!confirm('Убрать счётчик из списка? История показаний и расходов сохранится.')) return; try { await api('PATCH', `/api/meters/${m.id}`, { archived: true }); closeModal(); load(); } catch (ex) { bad(ex); } } }, 'Убрать'),
        h('span', { class: 'spacer' }), h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('button', { class: 'btn primary', onclick: async () => {
          try {
            if (isNew) await api('POST', '/api/meters', { kind: kind.value, room_id: room.value || null, name: name.value, tariff: tariff.value, property_id: state.propertyId });
            else await api('PATCH', `/api/meters/${m.id}`, { name: name.value, tariff: tariff.value });
            closeModal(); toast('Сохранено'); load();
          } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
        } }, 'Сохранить')]);
    };
    const card = (m) => {
      const total = m.monthly.reduce((s, x) => s + Number(x.consumption), 0);
      return h('div', { class: 'meter-card' },
        h('div', { class: 'meter-head' }, h('b', {}, m.label), h('span', { class: 'muted small' }, m.room_name ? `номер ${m.room_name}` : 'общий'), h('span', { class: 'spacer' }),
          h('button', { class: 'btn small ghost', 'aria-label': 'Настроить счётчик', onclick: () => meterDialog(m) }, icon('settings'))),
        h('div', { class: 'meter-val' }, m.last ? [qtyFmt(m.last.value), h('small', {}, ` ${m.unit}`)] : h('span', { class: 'muted' }, 'нет показаний'),
          m.last ? h('div', { class: 'muted small' }, `на ${fmtDate(m.last.date)}${Number(m.last.consumption) ? ` · +${qtyFmt(m.last.consumption)} ${m.unit}` : ''}`) : null),
        m.monthly.length ? h('div', { class: 'muted small' }, `За 6 месяцев: ${qtyFmt(Math.round(total * 100) / 100)} ${m.unit}, ${fmtMoney(m.monthly.reduce((s, x) => s + Number(x.cost), 0))}`) : null,
        h('div', { class: 'muted small' }, `Тариф: ${qtyFmt(m.tariff)} ₽`),
        h('div', { class: 'meter-act' }, h('button', { class: 'btn small primary', onclick: () => readingDialog(m) }, 'Показание'), h('button', { class: 'btn small ghost', onclick: () => historyDialog(m) }, 'История')));
    };
    body.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Счётчики'), h('button', { class: 'btn small', onclick: () => meterDialog({}) }, icon('plus'), 'Счётчик')),
      h('div', { class: 'card-pad' }, d.meters.length ? h('div', { class: 'meter-grid' }, d.meters.map(card))
        : h('div', { class: 'muted' }, 'Добавьте счётчики воды, электричества, газа или отопления. Раз в месяц вносите показания — система посчитает расход, умножит на тариф и сама запишет расход в «Финансы».')),
      d.meters.length ? h('div', { class: 'card-pad' }, h('button', { class: 'btn small ghost', onclick: async () => {
        try { await api('POST', '/api/tasks', { title: 'Снять показания счётчиков', recurrence: 'monthly', due_date: todayISO(), description: 'Хозяйство → Счётчики → «Показание»' }); toast('Задача «Снять показания» будет повторяться каждый месяц'); } catch (ex) { bad(ex); }
      } }, 'Напоминать каждый месяц (задача)')) : null));
  }

  // ---------------- инвентарь ----------------
  async function drawInventory() {
    const hk = await api('GET', '/api/housekeeping?' + qs({ property_id: state.propertyId }));
    const rooms = hk.rooms;
    if (!rooms.length) { body.append(h('div', { class: 'card empty' }, 'В объекте нет номеров.')); return; }
    let roomId = store.get('hh_room');
    if (!rooms.some((r) => r.id === roomId)) roomId = rooms[0].id;
    const sel = h('select', { class: 'input', style: { maxWidth: '260px' }, onchange: () => { roomId = sel.value; store.set('hh_room', roomId); drawRoom(); } }, rooms.map((r) => h('option', { value: r.id, selected: r.id === roomId }, `Номер ${r.name} · ${r.type}`)));
    const area = h('div', { class: 'stack' });
    body.append(h('div', { class: 'board-tools' }, sel), area);
    async function drawRoom() {
      const inv = await api('GET', `/api/rooms/${roomId}/inventory`);
      const checks = (await api('GET', `/api/rooms/${roomId}/inventory-checks`)).checks;
      const name = h('input', { class: 'input', placeholder: 'Например: чайник, фен, плед', maxlength: 120 });
      const qty = h('input', { class: 'input', type: 'number', min: 1, value: 1, style: { width: '90px' } });
      const add = async () => { if (!name.value.trim()) return; try { await api('POST', `/api/rooms/${roomId}/inventory`, { name: name.value, qty: qty.value }); drawRoom(); } catch (ex) { bad(ex); } };
      name.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); });
      area.innerHTML = '';
      area.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, `Что в номере ${inv.room.name}`),
        inv.items.length ? h('button', { class: 'btn small', title: 'Добавить недостающие позиции во все остальные номера этой категории', onclick: async () => {
          try { const r = await api('POST', `/api/rooms/${roomId}/inventory/copy`, {}); toast(r.added ? `Скопировано в ${r.rooms} ${r.rooms === 1 ? 'номер' : 'номеров'}: ${r.added} позиций` : 'Во всех номерах категории уже есть такой список'); } catch (ex) { bad(ex); }
        } }, 'Скопировать в номера категории') : null),
      h('div', { class: 'card-pad' }, inv.items.map((it) => h('div', { class: 'inv-edit' }, h('b', {}, it.name), h('span', { class: 'muted' }, `× ${it.qty}`),
        h('button', { class: 'btn small ghost', onclick: async () => { const v = prompt(`${it.name}: сколько штук?`, it.qty); if (v === null) return; try { await api('PATCH', `/api/inventory/${it.id}`, { qty: v }); drawRoom(); } catch (ex) { bad(ex); } } }, 'Количество'),
        h('button', { class: 'btn small ghost', 'aria-label': `Удалить ${it.name}`, onclick: async () => { try { await api('DELETE', `/api/inventory/${it.id}`); drawRoom(); } catch (ex) { bad(ex); } } }, icon('trash'))),
      ), inv.items.length ? null : h('div', { class: 'muted', style: { marginBottom: '10px' } }, 'Список пуст. Внесите вещи, которые должны быть в номере, — после выезда горничная пройдётся по списку, а о пропаже или поломке вам придёт задача.'),
      h('div', { class: 'inv-add' }, name, qty, h('button', { class: 'btn primary', onclick: add }, icon('plus'), 'Добавить')))),
      checks.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Проверки после выезда')),
        h('div', { class: 'card-pad' }, checks.map((k) => h('div', { class: 'move-row small' }, h('span', { class: 'muted' }, fmtDateTime(k.created_at)), h('b', {}, k.user_name || '—'),
          k.problems ? h('span', { class: 'down' }, k.items.map((i) => `${i.name} (${i.state === 'missing' ? 'нет' : 'сломано'})`).join(', ')) : h('span', { class: 'up' }, 'всё на месте'))))) : null);
    }
    await drawRoom();
  }

  async function load() {
    body.innerHTML = '';
    if (manager) drawSeg();
    try { await ({ stock: drawStock, meters: drawMeters, inventory: drawInventory }[tab])(); } catch (ex) { body.append(h('div', { class: 'card empty' }, ex.message)); }
  }
  load();
}
