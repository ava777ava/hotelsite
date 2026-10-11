// Флигель — интерфейс администратора (раздел «отчёты»). ES-модуль без сборки.
import { scopeSeg } from './app.js';
import { MONTHS_SHORT, WD, addDays, api, downloadCsv, fmtMoney, h, icon, iso, pad, parseISO, qs, state, store, todayISO } from './core.js';

// ---------- отчёты: графики (свой SVG, без библиотек) ----------
export const escHtml = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const safeColor = (c) => (/^#[0-9a-fA-F]{6}$/.test(c || '') ? c : '#69755F');

export function svgEl(markup) {
  const wrap = document.createElement('div');
  wrap.innerHTML = markup.trim();
  return wrap.firstChild;
}

export const CHART_COLORS = ['#2F5D50', '#B7791F', '#6E4A93', '#23767E', '#B4562E', '#4A5A6A', '#5E6B5A', '#7A3418', '#8A5A12', '#69755F'];

export function monthlyChart(monthly) {
  const W = 720, H = 230, padB = 24, plotH = H - padB - 8;
  const vals = monthly.flatMap((m) => [Number(m.revenue) + Number(m.other_income || 0), Number(m.expenses), Math.abs(Number(m.profit))]);
  const max = Math.max(1, ...vals);
  const n = monthly.length;
  const colW = W / n;
  const barW = Math.min(16, colW * 0.32);
  const y0 = plotH + 8;
  let bars = '';
  let points = '';
  monthly.forEach((m, i) => {
    const cx = colW * (i + 0.5);
    const rev = Number(m.revenue), oth = Number(m.other_income || 0), exp = Number(m.expenses), profit = Number(m.profit);
    const revH = (rev / max) * plotH, othH = (oth / max) * plotH, expH = (exp / max) * plotH;
    const dt = parseISO(m.month);
    const tip = `${MONTHS_SHORT[dt.getMonth()]} ${dt.getFullYear()}: проживание ${fmtMoney(rev)}, прочие доходы ${fmtMoney(oth)}, расходы ${fmtMoney(exp)}, прибыль ${fmtMoney(profit)}`;
    bars += `<g><title>${tip}</title>`;
    bars += `<rect x="${cx - barW - 2}" y="${y0 - revH}" width="${barW}" height="${revH}" fill="${CHART_COLORS[0]}" rx="2"/>`;
    if (othH > 0.5) bars += `<rect x="${cx - barW - 2}" y="${y0 - revH - othH}" width="${barW}" height="${othH}" fill="${CHART_COLORS[3]}" rx="2"/>`;
    bars += `<rect x="${cx + 2}" y="${y0 - expH}" width="${barW}" height="${expH}" fill="${CHART_COLORS[4]}" rx="2"/>`;
    bars += `<rect x="${cx - colW / 2}" y="0" width="${colW}" height="${H}" fill="transparent"/></g>`;
    const py = Math.max(-4, Math.min(y0, y0 - (profit / max) * plotH));
    points += `${cx},${py} `;
    bars += `<text x="${cx}" y="${H - 6}" font-size="10.5" fill="var(--muted)" text-anchor="middle">${MONTHS_SHORT[dt.getMonth()]}</text>`;
  });
  return svgEl(`<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;display:block;overflow:visible" role="img" aria-label="Доходы, расходы и прибыль по месяцам">
    <line x1="0" y1="${y0}" x2="${W}" y2="${y0}" stroke="var(--border)"/>
    ${bars}
    <polyline points="${points.trim()}" fill="none" stroke="${CHART_COLORS[1]}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
  </svg>`);
}

// Расходы по категориям помесячно — столбцы с накоплением. Показаны крупнейшие категории,
// остальные слиты в «Остальные» (это делает сервер).
export function stackedExpenseChart(em) {
  const W = 720, H = 220, padB = 24, plotH = H - padB - 8, y0 = plotH + 8;
  const totals = em.rows.map((r) => Object.values(r.amounts).reduce((s, v) => s + Number(v), 0));
  const max = Math.max(1, ...totals);
  const colW = W / em.rows.length, barW = Math.min(30, colW * 0.6);
  let bars = '';
  em.rows.forEach((row, i) => {
    const cx = colW * (i + 0.5);
    let y = y0;
    const tipLines = [];
    em.categories.forEach((c) => {
      const v = Number(row.amounts[c.category_id] || 0);
      if (v <= 0) return;
      const hgt = (v / max) * plotH;
      y -= hgt;
      bars += `<rect x="${cx - barW / 2}" y="${y}" width="${barW}" height="${Math.max(hgt, 0.5)}" fill="${safeColor(c.color)}"/>`;
      tipLines.push(`${escHtml(c.name)}: ${fmtMoney(v)}`);
    });
    const dt = parseISO(row.month);
    bars += `<rect x="${cx - colW / 2}" y="0" width="${colW}" height="${H}" fill="transparent"><title>${MONTHS_SHORT[dt.getMonth()]} ${dt.getFullYear()} — всего ${fmtMoney(totals[i])}\n${tipLines.join('\n')}</title></rect>`;
    bars += `<text x="${cx}" y="${H - 6}" font-size="10.5" fill="var(--muted)" text-anchor="middle">${MONTHS_SHORT[dt.getMonth()]}</text>`;
  });
  return svgEl(`<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;display:block" role="img" aria-label="Расходы по категориям по месяцам">
    <line x1="0" y1="${y0}" x2="${W}" y2="${y0}" stroke="var(--border)"/>${bars}</svg>`);
}

export function weekdayChart(weekday) {
  const W = 420, H = 160, padB = 22;
  const plotH = H - padB;
  const order = [1, 2, 3, 4, 5, 6, 0]; // показываем неделю с понедельника
  const colW = W / order.length;
  const barW = Math.min(34, colW * 0.55);
  let bars = '';
  order.forEach((wd, i) => {
    const x = weekday.find((w) => w.weekday === wd) || { occupancy: 0 };
    const cx = colW * (i + 0.5);
    const bh = (Math.min(100, x.occupancy) / 100) * plotH;
    bars += `<rect x="${cx - barW / 2}" y="${plotH - bh}" width="${barW}" height="${Math.max(bh, 1)}" fill="var(--pine)" rx="3"/>`;
    bars += `<text x="${cx}" y="${plotH - bh - 6}" font-size="11" fill="var(--ink)" text-anchor="middle" font-weight="600">${Math.round(x.occupancy)}%</text>`;
    bars += `<text x="${cx}" y="${H - 6}" font-size="11" fill="var(--muted)" text-anchor="middle">${WD[wd]}</text>`;
  });
  return svgEl(`<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;display:block">
    <line x1="0" y1="${plotH}" x2="${W}" y2="${plotH}" stroke="var(--border)"/>
    ${bars}
  </svg>`);
}

export function expenseDonut(byCategory) {
  const size = 160, r = 62, cx = size / 2, cy = size / 2, circ = 2 * Math.PI * r;
  const total = byCategory.reduce((s, x) => s + Number(x.amount), 0) || 1;
  let offset = 0;
  let circles = '';
  byCategory.forEach((x, i) => {
    const frac = Number(x.amount) / total;
    const len = frac * circ;
    circles += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${safeColor(x.color)}" stroke-width="22"` +
      ` stroke-dasharray="${len} ${circ - len}" stroke-dashoffset="${-offset}" transform="rotate(-90 ${cx} ${cy})"/>`;
    offset += len;
  });
  return svgEl(`<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">${circles}</svg>`);
}

export function deltaBadge(delta) {
  if (delta === null || delta === undefined) return h('span', { class: 'muted small' }, '—');
  const good = delta >= 0;
  return h('span', { class: 'small', style: { color: good ? 'var(--pine)' : 'var(--clay)', fontWeight: 600 } },
    `${good ? '▲' : '▼'} ${Math.abs(delta).toFixed(1).replace('.', ',')}%`);
}

export function kpiCard(label, value, unit, compare, text = false) {
  const v = h('div', { class: 'v' + (text ? ' txt' : '') }, value, unit ? h('small', {}, ` ${unit}`) : null);
  const cmp = compare ? h('div', { class: 'small muted', style: { marginTop: '6px', display: 'flex', gap: '10px' } },
    h('span', {}, 'к периоду: ', deltaBadge(compare.period)), h('span', {}, 'к году: ', deltaBadge(compare.year))) : null;
  return h('div', { class: 'kpi' }, h('div', { class: 'l' }, label), v, cmp);
}

// ---------- отчёты ----------
export async function viewStats(main) {
  const t = todayISO(); const d = parseISO(t);
  const monthStart = iso(new Date(d.getFullYear(), d.getMonth(), 1));
  const nextMonth = iso(new Date(d.getFullYear(), d.getMonth() + 1, 1));
  const prevMonth = iso(new Date(d.getFullYear(), d.getMonth() - 1, 1));
  const quarterStart = iso(new Date(d.getFullYear(), Math.floor(d.getMonth() / 3) * 3, 1));
  const yearStart = iso(new Date(d.getFullYear(), 0, 1));
  const nextYear = iso(new Date(d.getFullYear() + 1, 0, 1));
  const periods = [
    ['Этот месяц', monthStart, nextMonth], ['Прошлый месяц', prevMonth, monthStart],
    ['Этот квартал', quarterStart, nextMonth > quarterStart ? nextMonth : addDays(quarterStart, 90)],
    ['Этот год', yearStart, nextYear], ['Свой период', null, null],
  ];
  let current = Math.min(parseInt(store.get('stats_period', '0'), 10) || 0, periods.length - 2); // свой период не запоминаем
  const custom = { from: addDays(t, -30), to: t };
  const scope = { value: 'current' };
  const content = h('div', { class: 'stack' });
  const customBox = h('div', { class: 'board-tools', style: { display: 'none' } });
  const seg = h('div', { class: 'seg', style: { flexWrap: 'wrap' } });
  const drawSeg = () => {
    seg.innerHTML = '';
    periods.forEach(([l], i) => seg.append(h('button', { class: i === current ? 'on' : '', onclick: () => { current = i; if (i < periods.length - 1) store.set('stats_period', String(i)); drawSeg(); customBox.style.display = i === periods.length - 1 ? 'flex' : 'none'; if (i !== periods.length - 1) load(); } }, l)));
  };
  drawSeg();
  const fromInp = h('input', { class: 'input', type: 'date', value: custom.from, style: { width: '150px' }, onchange: (e) => { custom.from = e.target.value; load(); } });
  const toInp = h('input', { class: 'input', type: 'date', value: custom.to, style: { width: '150px' }, onchange: (e) => { custom.to = e.target.value; load(); } });
  customBox.append(fromInp, '—', toInp);
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Отчёты'), seg, scopeSeg(scope, () => load())), customBox, content);

  async function load() {
    const isCustom = current === periods.length - 1;
    const from = isCustom ? custom.from : periods[current][1];
    const to = isCustom ? custom.to : periods[current][2];
    const propertyId = scope.value === 'current' ? state.propertyId : undefined;
    let r;
    try {
      r = await api('GET', '/api/reports?' + qs({ from, to, property_id: propertyId }));
    } catch (ex) { content.innerHTML = ''; content.append(h('div', { class: 'card empty' }, ex.message)); return; }
    const tt = r.totals;
    const cmp = { period: r.compare_prev_period, year: r.compare_prev_year };
    const money = (v) => fmtMoney(v).replace('.', ',');

    content.innerHTML = '';
    content.append(h('div', { class: 'kpis' },
      kpiCard('Выручка от проживания', money(tt.revenue), null, { period: cmp.period.revenue_delta, year: cmp.year.revenue_delta }),
      kpiCard('Прочие доходы', money(tt.other_income), null, { period: cmp.period.other_income_delta, year: cmp.year.other_income_delta }),
      kpiCard('Расходы', money(tt.expenses), null, { period: cmp.period.expenses_delta, year: cmp.year.expenses_delta }),
      kpiCard('Прибыль', money(tt.profit), null, { period: cmp.period.profit_delta, year: cmp.year.profit_delta }),
      kpiCard('Рентабельность', tt.margin == null ? '—' : String(tt.margin).replace('.', ','), tt.margin == null ? null : '%'),
      kpiCard('Загрузка', String(tt.occupancy).replace('.', ','), '%', { period: cmp.period.occupancy_delta, year: cmp.year.occupancy_delta }),
      kpiCard('Цена ночи (ADR)', money(tt.adr)),
      kpiCard('Доход на номер (RevPAR)', money(tt.revpar)),
      kpiCard('Средний срок проживания', String(tt.avg_stay).replace('.', ','), 'ноч.'),
      kpiCard('Доля отмен', String(tt.cancellation_rate).replace('.', ','), '%'),
      kpiCard('Гости должны доплатить', money(tt.due_amount))));

    const chartsRow = h('div', { class: 'grid-2' });
    chartsRow.append(
      h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, 'Доходы, расходы и прибыль по месяцам'),
        monthlyChart(r.monthly),
        h('div', { class: 'legend', style: { padding: '10px 0 0', border: 0 } },
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[0] } }), 'Проживание'),
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[3] } }), 'Прочие доходы'),
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[4] } }), 'Расходы'),
          h('span', {}, h('i', { class: 'dot', style: { background: CHART_COLORS[1] } }), 'Прибыль (линия)'))),
      h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, 'Загрузка по дням недели'),
        weekdayChart(r.weekday_occupancy)));
    content.append(chartsRow);
    // Деньги, которые реально поступили за период (по датам платежей), — в отличие от выручки по ночам
    const cash = h('div', { class: 'card card-pad' });
    content.append(cash);
    api('GET', '/api/payments/summary?' + qs({ from, to: addDays(to, -1) })).then((c) => {
      cash.append(h('h2', { style: { marginBottom: '8px' } }, 'Поступления денег'),
        h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Сколько оплат внесено за период (по дате платежа), независимо от того, за какие ночи.'),
        h('div', { class: 'month-grid' },
          h('div', {}, h('span', { class: 'muted small' }, 'Принято'), h('b', {}, fmtMoney(c.received))),
          h('div', {}, h('span', { class: 'muted small' }, 'Возвраты'), h('b', {}, fmtMoney(c.refunded))),
          h('div', {}, h('span', { class: 'muted small' }, 'Итого'), h('b', { class: 'pos' }, fmtMoney(c.net))),
          ...c.by_method.map((m) => h('div', {}, h('span', { class: 'muted small' }, m.label), h('b', {}, fmtMoney(m.received - m.refunded))))));
    }).catch(() => { cash.remove(); });

    const structureCard = (title, items, emptyText) => {
      const card = h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, title));
      if (items.length) {
        const total = items.reduce((s, x) => s + Number(x.amount), 0) || 1;
        card.append(h('div', { class: 'donut-box' }, expenseDonut(items),
          h('div', { style: { flex: 1, minWidth: '200px' } }, items.map((x) => h('div', {
            style: { display: 'flex', justifyContent: 'space-between', gap: '10px', padding: '4px 0' },
          }, h('span', {}, h('i', { class: 'dot', style: { background: safeColor(x.color) } }), ' ', x.name,
            h('span', { class: 'muted small' }, ` ${Math.round((Number(x.amount) / total) * 100)}%`)), h('b', { class: 'num' }, money(x.amount)))))));
      } else card.append(h('div', { class: 'empty' }, emptyText));
      return card;
    };
    content.append(h('div', { class: 'grid-2' },
      structureCard('Структура расходов', r.by_expense_category, 'Расходов за период нет'),
      structureCard('Структура прочих доходов', r.by_income_category, 'Прочих доходов за период нет')));

    if (r.expense_monthly && r.expense_monthly.categories.length) {
      content.append(h('div', { class: 'card card-pad' }, h('h3', { style: { marginBottom: '10px' } }, 'Расходы по категориям по месяцам'),
        stackedExpenseChart(r.expense_monthly),
        h('div', { class: 'legend', style: { padding: '10px 0 0', border: 0 } },
          r.expense_monthly.categories.map((c) => h('span', {}, h('i', { class: 'dot', style: { background: safeColor(c.color) } }), c.name)))));
    }

    if (r.by_property && r.by_property.length) {
      content.append(h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', {}, 'По объектам')),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' },
          h('thead', {}, h('tr', {}, ['Объект', 'Номеров', 'Выручка', 'Прочие доходы', 'Расходы', 'Прибыль', 'Загрузка'].map((x) => h('th', {}, x)))),
          h('tbody', {}, r.by_property.map((p) => h('tr', {},
            h('td', {}, p.property_name), h('td', { class: 'num' }, p.rooms),
            h('td', { class: 'num' }, money(p.revenue)), h('td', { class: 'num' }, money(p.other_income)), h('td', { class: 'num' }, money(p.expenses)),
            h('td', { class: 'num' }, money(p.profit)), h('td', { class: 'num' }, `${String(p.occupancy).replace('.', ',')}%`))))))));
    }

    if (r.by_room_type.length) {
      content.append(h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', {}, 'По категориям номеров')),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' },
          h('thead', {}, h('tr', {}, ['Категория', 'Номеров', 'Ночей', 'Выручка'].map((x) => h('th', {}, x)))),
          h('tbody', {}, r.by_room_type.map((x) => h('tr', {},
            h('td', {}, x.room_type_name), h('td', { class: 'num' }, x.rooms),
            h('td', { class: 'num' }, x.nights), h('td', { class: 'num' }, money(x.revenue)))))))));
    }

    let roomSort = { key: 'profit', dir: -1 };
    const roomCard = h('div', { class: 'card' });
    const drawRoomTable = () => {
      const rows = [...r.by_room].sort((a, b) => {
        const av = isNaN(a[roomSort.key]) ? a[roomSort.key] : Number(a[roomSort.key]);
        const bv = isNaN(b[roomSort.key]) ? b[roomSort.key] : Number(b[roomSort.key]);
        return (av > bv ? 1 : av < bv ? -1 : 0) * roomSort.dir;
      });
      const th = (key, label) => h('th', { style: { cursor: 'pointer' }, onclick: () => { roomSort.dir = roomSort.key === key ? -roomSort.dir : -1; roomSort.key = key; drawRoomTable(); } },
        label, roomSort.key === key ? (roomSort.dir === -1 ? ' ↓' : ' ↑') : '');
      roomCard.innerHTML = '';
      const multi = state.me.properties.length > 1;
      const roomTableBody = rows.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' },
          h('thead', {}, h('tr', {}, th('room_name', 'Номер'), th('room_type_name', 'Категория'),
            multi ? th('property_name', 'Объект') : null, th('nights', 'Ночей'),
            th('occupancy', 'Загрузка'), th('revenue', 'Выручка'), th('other_income', 'Др. доходы'),
            th('expenses', 'Расходы'), th('profit', 'Прибыль'))),
          h('tbody', {}, rows.map((x) => h('tr', {},
            h('td', { 'data-l': 'Номер' }, h('b', {}, x.room_name)), h('td', { class: 'muted small', 'data-l': 'Категория' }, x.room_type_name),
            multi ? h('td', { class: 'muted small', 'data-l': 'Объект' }, x.property_name) : null,
            h('td', { class: 'num', 'data-l': 'Ночей' }, x.nights), h('td', { class: 'num', 'data-l': 'Загрузка' }, `${String(x.occupancy).replace('.', ',')}%`),
            h('td', { class: 'num', 'data-l': 'Выручка' }, money(x.revenue)),
            h('td', { class: 'num', 'data-l': 'Др. доходы' }, Number(x.other_income) ? money(x.other_income) : '—'),
            h('td', { class: 'num', 'data-l': 'Расходы' }, Number(x.expenses) ? money(x.expenses) : '—'),
            h('td', { class: 'num strong', 'data-l': 'Прибыль', style: { color: Number(x.profit) < 0 ? 'var(--clay)' : '' } }, money(x.profit))))))) : h('div', { class: 'empty' }, 'В этом объекте пока нет номеров');
      roomCard.append(h('div', { class: 'card-head' }, h('h2', {}, 'По номерам'), h('span', { class: 'muted small' }, 'нажмите на заголовок для сортировки')),
        roomTableBody,
        h('p', { class: 'muted small card-pad', style: { paddingTop: '8px' } }, 'Расходы и доходы здесь — только те, что записаны на сам номер (раздел «Финансы» → «Относится к»). Расходы объекта и общие между номерами не делятся.'));
    };
    drawRoomTable();
    content.append(roomCard);

    const maxSrc = Math.max(1, ...r.by_source.map((x) => Number(x.revenue)));
    const sourceRow = (x) => {
      const dot = h('i', { class: 'dot', style: { background: `var(--src-${x.source})` } });
      const label = h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, dot, x.label);
      const commission = Number(x.commission_percent) ? `${money(x.commission_amount)} (${x.commission_percent}%)` : '—';
      const barFill = h('i', { style: { width: `${(Number(x.revenue) / maxSrc) * 100}%`, background: `var(--src-${x.source})` } });
      const bar = h('div', { class: 'bar-h' }, barFill);
      return h('tr', {}, h('td', { class: 'wide' }, label), h('td', { class: 'num', 'data-l': 'Броней' }, x.bookings), h('td', { class: 'num', 'data-l': 'Ночей' }, x.nights),
        h('td', { class: 'num', 'data-l': 'Выручка' }, money(x.revenue)), h('td', { class: 'num muted small', 'data-l': 'Комиссия' }, commission),
        h('td', { class: 'num', 'data-l': 'Чистая выручка' }, money(x.net_revenue)), h('td', { class: 'wide', style: { width: '25%' } }, bar));
    };
    const sourceHead = h('thead', {}, h('tr', {}, ['Источник', 'Броней', 'Ночей', 'Выручка', 'Комиссия', 'Чистая выручка', ''].map((x) => h('th', {}, x))));
    const sourceBody = r.by_source.length
      ? h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' }, sourceHead, h('tbody', {}, r.by_source.map(sourceRow))))
      : h('div', { class: 'empty' }, 'За этот период броней нет');
    content.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'По источникам броней')), sourceBody));

    content.append(h('p', { class: 'muted small' },
      'Выручка считается по ночам внутри периода: бронь, которая начинается в одном месяце и заканчивается в другом, делится пропорционально. ',
      r.share_note,
      ' Комиссии площадок настраиваются в разделе «Настройки».'));

    content.append(h('div', { style: { display: 'flex', justifyContent: 'flex-end' } },
      h('button', { class: 'btn', onclick: () => downloadCsv('/api/reports/export.csv?' + qs({ from, to, property_id: propertyId }), `report_${from}_${to}.csv`) },
        icon('download'), 'Выгрузить отчёт в CSV')));
  }
  load();
}
