// Флигель — интерфейс администратора (раздел «уборка»). ES-модуль без сборки.
import { autoRefresh } from './app.js';
import { inventoryCheckDialog } from './household.js';
import { api, can, closeModal, fmtDate, h, openModal, qs, state, store, toast } from './core.js';

// ---------- уборка ----------
export const HK = { clean: 'Чистый', dirty: 'Нужна уборка', cleaning: 'Убирают', inspect: 'Ждёт проверки', repair: 'Ремонт', occupied: 'Заселён' };
export const HK_ORDER = ['dirty', 'cleaning', 'inspect', 'repair', 'clean', 'occupied'];

export async function viewCleaning(main) {
  const manager = can('manager');
  const mineOnly = { value: store.get('hk_mine') === '1' };
  const box = h('div', { class: 'stack' });
  const sum = h('div', { class: 'hk-sum' });
  const mineBtn = h('button', { class: 'btn', type: 'button', onclick: () => { mineOnly.value = !mineOnly.value; store.set('hk_mine', mineOnly.value ? '1' : '0'); draw(); } });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Уборка'), mineBtn), sum, box);
  let data = null;
  const setStatus = async (room, status, note) => {
    try { await api('POST', `/api/rooms/${room.id}/status`, { status, note }); await load(); }
    catch (ex) { toast(ex.message, true); }
  };
  const repairDialog = (room) => {
    const note = h('textarea', { class: 'input', placeholder: 'Что случилось: течёт кран, не работает розетка, разбито окно…' });
    const err = h('div', { class: 'note bad', style: { display: 'none' } });
    openModal(`Поломка в номере ${room.name}`, h('div', {}, err, h('label', { class: 'field' }, h('span', {}, 'Что сломалось'), note),
      h('p', { class: 'muted small', style: { marginBottom: 0 } }, 'Администратор сразу увидит сообщение в колокольчике и (если подключён) в Telegram.')),
    [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
      try { await api('POST', `/api/rooms/${room.id}/status`, { status: 'repair', note: note.value }); closeModal(); toast('Сообщение отправлено'); load(); }
      catch (ex) { err.textContent = ex.message; err.style.display = ''; }
    } }, 'Сообщить')]);
  };
  const noteDialog = (room) => {
    const note = h('textarea', { class: 'input', placeholder: 'Ключ у соседей, диван раскладывается, не включать кондиционер…' }, room.note || '');
    openModal(`Заметка к номеру ${room.name}`, h('div', {}, h('label', { class: 'field' }, h('span', {}, 'Видят все сотрудники'), note)),
      [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
        try { await api('PUT', `/api/rooms/${room.id}/note`, { note: note.value }); closeModal(); load(); } catch (ex) { toast(ex.message, true); }
      } }, 'Сохранить')]);
  };
  const actions = (room) => {
    const b = (label, cls, fn) => h('button', { class: `btn small ${cls || ''}`, type: 'button', onclick: fn }, label);
    const out = [];
    if (room.status === 'dirty') out.push(b('Начать уборку', '', () => setStatus(room, 'cleaning')), b('Убрано', 'primary', () => setStatus(room, 'clean')));
    if (room.status === 'cleaning') out.push(b('Убрано', 'primary', () => setStatus(room, 'clean')), b('На проверку', '', () => setStatus(room, 'inspect')));
    if (room.status === 'inspect') out.push(manager ? b('Проверено', 'primary', () => setStatus(room, 'clean')) : h('span', { class: 'muted small' }, 'Ждёт проверки администратором'), b('Переделать', '', () => setStatus(room, 'dirty')));
    if (room.status === 'repair') out.push(manager ? b('Исправлено', 'primary', () => setStatus(room, 'dirty')) : null);
    if (room.status === 'clean' || room.status === 'occupied') out.push(b('Нужна уборка', 'ghost', () => setStatus(room, 'dirty')));
    if (room.status !== 'repair') out.push(b('Проверить инвентарь', 'ghost', () => inventoryCheckDialog(room)), b('Поломка', 'ghost', () => repairDialog(room)));
    if (manager) out.push(b(room.note ? 'Заметка' : '+ Заметка', 'ghost', () => noteDialog(room)));
    return out;
  };
  const roomCard = (room) => h('div', { class: `hk-card hk-${room.status}` },
    h('div', { class: 'hk-head' }, h('b', { class: 'hk-name' }, room.name), h('span', { class: 'muted small' }, room.type), h('span', { class: `hk-pill hk-${room.status}` }, HK[room.status])),
    h('div', { class: 'hk-tags' },
      room.arrives_today ? h('span', { class: 'tag warn' }, 'заезд сегодня') : (room.next_arrival ? h('span', { class: 'tag' }, `заезд ${fmtDate(room.next_arrival)}`) : null),
      room.departs_today ? h('span', { class: 'tag' }, `выезд${room.departing ? ': ' + room.departing : ''}`) : null,
      room.assigned_name ? h('span', { class: 'tag' }, `убирает: ${room.assigned_name}`) : null),
    room.hk_note ? h('div', { class: 'note bad', style: { margin: '8px 0 0' } }, room.hk_note) : null,
    room.note ? h('div', { class: 'hk-note' }, room.note) : null,
    h('div', { class: 'hk-actions' }, ...actions(room).filter(Boolean)),
    manager && data.housekeepers.length && room.status !== 'occupied' ? h('select', { class: 'input hk-assign', 'aria-label': 'Назначить горничной', onchange: async (e) => {
      try { await api('POST', '/api/housekeeping/assign', { room_ids: [room.id], user_id: e.target.value || null }); load(); } catch (ex) { toast(ex.message, true); }
    } }, h('option', { value: '' }, 'Не назначено'), data.housekeepers.map((u) => h('option', { value: u.id, selected: u.id === room.assigned_to }, u.name))) : null);
  function draw() {
    if (!data) return;
    mineBtn.textContent = mineOnly.value ? 'Показать все номера' : 'Только мои номера';
    mineBtn.style.display = data.rooms.some((r) => r.assigned_to === data.me) ? '' : 'none';
    sum.innerHTML = '';
    HK_ORDER.forEach((k) => { if (data.counts[k]) sum.append(h('span', { class: `hk-pill hk-${k}` }, `${HK[k]}: ${data.counts[k]}`)); });
    box.innerHTML = '';
    let rooms = data.rooms;
    if (mineOnly.value) rooms = rooms.filter((r) => r.assigned_to === data.me);
    const urgency = (r) => (r.arrives_today ? 0 : 1);
    HK_ORDER.forEach((k) => {
      const list = rooms.filter((r) => r.status === k).sort((a, b2) => urgency(a) - urgency(b2));
      if (!list.length) return;
      box.append(h('div', {}, h('h2', { class: 'hk-title' }, `${HK[k]} · ${list.length}`), h('div', { class: 'hk-grid' }, list.map(roomCard))));
    });
    if (!rooms.length) box.append(h('div', { class: 'card empty' }, h('h3', {}, 'Номеров нет'), 'Номера добавляются в «Настройках».'));
  }
  async function load() { data = await api('GET', '/api/housekeeping?' + qs({ property_id: state.propertyId })); draw(); }
  load().catch((ex) => box.append(h('div', { class: 'card empty' }, ex.message)));
  autoRefresh(load);
}
