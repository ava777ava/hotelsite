// Флигель — интерфейс администратора (раздел «список броней»). ES-модуль без сборки.
import { refreshBadges, scopeSeg } from './app.js';
import { bookingDrawer } from './booking.js';
import { SOURCE, STATUS, addDays, api, can, closeModal, downloadCsv, fmtMoney, fmtShort, h, icon, openModal, qs, state, store, toast, toastUndo, todayISO } from './core.js';
import { count, humanDay, skeleton } from './ui.js';

// ---------- список броней ----------
export async function viewBookings(main) {
  const scope = { value: 'current' };
  const f = {
    q: h('input', { class: 'input search-field', placeholder: 'Имя, телефон или email', style: { width: '240px' } }),
    from: h('input', { class: 'input', type: 'date', value: addDays(todayISO(), -7), style: { width: '150px' } }),
    to: h('input', { class: 'input', type: 'date', value: addDays(todayISO(), 60), style: { width: '150px' } }),
    status: h('select', { class: 'input', style: { width: '170px' } }, h('option', { value: '' }, 'Все активные'),
      Object.entries(STATUS).map(([k, l]) => h('option', { value: k, selected: k === store.get('bk_status', '') }, l))),
  };
  let chip = store.get('bk_chip', 'all');
  const chips = h('div', { class: 'type-filter' });
  const drawChips = () => {
    chips.innerHTML = '';
    [['all', 'Все'], ['requests', 'Заявки с сайта'], ['debt', 'Должны оплатить'], ['arrive', 'Заезжают сегодня']].forEach(([k, l]) => chips.append(h('button', { type: 'button', class: 'chip' + (chip === k ? ' on' : ''),
      onclick: () => { chip = k; store.set('bk_chip', k); drawChips(); shown = PAGE; draw(); } }, l)));
  };
  const table = h('div', { class: 'card' });
  let timer;
  Object.values(f).forEach((el) => el.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 250); }));
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Брони'),
    h('button', { class: 'btn', onclick: () => downloadCsv('/api/bookings/export.csv?' + qs({
      q: f.q.value, from: f.from.value, to: f.to.value, status: f.status.value,
      property_id: scope.value === 'current' ? state.propertyId : undefined }), `bookings_${f.from.value}_${f.to.value}.csv`) }, icon('download'), 'CSV'),
    h('button', { class: 'btn', onclick: () => importDialog(load) }, icon('upload'), 'Импорт'),
    h('button', { class: 'btn primary', onclick: () => bookingDrawer({}, load) }, icon('plus'), 'Бронь')),
  h('div', { class: 'board-tools', style: { marginBottom: '10px' } }, f.q, f.from, '—', f.to, f.status, scopeSeg(scope, () => load())), chips, table);
  const PAGE = 50;
  let shown = PAGE;
  let all = [];
  let rows = [];
  const draw = () => {
    table.innerHTML = '';
    const today = todayISO();
    rows = all.filter((b) => (chip === 'requests' ? b.status === 'pending' && b.source === 'direct'
      : chip === 'debt' ? b.status === 'confirmed' && Number(b.total_price) > Number(b.paid_amount)
      : chip === 'arrive' ? b.check_in === today && b.status !== 'cancelled' && b.status !== 'blocked' : true));
    if (!rows.length) {
      table.append(h('div', { class: 'empty' }, h('h3', {}, all.length ? 'В этом разделе пусто' : 'Броней не найдено'),
        all.length ? 'Нажмите «Все», чтобы увидеть остальные брони периода.' : 'Измените период или поиск — или создайте бронь.',
        h('div', { style: { marginTop: '12px' } }, can('manager') ? h('button', { class: 'btn primary', onclick: () => bookingDrawer({}, load) }, icon('plus'), 'Создать бронь') : null)));
      return;
    }
    const part = rows.slice(0, shown);
    const multi = scope.value === 'all';
    table.append(...[
      h('div', { class: 'card-head' }, h('h2', {}, 'Найдено броней'), h('span', { class: 'pill none num' }, rows.length)),
      h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' },
        h('thead', {}, h('tr', {}, [multi ? 'Объект' : null, 'Заезд', 'Выезд', 'Номер', 'Гость', 'Источник', 'Статус', 'Сумма', 'Оплачено', ''].filter((t) => t !== null).map((t) => h('th', {}, t)))),
        h('tbody', {}, part.map((b) => h('tr', { class: 'click', onclick: () => bookingDrawer(b, load) },
          multi ? h('td', { class: 'muted small', 'data-l': 'Объект' }, b.property_name) : null,
          h('td', { class: 'num', 'data-l': 'Заезд' }, fmtShort(b.check_in), h('div', { class: 'muted small' }, humanDay(b.check_in))), h('td', { class: 'num', 'data-l': 'Выезд' }, fmtShort(b.check_out)),
          h('td', { class: 'num', 'data-l': 'Номер' }, b.room_name),
          h('td', { 'data-l': 'Гость' }, b.status === 'blocked' ? h('span', { class: 'muted' }, 'Закрыто') : (b.guest_name || h('span', { class: 'muted' }, '—')),
            b.guest_phone ? h('div', { class: 'muted small nowrap' }, b.guest_phone) : null),
          h('td', { 'data-l': 'Источник' }, h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: '6px' } }, h('i', { class: 'dot', style: { background: `var(--src-${b.source})` } }), SOURCE[b.source])),
          h('td', { 'data-l': 'Статус' }, h('span', { class: 'pill ' + ({ confirmed: 'ok', pending: 'warn', blocked: 'none', cancelled: 'bad' }[b.status]) }, STATUS[b.status])),
          h('td', { class: 'num', 'data-l': b.status === 'blocked' ? null : 'Сумма' }, b.status === 'blocked' ? '' : fmtMoney(b.total_price)),
          h('td', { class: 'num', 'data-l': b.status === 'blocked' ? null : 'Оплачено' }, b.status === 'blocked' ? '' : fmtMoney(b.paid_amount)),
          h('td', { class: 'wide row-actions' }, b.status === 'pending' && !b.feed_id ? [
            h('button', { class: 'btn small primary', onclick: async (e) => {
              e.stopPropagation();
              try {
                await api('PATCH', `/api/bookings/${b.id}`, { status: 'confirmed' }); load(); refreshBadges();
                toastUndo('Бронь подтверждена', () => api('PATCH', `/api/bookings/${b.id}`, { status: 'pending' }), () => { load(); refreshBadges(); });
              } catch (ex) { toast(ex.message, true); }
            } }, 'Подтвердить'),
            h('button', { class: 'btn small ghost danger', onclick: async (e) => {
              e.stopPropagation();
              try {
                await api('DELETE', `/api/bookings/${b.id}`); load(); refreshBadges();
                toastUndo(`Заявка${b.guest_name ? ` от «${b.guest_name}»` : ''} отклонена, номер освободился`, () => api('PATCH', `/api/bookings/${b.id}`, { status: 'pending' }), () => { load(); refreshBadges(); });
              } catch (ex) { toast(ex.message, true); }
            } }, 'Отклонить')] : null)))))),
      rows.length > shown ? h('div', { class: 'more-count' }, h('button', { class: 'btn', onclick: () => { shown += PAGE; draw(); } },
        `Показать ещё (${Math.min(PAGE, rows.length - shown)} из ${rows.length - shown} оставшихся)`)) : null,
    ].filter(Boolean));
  };
  async function load() {
    store.set('bk_status', f.status.value);
    if (!all.length) { table.innerHTML = ''; table.append(skeleton(6)); }
    try {
      all = await api('GET', '/api/bookings?' + qs({
        q: f.q.value, from: f.from.value, to: f.to.value, status: f.status.value,
        property_id: scope.value === 'current' ? state.propertyId : undefined,
      }));
      shown = PAGE;
      draw();
    } catch (ex) { table.innerHTML = ''; table.append(h('div', { class: 'empty' }, ex.message)); }
  }
  drawChips();
  load();
}

