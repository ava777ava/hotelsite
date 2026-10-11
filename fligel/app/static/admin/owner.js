// Флигель — интерфейс администратора (раздел «собственники и журнал»). ES-модуль без сборки.
import { SOURCE, api, can, downloadCsv, fmtDateTime, fmtMoney, fmtShort, h, icon, pad, printNode, qs, state, store, toast } from './core.js';
import { kpiCard } from './reports.js';

// ---------- отчёт собственнику ----------
export async function viewOwnerReport(main) {
  const landlord = state.me.role === 'landlord';
  const props = await api('GET', '/api/landlord/properties');
  const now = new Date();
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const monthInput = h('input', { class: 'input', type: 'month', value: store.get('or_month') || `${prev.getFullYear()}-${pad(prev.getMonth() + 1)}`, style: { width: '170px' } });
  const sel = h('select', { class: 'input', style: { width: '240px' } }, props.map((p) => h('option', { value: p.id, selected: p.id === state.propertyId }, p.name)));
  const box = h('div', { class: 'stack' });
  const csvBtn = h('button', { class: 'btn', onclick: () => downloadCsv('/api/landlord/report?' + qs({ property_id: sel.value, month: monthInput.value, format: 'csv' }), `owner_report_${monthInput.value}.csv`) }, icon('download'), 'CSV');
  const printBtn = h('button', { class: 'btn', onclick: () => printNode(box) }, icon('print'), 'Печать');
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Отчёт собственнику'), csvBtn, printBtn),
    h('div', { class: 'board-tools no-print', style: { marginBottom: '14px' } }, props.length > 1 ? sel : null, monthInput), box);
  if (!props.length) { box.append(h('div', { class: 'card empty' }, h('h3', {}, 'Нет доступных объектов'), landlord ? 'Попросите владельца сервиса открыть вам доступ к объекту.' : 'Добавьте объект в «Настройках».')); return; }
  const line = (label, value, cls, hint) => h('div', { class: 'or-line ' + (cls || '') }, h('span', {}, label, hint ? h('small', {}, hint) : null), h('b', {}, value));
  async function load() {
    store.set('or_month', monthInput.value);
    box.innerHTML = '';
    box.append(h('div', { class: 'card empty' }, h('span', { class: 'spin' }), 'Считаю…'));
    let r;
    try { r = await api('GET', '/api/landlord/report?' + qs({ property_id: sel.value, month: monthInput.value })); }
    catch (ex) { box.innerHTML = ''; box.append(h('div', { class: 'card empty' }, ex.message)); return; }
    box.innerHTML = '';
    const mcLabel = `Комиссия управляющей компании ${Number(r.mc_percent)}%`;
    box.append(
      h('div', { class: 'or-head print-only' }, h('h2', {}, r.property.name), h('div', { class: 'muted' }, `${r.property.address || ''} · отчёт за ${monthInput.value}`)),
      h('div', { class: 'kpis' }, kpiCard('К выплате собственнику', fmtMoney(r.payout)), kpiCard('Загрузка', `${r.occupancy}%`), kpiCard('Ночей продано', String(r.sold_nights)), kpiCard('Средняя цена ночи', fmtMoney(r.adr))),
      h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '10px' } }, 'Как получилась сумма'),
        line('Выручка от проживания', fmtMoney(r.revenue), '', 'по ночам месяца'),
        line('− Комиссии площадок', `−${fmtMoney(r.platform_commission)}`),
        line('= Чистая выручка', fmtMoney(r.net_revenue), 'sub'),
        Number(r.other_incomes) ? line('+ Прочие доходы объекта', fmtMoney(r.other_incomes)) : null,
        line('− Расходы объекта', `−${fmtMoney(r.expenses_total)}`, '', 'общие расходы компании сюда не входят'),
        Number(r.mc_percent) ? line(`− ${mcLabel}`, `−${fmtMoney(r.mc_commission)}`, '', r.mc_base === 'gross' ? 'от выручки' : 'от чистой выручки') : null,
        line('К выплате', fmtMoney(r.payout), 'total')),
      r.expenses.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Расходы объекта')),
        h('table', { class: 'list' }, h('tbody', {}, r.expenses.map((e) => h('tr', {}, h('td', {}, h('i', { class: 'dot', style: { background: e.color, marginRight: '8px' } }), e.name), h('td', { class: 'num' }, fmtMoney(e.amount))))))) : null,
      r.by_source.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'По источникам')),
        h('table', { class: 'list' }, h('thead', {}, h('tr', {}, ['Источник', 'Броней', 'Ночей', 'Выручка', 'Комиссия'].map((t) => h('th', {}, t)))),
          h('tbody', {}, r.by_source.map((x) => h('tr', {}, h('td', {}, x.label), h('td', { class: 'num' }, x.bookings), h('td', { class: 'num' }, x.nights), h('td', { class: 'num' }, fmtMoney(x.revenue)), h('td', { class: 'num' }, fmtMoney(x.commission))))))) : null,
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Проживания в месяце'), h('span', { class: 'pill none num' }, r.stays.length)),
        r.stays.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' }, h('thead', {}, h('tr', {}, ['Заезд', 'Выезд', 'Номер', 'Гость', 'Источник', 'Ночей', 'Выручка'].map((t) => h('th', {}, t)))),
          h('tbody', {}, r.stays.map((x) => h('tr', {}, h('td', { 'data-l': 'Заезд' }, fmtShort(x.check_in)), h('td', { 'data-l': 'Выезд' }, fmtShort(x.check_out)), h('td', { 'data-l': 'Номер' }, x.room_name),
            h('td', { 'data-l': 'Гость' }, x.guest), h('td', { 'data-l': 'Источник' }, SOURCE[x.source]), h('td', { class: 'num', 'data-l': 'Ночей' }, x.nights_in), h('td', { class: 'num', 'data-l': 'Выручка' }, fmtMoney(x.revenue)))))))
          : h('div', { class: 'empty' }, 'В этом месяце проживаний не было.')));
    if (can('owner')) {
      const pct = h('input', { class: 'input', type: 'number', min: 0, max: 100, step: '0.5', value: Number(r.mc_percent), style: { width: '110px' } });
      const base = h('select', { class: 'input', style: { width: '260px' } }, h('option', { value: 'net', selected: r.mc_base === 'net' }, 'от чистой выручки (после комиссий площадок)'), h('option', { value: 'gross', selected: r.mc_base === 'gross' }, 'от выручки (до комиссий площадок)'));
      box.append(h('div', { class: 'card card-pad no-print' }, h('h2', { style: { marginBottom: '6px' } }, 'Комиссия управляющей компании'),
        h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Если вы управляете чужими объектами: процент, который удерживает управляющая компания, и от какой суммы он считается. Собственники видят это в своём отчёте.'),
        h('div', { class: 'money-actions' }, pct, '%', base, h('button', { class: 'btn primary', onclick: async () => {
          try { await api('PUT', `/api/properties/${sel.value}/commission`, { percent: pct.value || 0, base: base.value }); toast('Сохранено'); load(); } catch (ex) { toast(ex.message, true); }
        } }, 'Сохранить'))));
    }
  }
  sel.addEventListener('change', load); monthInput.addEventListener('change', load);
  load();
}

