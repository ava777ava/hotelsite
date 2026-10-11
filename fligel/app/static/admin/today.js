// Флигель — интерфейс администратора (раздел «сегодня»). ES-модуль без сборки.
import { autoRefresh, scopeSeg } from './app.js';
import { bookingDrawer } from './booking.js';
import { MONTHS_NOM, SOURCE, WD, addDays, api, can, fmtDate, fmtMoney, fmtShort, h, icon, letterhead, pad, parseISO, qs, state, toast, todayISO } from './core.js';
import { kpiCard } from './reports.js';
import { plural, count } from './ui.js';

// ---------- сегодня ----------
export async function viewToday(main) {
  let day = todayISO();
  let lastData = null;
  const scope = { value: 'current' };
  const content = h('div');
  const dateInput = h('input', { class: 'input', type: 'date', value: day, style: { width: '160px' }, onchange: (e) => { day = e.target.value || todayISO(); load(); } });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Заезды и выезды'),
    h('button', { class: 'btn icon', 'aria-label': 'Предыдущий день', onclick: () => { day = addDays(day, -1); dateInput.value = day; load(); } }, icon('left')),
    dateInput,
    h('button', { class: 'btn icon', 'aria-label': 'Следующий день', onclick: () => { day = addDays(day, 1); dateInput.value = day; load(); } }, icon('right')),
    scopeSeg(scope, () => load()),
    h('button', { class: 'btn', onclick: () => { day = todayISO(); dateInput.value = day; load(); } }, 'Сегодня'),
    h('button', { class: 'btn', onclick: () => lastData && printDaySheet(day, lastData) }, icon('print'), 'Печать')), content);
  const item = (b, kind) => {
    const due = Number(b.total_price) - Number(b.paid_amount);
    return h('div', { class: 'item', onclick: () => bookingDrawer(b, load) },
      h('div', { class: 'room-chip' }, b.room_name),
      h('div', { style: { flex: 1, minWidth: 0 } },
        h('div', { style: { fontWeight: 600 } }, b.guest_name || `Гость с площадки ${SOURCE[b.source]}`,
          scope.value === 'all' ? h('span', { class: 'muted small', style: { fontWeight: 400 } }, ' · ', b.property_name) : null),
        h('div', { class: 'muted small' }, `${fmtShort(b.check_in)} — ${fmtShort(b.check_out)} · ${count(b.guests_count, 'guest')} · ${SOURCE[b.source]}`),
        b.guest_phone ? h('a', { class: 'small tel', href: `tel:${b.guest_phone}`, onclick: (e) => e.stopPropagation() }, b.guest_phone) : null),
      kind !== 'staying' && due > 0 && can('manager') ? h('span', { class: 'pill warn num' }, `к оплате ${fmtMoney(due)}`) : null,
      b.status === 'pending' ? h('span', { class: 'pill warn' }, 'заявка') : null,
      kind === 'out' && day === todayISO() ? cleaningControl(b) : null);
  };
  // Уборка: номер, из которого сегодня выезжают, «ждёт уборки», пока горничная (или любой сотрудник) не отметит его убранным
  const cleaningControl = (b) => {
    const clean = b.room_cleaned_on && b.room_cleaned_on.slice(0, 10) === day;
    return h('button', {
      class: 'btn small' + (clean ? ' ok-btn' : ''), title: clean ? 'Нажмите, чтобы снять отметку' : 'Отметить номер убранным',
      onclick: async (e) => {
        e.stopPropagation();
        try { await api('POST', `/api/rooms/${b.room_id}/cleaned`, { cleaned: !clean }); load(); } catch (ex) { toast(ex.message, true); }
      },
    }, clean ? '✓ Убран' : 'Убрать');
  };
  const block = (title, list, kind, emptyText) => h('div', { class: 'card' },
    h('div', { class: 'card-head' }, h('h2', {}, title), h('span', { class: 'pill none num' }, list.length)),
    list.length ? h('div', { class: 'day-list' }, list.map((b) => item(b, kind))) : h('div', { class: 'empty' }, emptyText));
  const load = async () => {
    try {
      const d = await api('GET', '/api/today?' + qs({ date: day, property_id: scope.value === 'current' ? state.propertyId : undefined, summary: can('manager') && day === todayISO() ? 1 : undefined }));
      lastData = d;
      content.innerHTML = '';
      const dueToday = [...d.arrivals, ...d.departures].reduce((sum, b) => sum + Math.max(Number(b.total_price) - Number(b.paid_amount), 0), 0);
      content.append(
        h('p', { class: 'muted', style: { marginTop: '-6px' } }, `${fmtDate(day)}, ${WD[parseISO(day).getDay()].toLowerCase()}`),
        d.summary ? homeSummary(d.summary) : '',
        h('div', { class: 'kpis' },
          kpiCard('Заезды', String(d.arrivals.length)), kpiCard('Выезды', String(d.departures.length)),
          kpiCard('Проживают', String(d.staying.length)),
          kpiCard('Свободно на ночь', `${d.free_tonight}`, `из ${d.rooms_total}`),
          day === todayISO() ? kpiCard('Ждут уборки', String(d.departures.filter((b) => !(b.room_cleaned_on && b.room_cleaned_on.slice(0, 10) === day)).length)) : null,
          can('manager') ? kpiCard('К доплате по заездам и выездам', fmtMoney(dueToday)) : null),
        h('div', { class: 'grid-2' },
          block('Заезды', d.arrivals, 'in', 'Заездов нет'),
          block('Выезды', d.departures, 'out', 'Выездов нет'),
          block('Проживают', d.staying, 'staying', 'Сейчас никто не проживает')));
    } catch (ex) { content.innerHTML = ''; content.append(h('div', { class: 'card empty' }, ex.message)); }
  };
  load();
  autoRefresh(load);
}

