// Флигель — интерфейс администратора (раздел «аналитика»: прогноз, темп, каналы, сводка бухгалтеру). ES-модуль без сборки.
import { scopeSeg } from './app.js';
import { api, downloadCsv, fmtMoney, h, pad, qs, state, store } from './core.js';
import { plural } from './ui.js';

const TABS = [['forecast', 'Прогноз'], ['pace', 'Темп и окно брони'], ['channels', 'Каналы'], ['accountant', 'Бухгалтеру']];
const fmtPct = (v) => (v == null ? '—' : `${String(v).replace('.', ',')} %`);
const signed = (v, suffix = ' %') => (v == null ? '—' : `${v > 0 ? '+' : ''}${String(v).replace('.', ',')}${suffix}`);
const deltaClass = (v) => (v == null || v === 0 ? 'muted' : (v > 0 ? 'up' : 'down'));
const nights = (n) => `${n} ${plural(n, ['ночь', 'ночи', 'ночей'])}`;
const bookingsWord = (n) => `${n} ${plural(n, ['бронь', 'брони', 'броней'])}`;

const card = (title, ...body) => h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, title)), h('div', { class: 'card-pad' }, ...body));
const tableCard = (title, head, rows, note) => h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, title)),
  h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('thead', {}, h('tr', {}, head.map((x, i) => h('th', { class: i ? 'num' : '' }, x)))), h('tbody', {}, rows))),
  note ? h('div', { class: 'card-pad muted small' }, note) : null);
const num = (v) => h('td', { class: 'num' }, v);