// Журнал действий (для владельца): кто, что и когда
export async function viewAudit(main) {
  const card = h('div', { class: 'card' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Журнал действий')),
    h('p', { class: 'muted', style: { marginTop: '-6px' } }, 'Кто что менял: брони, платежи, цены, доступы сотрудников, подключения площадок.'), card);
  let before = null;
  const rows = h('div', { class: 'day-list' });
  const more = h('div', { style: { padding: '12px', textAlign: 'center' } });
  card.append(rows, more);
  async function load() {
    const r = await api('GET', '/api/audit?' + qs({ before }));
    if (!r.items.length && !before) { rows.append(h('div', { class: 'empty' }, h('h3', {}, 'Журнал пока пуст'), 'Записи появятся, как только вы или сотрудники начнут работать.')); return; }
    r.items.forEach((i) => rows.append(h('div', { class: 'item audit-item' },
      h('div', { class: 'audit-when muted small' }, fmtDateTime(i.created_at)), h('div', { style: { flex: 1, minWidth: 0 } }, h('div', {}, i.text), h('div', { class: 'muted small' }, i.who)))));
    more.innerHTML = '';
    if (r.more && r.items.length) { before = r.items[r.items.length - 1].created_at; more.append(h('button', { class: 'btn', onclick: load }, 'Показать ещё')); }
  }
  load().catch((ex) => rows.append(h('div', { class: 'empty' }, ex.message)));
}