// Главное за минуту: что требует внимания и итог месяца на сегодня (вверху страницы «Сегодня» у владельца и администратора)
export function homeSummary(sm) {
  const a = sm.alerts, m = sm.month;
  const items = [
    a.requests ? ['Заявки с сайта ждут ответа', `${a.requests}`, '#/bookings', 'warn'] : null,
    a.conflicts ? ['Конфликты с площадок', `${a.conflicts}`, '#/channels', 'bad'] : null,
    a.debt_count ? ['Гости должны', fmtMoney(a.debt_amount), '#/bookings', 'warn', `${a.debt_count} ${plural(a.debt_count, ['бронь', 'брони', 'броней'])}`] : null,
    a.repairs ? ['Номера в ремонте', `${a.repairs}`, '#/cleaning', 'bad'] : null,
  ].filter(Boolean);
  const month = MONTHS_NOM[parseISO(m.from).getMonth()];
  return h('div', { class: 'home-summary' },
    h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '10px' } }, 'Требует внимания'),
      items.length ? h('div', { class: 'alert-list' }, items.map(([t, v, href, cls, sub]) => h('a', { href, class: `alert-item ${cls}` }, h('span', {}, t, sub ? h('small', {}, sub) : null), h('b', {}, v))))
        : h('div', { class: 'muted' }, 'Всё спокойно: заявок, конфликтов, долгов и поломок нет.')),
    h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '10px' } }, `${month}: итог на сегодня`),
      h('div', { class: 'month-grid' },
        h('div', {}, h('span', { class: 'muted small' }, 'Выручка'), h('b', {}, fmtMoney(m.revenue))),
        h('div', {}, h('span', { class: 'muted small' }, 'Расходы'), h('b', {}, fmtMoney(m.expenses))),
        h('div', {}, h('span', { class: 'muted small' }, 'Прибыль'), h('b', { class: Number(m.profit) < 0 ? 'neg' : 'pos' }, fmtMoney(m.profit))),
        h('div', {}, h('span', { class: 'muted small' }, 'Загрузка'), h('b', {}, `${m.occupancy}%`))),
      h('a', { href: '#/stats', class: 'small', style: { display: 'inline-block', marginTop: '8px' } }, 'Подробнее в отчётах →')));
}

// ---------- печатный лист ----------
export function printDaySheet(day, data) {
  document.getElementById('print-sheet')?.remove();
  const W = { 'Номер': '9%', 'Гость': '30%', 'Телефон': '21%', 'Гостей': '8%', 'К оплате': '14%', 'Отметка': '18%' };
  const th = (t) => h('th', { style: { textAlign: 'left', borderBottom: '2px solid #000', padding: '5px 6px', fontSize: '13px', width: W[t] } }, t);
  const td = (t) => h('td', { style: { borderBottom: '1px solid #999', padding: '6px', fontSize: '13px' } }, t);
  const section = (title, list, withDue) => {
    const cols = ['Номер', 'Гость', 'Телефон', 'Гостей', withDue ? 'К оплате' : null, 'Отметка'].filter(Boolean);
    const rows = list.length
      ? list.map((b) => h('tr', {}, td(b.room_name), td(b.guest_name || `Гость (${SOURCE[b.source]})`), td(b.guest_phone || '—'),
          td(String(b.guests_count)), withDue ? td(fmtMoney(Number(b.total_price) - Number(b.paid_amount))) : null,
          h('td', { style: { borderBottom: '1px solid #999', width: '70px' } })))
      : [h('tr', {}, h('td', { colspan: String(cols.length), style: { padding: '6px', color: '#666' } }, 'Нет'))];
    return h('div', { style: { marginBottom: '26px' } },
      h('h2', { style: { margin: '0 0 8px', fontSize: '16px' } }, title),
      h('table', { style: { width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' } },
        h('thead', {}, h('tr', {}, cols.map(th))), h('tbody', {}, rows)));
  };
  const sheet = h('div', { id: 'print-sheet' },
    letterhead((state.me.properties.find((p) => p.id === state.propertyId) || {}).name || 'Флигель'),
    h('h1', { style: { fontSize: '20px', marginBottom: '4px' } }, 'Заезды и выезды'),
    h('p', { style: { marginTop: 0, marginBottom: '18px', color: '#333' } }, `${fmtDate(day)}, ${WD[parseISO(day).getDay()].toLowerCase()}`),
    section('Заезды', data.arrivals, true),
    section('Выезды', data.departures, true),
    section('Проживают', data.staying, false));
  document.body.append(sheet);
  window.print();
}