export async function viewAnalytics(main) {
  let tab = store.get('an_tab') || 'forecast';
  const scope = { value: 'current' };
  const body = h('div', { class: 'stack' });
  const seg = h('div', { class: 'seg' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Аналитика'), state.me.properties.length > 1 ? scopeSeg(scope, () => load()) : null),
    h('div', { class: 'seg-scroll' }, seg), body);
  const params = (extra = {}) => qs({ property_id: scope.value === 'all' ? '' : state.propertyId, ...extra });
  const drawSeg = () => {
    seg.innerHTML = '';
    TABS.forEach(([k, l]) => seg.append(h('button', { type: 'button', class: tab === k ? 'on' : '', onclick: () => { tab = k; store.set('an_tab', k); drawSeg(); load(); } }, l)));
  };

  // ---- прогноз ----
  function forecastCard(x) {
    const ya = x.year_ago_pace;
    const fin = x.year_ago_final;
    return h('div', { class: 'card forecast' }, h('div', { class: 'card-head' }, h('h2', {}, `Ближайшие ${x.days} дней`)),
      h('div', { class: 'card-pad' },
        h('div', { class: 'fc-main' }, h('div', {}, h('div', { class: 'muted small' }, 'Загрузка'), h('div', { class: 'fc-big' }, fmtPct(x.occupancy))),
          h('div', {}, h('div', { class: 'muted small' }, 'Выручка по броням'), h('div', { class: 'fc-big' }, fmtMoney(x.revenue)))),
        h('div', { class: 'muted small' }, `${nights(x.sold_nights)} из ${x.room_nights} возможных · средняя цена ночи ${fmtMoney(x.adr)}`),
        h('div', { class: 'fc-cmp' },
          ya ? h('div', {}, 'На эту дату год назад было: ', h('b', {}, `${fmtPct(ya.occupancy)}, ${fmtMoney(ya.revenue)}`), ' ',
            h('span', { class: deltaClass(x.revenue_vs_pace) }, `(выручка ${signed(x.revenue_vs_pace)})`)) : h('div', { class: 'muted small' }, 'На эту дату год назад — нет данных: система работает меньше года.'),
          fin ? h('div', {}, 'Чем закончился тот период год назад: ', h('b', {}, `${fmtPct(fin.occupancy)}, ${fmtMoney(fin.revenue)}`), ' ',
            h('span', { class: deltaClass(x.revenue_vs_final) }, `(сейчас ${signed(x.revenue_vs_final)} от итога)`)) : null)));
  }
  async function drawForecast() {
    const d = await api('GET', '/api/analytics/forecast?' + params());
    if (!d.horizons.some((x) => x.sold_nights > 0)) {
      body.append(h('div', { class: 'card empty' }, h('h3', {}, 'Пока нечего прогнозировать'), 'Как только появятся брони на ближайшие дни, здесь будут загрузка и выручка вперёд — со сравнением с прошлым годом.'));
      return;
    }
    body.append(h('p', { class: 'muted' }, `Что уже забронировано впереди (номеров: ${d.rooms}). Цифры растут по мере новых броней — сравните со «вчера» и «годом назад», чтобы понять, не отстаёте ли.`),
      h('div', { class: 'grid-3' }, d.horizons.map(forecastCard)), h('p', { class: 'muted small' }, d.note));
  }

  // ---- темп + окно брони ----
  async function drawPace() {
    const [p, l] = await Promise.all([api('GET', '/api/analytics/pace?' + params()), api('GET', '/api/analytics/lead-time?' + params())]);
    const t = p.total;
    const diff = t.bookings - t.prev_bookings;
    const max = Math.max(...p.daily.map((x) => x.bookings), 1);
    body.append(
      h('div', { class: 'kpis' },
        h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Новых броней за 7 дней'), h('div', { class: 'v' }, t.bookings), h('div', { class: `small ${deltaClass(diff)}` }, `${diff > 0 ? '+' : ''}${diff} к прошлым 7 дням (${t.prev_bookings})`)),
        h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Ночей в новых бронях'), h('div', { class: 'v' }, t.nights)),
        h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Сумма новых броней'), h('div', { class: 'v' }, fmtMoney(t.revenue)), h('div', { class: 'small muted' }, `прошлые 7 дней: ${fmtMoney(t.prev_revenue)}`))),
      card('Новые брони по дням (14 дней)', h('div', { class: 'daily-bars' }, p.daily.map((x) => h('div', { class: 'db', title: `${x.day}: ${x.bookings}` },
        h('i', { style: { height: `${Math.max((x.bookings / max) * 100, x.bookings ? 6 : 2)}%` } }), h('span', {}, x.day.slice(8)))))),
      tableCard('Темп по источникам', ['Источник', '7 дней', 'Прошлые 7', 'Ночей', 'Сумма'], p.sources.map((s) => h('tr', {}, h('td', {}, s.label), num(s.bookings), num(s.prev_bookings), num(s.nights), num(fmtMoney(s.revenue)))), 'Считаются брони, появившиеся в системе (не отменённые).'),
      tableCard('За сколько дней бронируют и на сколько ночей живут', ['Канал', 'Броней', 'Окно, дней', 'Ночей в среднем'],
        [...l.by_source.map((s) => h('tr', {}, h('td', {}, s.label), num(s.bookings), num(s.lead), num(s.stay))),
          h('tr', { class: 'total' }, h('td', {}, h('b', {}, 'Все каналы')), num(l.overall.bookings), num(l.overall.lead ?? '—'), num(l.overall.stay ?? '—'))],
        `Заезды за последние 90 дней. Брони с площадок приходят через календарь и считаются от момента, когда появились в системе, — для них окно занижено.`),
      card('Как заранее бронируют', l.buckets.map((b) => h('div', { class: 'dist-row' }, h('span', { class: 'dist-l', style: { width: '170px' } }, b.label),
        h('span', { class: 'dist-bar' }, h('i', { style: { width: `${l.overall.bookings ? (b.bookings / l.overall.bookings) * 100 : 0}%` } })), h('span', { class: 'dist-n' }, b.bookings)))));
  }

  // ---- каналы ----
  async function drawChannels() {
    const d = await api('GET', '/api/analytics/channels?' + params());
    if (!d.items.length) { body.append(h('div', { class: 'card empty' }, h('h3', {}, 'За последние 90 дней заездов не было'))); return; }
    body.append(tableCard('Доходность каналов (заезды за 90 дней)', ['Канал', 'Броней', 'Выручка', 'Комиссия', 'Чистая', 'Цена ночи', 'Чистая за ночь', 'Отмены'],
      [...d.items.map((x) => h('tr', {}, h('td', {}, x.label), num(bookingsWord(x.bookings)), num(fmtMoney(x.revenue)),
        num(x.commission_percent ? `${fmtMoney(x.commission)} (${x.commission_percent}%)` : '—'), num(h('b', {}, fmtMoney(x.net_revenue))), num(fmtMoney(x.avg_price)),
        num(fmtMoney(x.net_avg_price)), num(h('span', { class: x.cancel_share >= 20 ? 'down' : '' }, `${x.cancel_share} %`)))),
      h('tr', { class: 'total' }, h('td', {}, h('b', {}, 'Итого')), num(''), num(fmtMoney(d.totals.revenue)), num(fmtMoney(d.totals.commission)), num(h('b', {}, fmtMoney(d.totals.net_revenue))), num(''), num(''), num(''))],
      d.note));
  }

  // ---- бухгалтеру ----
  async function drawAccountant() {
    const prev = new Date(); prev.setMonth(prev.getMonth() - 1);
    const month = h('input', { class: 'input', type: 'month', value: store.get('an_month') || `${prev.getFullYear()}-${pad(prev.getMonth() + 1)}`, style: { width: '170px' } });
    const area = h('div', { class: 'stack' });
    const range = () => {
      const [y, m] = month.value.split('-').map(Number);
      return { from: `${y}-${pad(m)}-01`, to: m === 12 ? `${y + 1}-01-01` : `${y}-${pad(m + 1)}-01` };
    };
    const csv = h('button', { class: 'btn', onclick: () => downloadCsv('/api/analytics/accountant.csv?' + params(range()), `accountant_${month.value}.csv`) }, 'Скачать CSV для бухгалтера');
    body.append(h('div', { class: 'board-tools' }, month, csv), area);
    async function draw() {
      store.set('an_month', month.value);
      const d = await api('GET', '/api/analytics/accountant?' + params(range()));
      const t = d.totals;
      area.innerHTML = '';
      area.append(
        h('div', { class: 'kpis' },
          h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Поступило по оплатам броней'), h('div', { class: 'v' }, fmtMoney(t.receipts))),
          h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Прочие доходы'), h('div', { class: 'v' }, fmtMoney(t.other_income))),
          h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Расходы'), h('div', { class: 'v' }, fmtMoney(t.expenses))),
          h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Итого за месяц'), h('div', { class: 'v' }, fmtMoney(t.result)))),
        tableCard('Поступления по способам оплаты', ['Способ', 'Оплаты', 'Возвраты', 'Итого'], d.by_method.length ? d.by_method.map((x) => h('tr', {}, h('td', {}, x.label), num(fmtMoney(x.payments)), num(fmtMoney(x.refunds)), num(h('b', {}, fmtMoney(x.net))))) : [h('tr', {}, h('td', { colspan: 4, class: 'muted' }, 'Платежей за месяц нет'))]),
        h('div', { class: 'grid-2' },
          tableCard('Прочие доходы', ['Категория', 'Сумма'], d.income_by_category.length ? d.income_by_category.map((x) => h('tr', {}, h('td', {}, x.name), num(fmtMoney(x.amount)))) : [h('tr', {}, h('td', { colspan: 2, class: 'muted' }, 'Нет'))]),
          tableCard('Расходы по категориям', ['Категория', 'Сумма'], d.expense_by_category.length ? d.expense_by_category.map((x) => h('tr', {}, h('td', {}, x.name), num(fmtMoney(x.amount)))) : [h('tr', {}, h('td', { colspan: 2, class: 'muted' }, 'Нет'))])),
        h('p', { class: 'muted small' }, d.note));
    }
    month.addEventListener('change', () => draw().catch((ex) => area.append(h('div', { class: 'card empty' }, ex.message))));
    await draw();
  }

  async function load() {
    body.innerHTML = '';
    drawSeg();
    try { await ({ forecast: drawForecast, pace: drawPace, channels: drawChannels, accountant: drawAccountant }[tab])(); }
    catch (ex) { body.append(h('div', { class: 'card empty' }, ex.message)); }
  }
  load();
}