// Импорт броней из CSV: сначала проверка (ничего не сохраняется), потом настоящий импорт
export function importDialog(onDone) {
  let text = '';
  const info = h('div', { class: 'muted small' }, 'Файл не выбран');
  const report = h('div', {});
  const go = h('button', { class: 'btn primary', disabled: true }, 'Проверить файл');
  let checked = false;
  const file = h('input', { type: 'file', accept: '.csv,.txt,text/csv', style: { display: 'none' }, onchange: async () => {
    const f = file.files[0]; if (!f) return;
    if (f.size > 1_500_000) { toast('Файл слишком большой (максимум 1,5 МБ)', true); return; }
    text = await f.text(); checked = false; report.innerHTML = '';
    info.textContent = `Выбран файл: ${f.name}`; go.textContent = 'Проверить файл'; go.disabled = false;
  } });
  const show = (r) => {
    report.innerHTML = '';
    report.append(h('div', { class: 'note ' + (r.created ? 'ok' : 'bad'), style: { margin: '12px 0 8px' } },
      r.dry_run ? `Можно загрузить броней: ${r.created} из ${r.total}.` : `Загружено броней: ${r.created} из ${r.total}.`,
      r.skipped ? ` Пропущено: ${r.skipped}.` : ''));
    if (r.errors.length) report.append(h('div', { class: 'table-wrap', style: { maxHeight: '220px', overflow: 'auto' } },
      h('table', { class: 'list' }, h('tbody', {}, r.errors.map((e) => h('tr', {}, h('td', { class: 'num' }, `строка ${e.line}`), h('td', {}, e.error)))))));
  };
  go.addEventListener('click', async () => {
    go.disabled = true;
    try {
      const r = await api('POST', '/api/bookings/import', { csv: text, dry_run: !checked, property_id: state.propertyId });
      show(r);
      if (r.dry_run) {
        checked = true; go.textContent = r.created ? `Загрузить ${r.created} бронь(ей)` : 'Проверить заново'; go.disabled = !r.created;
        if (!r.created) { checked = false; go.disabled = false; }
      } else { go.textContent = 'Готово'; toast(`Загружено броней: ${r.created}`); onDone?.(); refreshBadges?.(); }
    } catch (ex) { toast(ex.message, true); go.disabled = false; checked = false; }
  });
  openModal('Импорт броней из CSV', h('div', {},
    h('p', { class: 'muted small', style: { marginTop: 0 } },
      'Переезжаете из Excel или другой системы? Сохраните таблицу как CSV: нужны колонки «Заезд», «Выезд» и «Номер» (название номера из «Настроек»); необязательно — «Гость», «Телефон», «Email», «Гостей», «Источник», «Стоимость», «Оплачено», «Комментарий». Если стоимость не указана, она посчитается по тарифам. Брони загрузятся в выбранный объект как подтверждённые; пересекающиеся с уже существующими будут пропущены.'),
    h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' } },
      h('button', { class: 'btn', type: 'button', onclick: () => file.click() }, icon('upload'), 'Выбрать файл'),
      h('button', { class: 'btn ghost', type: 'button', onclick: () => downloadCsv('/api/bookings/import-template.csv', 'bookings_template.csv') }, icon('download'), 'Скачать образец'),
      info, file),
    report),
  [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Закрыть'), h('span', { class: 'spacer' }), go]);
}
