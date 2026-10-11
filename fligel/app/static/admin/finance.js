// Флигель — интерфейс администратора (раздел «финансы»). ES-модуль без сборки.
import { G, addDays, api, can, closeDrawer, downloadCsv, fmtMoney, fmtShort, h, icon, loadingBox, openDrawer, pad, qs, state, store, toast, todayISO } from './core.js';
import { kpiCard } from './reports.js';
import { count } from './ui.js';

export function categoryDrawer(cat, cfg = FLOW.expense) {
  const g = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const COLORS = ['#23767E', '#4A5A6A', '#6E4A93', '#B4562E', '#B7791F', '#2F5D50', '#5E6B5A', '#7A3418', '#8A5A12', '#69755F', '#C1852B', '#3B7A9E'];
  let color = cat.color || COLORS[0];
  if (!cat.id && cfg.kind === 'income') color = '#2F5D50';
  const swatches = h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' } });
  const drawSwatches = () => {
    swatches.innerHTML = '';
    COLORS.forEach((c) => swatches.append(h('button', {
      type: 'button', onclick: () => { color = c; drawSwatches(); },
      style: { width: '26px', height: '26px', borderRadius: '7px', background: c, border: color === c ? '2px solid var(--ink)' : '2px solid transparent', cursor: 'pointer' },
    })));
  };
  drawSwatches();
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; err.style.display = 'none';
    try {
      const payload = { name: g.name.value, color };
      if (cat.id) await api('PATCH', `${cfg.catApi}/${cat.id}`, payload);
      else await api('POST', cfg.catApi, payload);
      closeDrawer(); toast('Сохранено'); cat.onSaved?.();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, 'Сохранить');
  const foot = [h('span', { class: 'spacer' }), save];
  if (cat.id) {
    foot.unshift(h('button', { class: 'btn ghost danger', onclick: async () => {
      if (!confirm(`Архивировать категорию «${cat.name}»? Старые расходы останутся, но выбрать её для новых будет нельзя.`)) return;
      try { await api('PATCH', `${cfg.catApi}/${cat.id}`, { archived: true }); closeDrawer(); toast('Категория архивирована'); cat.onSaved?.(); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Архивировать'));
  }
  openDrawer(cat.id ? (cfg.kind === 'income' ? 'Категория доходов' : 'Категория расходов') : 'Новая категория', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Название'), g.name = h('input', { class: 'input', value: cat.name || '', required: true })),
    h('div', { class: 'field' }, h('span', {}, 'Цвет'), swatches)), foot);
}

export function recurringDrawer(cats, rule, propertyOptions, onSaved) {
  const g = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  g.category_id = h('select', { class: 'input' }, cats.map((c) => h('option', { value: c.id, selected: c.id === rule.category_id }, c.name)));
  g.amount = h('input', { class: 'input', money: true, type: 'number', min: 0, value: rule.amount ? Math.round(rule.amount) : '' });
  g.day_of_month = h('input', { class: 'input', type: 'number', min: 1, max: 28, value: rule.day_of_month || 1 });
  g.property_id = h('select', { class: 'input' }, h('option', { value: '' }, 'Общий — по всем объектам'),
    propertyOptions.map((p) => h('option', { value: p.id, selected: p.id === rule.property_id }, p.name)));
  g.comment = h('input', { class: 'input', value: rule.comment || '', placeholder: 'Например: аренда помещения' });
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; err.style.display = 'none';
    try {
      const payload = {
        category_id: g.category_id.value, amount: g.amount.value, day_of_month: g.day_of_month.value,
        property_id: g.property_id.value || null, comment: g.comment.value,
      };
      if (rule.id) await api('PATCH', `/api/expense-recurring/${rule.id}`, payload);
      else await api('POST', '/api/expense-recurring', payload);
      closeDrawer(); toast('Сохранено'); onSaved();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, 'Сохранить');
  const foot = [h('span', { class: 'spacer' }), save];
  if (rule.id) {
    foot.unshift(h('button', { class: 'btn ghost danger', onclick: async () => {
      if (!confirm('Удалить повторяющийся расход? Уже созданные записи расходов останутся.')) return;
      try { await api('DELETE', `/api/expense-recurring/${rule.id}`); closeDrawer(); toast('Удалено'); onSaved(); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Удалить'));
  }
  openDrawer(rule.id ? 'Повторяющийся расход' : 'Новый повторяющийся расход', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Категория'), g.category_id),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Сумма, ₽'), g.amount),
      h('label', { class: 'field' }, h('span', {}, 'Число месяца (1—28)'), g.day_of_month)),
    h('label', { class: 'field' }, h('span', {}, 'Объект'), g.property_id),
    h('label', { class: 'field' }, h('span', {}, 'Комментарий'), g.comment),
    h('p', { class: 'muted small' }, 'В нужный день месяца расход создастся сам — в том же фоновом режиме, что и синхронизация площадок.')),
  foot);
}

// ---------- финансы: расходы и прочие доходы ----------
// Расходы и прочие доходы (завтраки, парковка, трансфер…) устроены одинаково: свои категории,
// привязка к объекту или к конкретному номеру либо «общая» запись на весь аккаунт.
export const FLOW = {
  expense: {
    kind: 'expense', api: '/api/expenses', catApi: '/api/expense-categories', csv: 'expenses', catColor: '#69755F',
    tab: 'Расходы', one: 'Расход', newTitle: 'Новый расход', addBtn: 'Расход', listTitle: 'Расходы за период',
    emptyList: 'Расходов не найдено', added: 'Расход добавлен', delConfirm: 'Удалить расход?',
    noCats: 'Нет ни одной активной категории расходов — добавьте хотя бы одну ниже', catTitle: 'Категории расходов',
    byRoomTitle: 'Расходы по номерам',
  },
  income: {
    kind: 'income', api: '/api/incomes', catApi: '/api/income-categories', csv: 'incomes', catColor: '#2F5D50',
    tab: 'Прочие доходы', one: 'Доход', newTitle: 'Новый доход', addBtn: 'Доход', listTitle: 'Доходы за период',
    emptyList: 'Доходов не найдено', added: 'Доход добавлен', delConfirm: 'Удалить запись о доходе?',
    noCats: 'Нет ни одной активной категории доходов — добавьте хотя бы одну ниже', catTitle: 'Категории доходов',
    byRoomTitle: 'Доходы по номерам',
  },
};

export async function loadScopes() {
  if (!G.scopeCache) {
    G.scopeCache = await Promise.all(state.me.properties.map(async (p) => {
      const full = await api('GET', `/api/properties/${p.id}`);
      return { id: p.id, name: p.name, rooms: full.room_types.flatMap((t) => t.rooms.map((r) => ({ id: r.id, name: r.name, type: t.name }))) };
    }));
  }
  return G.scopeCache;
}
export function scopeSelect(scopes, current, { general = true, extra = [], attrs = {} } = {}) {
  const sel = h('select', { class: 'input', ...attrs });
  extra.forEach(([v, l]) => sel.append(h('option', { value: v }, l)));
  if (general) sel.append(h('option', { value: '' }, 'Общий — по всем объектам'));
  scopes.forEach((p) => {
    const grp = h('optgroup', { label: p.name }, h('option', { value: `p:${p.id}` }, `${p.name} — весь объект`));
    p.rooms.forEach((r) => grp.append(h('option', { value: `r:${r.id}` }, `№${r.name} · ${r.type} (${p.name})`)));
    sel.append(grp);
  });
  sel.value = current;
  return sel;
}
export const scopePayload = (v) => (v.startsWith('r:') ? { room_id: v.slice(2), property_id: null }
  : v.startsWith('p:') ? { property_id: v.slice(2), room_id: null } : { property_id: null, room_id: null });
export const scopeOf = (row) => (row.room_id ? `r:${row.room_id}` : row.property_id ? `p:${row.property_id}` : '');
export const scopeLabel = (row) => (row.property_name ? `${row.property_name}${row.room_name ? ` · №${row.room_name}` : ''}` : 'Общий');

export function flowDrawer(cfg, cats, scopes, rec, onSaved) {
  const readOnly = !can('manager');
  const g = {};
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  g.date = h('input', { class: 'input', type: 'date', value: rec.date || todayISO(), disabled: readOnly });
  g.amount = h('input', { class: 'input', money: true, type: 'number', inputmode: 'decimal', min: 0, step: '0.01', value: rec.amount != null ? Number(rec.amount) : '', disabled: readOnly });
  g.category_id = h('select', { class: 'input', disabled: readOnly }, cats.map((c) => h('option', { value: c.id, selected: c.id === rec.category_id }, c.name)));
  g.scope = scopeSelect(scopes, scopeOf(rec), { attrs: { disabled: readOnly } });
  g.comment = h('textarea', { class: 'input', disabled: readOnly }, rec.comment || '');
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; err.style.display = 'none';
    try {
      const payload = { date: g.date.value, amount: g.amount.value, category_id: g.category_id.value, comment: g.comment.value, ...scopePayload(g.scope.value) };
      if (rec.id) await api('PATCH', `${cfg.api}/${rec.id}`, payload);
      else await api('POST', cfg.api, payload);
      closeDrawer(); toast(rec.id ? 'Сохранено' : cfg.added); onSaved();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, rec.id ? 'Сохранить' : 'Добавить');
  const foot = readOnly ? null : [h('span', { class: 'spacer' }), save];
  if (rec.id && can('owner')) {
    foot.unshift(h('button', { class: 'btn ghost danger', onclick: async () => {
      if (!confirm(cfg.delConfirm)) return;
      try { await api('DELETE', `${cfg.api}/${rec.id}`); closeDrawer(); toast('Удалено'); onSaved(); }
      catch (ex) { toast(ex.message, true); }
    } }, 'Удалить'));
  }
  openDrawer(rec.id ? cfg.one : cfg.newTitle, h('div', {}, err,
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Дата'), g.date),
      h('label', { class: 'field' }, h('span', {}, 'Сумма, ₽'), g.amount)),
    h('label', { class: 'field' }, h('span', {}, 'Категория'), g.category_id),
    h('label', { class: 'field' }, h('span', {}, 'Относится к'), g.scope),
    h('p', { class: 'muted small', style: { marginTop: '-6px' } }, 'Можно записать на весь объект, на конкретный номер или оставить общим — тогда сумма делится между объектами пропорционально числу номеров.'),
    h('label', { class: 'field' }, h('span', {}, 'Комментарий'), g.comment)),
  foot);
}

export async function viewExpenses(main) {
  G.scopeCache = null;
  let cfg = FLOW[state.financeKind] || FLOW.expense;
  const filters = { from: addDays(todayISO(), -30), to: addDays(todayISO(), 1), scope: `p:${state.propertyId}`, category_id: '' };
  let quickCat = null;
  const content = h('div', { class: 'stack' });
  const tabs = h('div', { class: 'seg' });
  const drawTabs = () => {
    tabs.innerHTML = '';
    Object.values(FLOW).forEach((f) => tabs.append(h('button', { class: f === cfg ? 'on' : '', onclick: () => {
      cfg = f; state.financeKind = f.kind; store.set('finance_kind', f.kind); filters.category_id = ''; quickCat = null; drawTabs(); csvBtn.lastChild.textContent = ' CSV'; run();
    } }, f.tab)));
  };
  const flowQuery = () => ({
    from: filters.from, to: filters.to, category_id: filters.category_id,
    property_id: filters.scope === 'none' ? 'none' : filters.scope.startsWith('p:') ? filters.scope.slice(2) : undefined,
    room_id: filters.scope.startsWith('r:') ? filters.scope.slice(2) : undefined,
  });
  const csvBtn = h('button', { class: 'btn', onclick: () => downloadCsv(`${cfg.api}/export.csv?` + qs(flowQuery()), `${cfg.csv}_${filters.from}_${filters.to}.csv`) },
    icon('download'), ' CSV');
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Финансы'), tabs, csvBtn), content);
  drawTabs();

  async function load() {
    const [scopes, cats, data] = await Promise.all([
      loadScopes(), api('GET', cfg.catApi), api('GET', cfg.api + '?' + qs(flowQuery()))]);
    content.innerHTML = '';

    // быстрое добавление: сумма → категория → сохранить
    const amountInp = h('input', { class: 'input', money: true, type: 'number', inputmode: 'decimal', min: 0, step: '0.01', placeholder: 'Сумма, ₽', style: { width: '150px' } });
    const dateInp = h('input', { class: 'input', type: 'date', value: todayISO(), style: { width: '150px' } });
    const quickScope = scopeSelect(scopes, filters.scope.startsWith('p:') || filters.scope.startsWith('r:') ? filters.scope : '', { attrs: { style: 'width:220px', 'aria-label': 'Относится к' } });
    const chips = h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } });
    const quickSave = h('button', { class: 'btn primary', disabled: true, onclick: async () => {
      quickSave.disabled = true;
      try {
        await api('POST', cfg.api, { amount: amountInp.value, category_id: quickCat, date: dateInp.value, ...scopePayload(quickScope.value) });
        amountInp.value = ''; quickCat = null; toast(cfg.added); load();
      } catch (ex) { toast(ex.message, true); quickSave.disabled = false; }
    } }, 'Сохранить');
    const drawChips = () => {
      chips.innerHTML = '';
      cats.forEach((c) => chips.append(h('button', {
        type: 'button', class: 'btn small' + (quickCat === c.id ? ' primary' : ''),
        style: quickCat === c.id ? {} : { borderColor: c.color },
        onclick: () => { quickCat = c.id; drawChips(); quickSave.disabled = false; },
      }, h('i', { class: 'dot', style: { background: c.color } }), c.name)));
    };
    drawChips();
    if (can('manager')) {
      content.append(h('div', { class: 'card card-pad' },
        h('h3', { style: { marginBottom: '10px' } }, 'Быстрое добавление'),
        cats.length
          ? [h('div', { class: 'quick-row' }, amountInp, dateInp, quickScope, quickSave), chips]
          : h('div', { class: 'empty' }, cfg.noCats)));
    }

    // фильтры
    const scopeSel = scopeSelect(scopes, filters.scope, { general: false, extra: [['', 'Все записи'], ['none', 'Только общие']], attrs: { style: 'width:230px' } });
    scopeSel.addEventListener('change', () => { filters.scope = scopeSel.value; load(); });
    const catSel = h('select', { class: 'input', style: { width: '190px' } }, h('option', { value: '' }, 'Все категории'),
      cats.map((c) => h('option', { value: c.id, selected: c.id === filters.category_id }, c.name)));
    catSel.addEventListener('change', () => { filters.category_id = catSel.value; load(); });
    const fromInp = h('input', { class: 'input', type: 'date', value: filters.from, style: { width: '150px' } });
    const toInp = h('input', { class: 'input', type: 'date', value: filters.to, style: { width: '150px' } });
    fromInp.addEventListener('change', () => { filters.from = fromInp.value; load(); });
    toInp.addEventListener('change', () => { filters.to = toInp.value; load(); });
    content.append(h('div', { class: 'board-tools filters' }, fromInp, h('span', { class: 'dash' }, '—'), toInp, scopeSel, catSel,
      can('manager') && cats.length ? h('button', { class: 'btn primary add-btn', style: { marginLeft: 'auto' },
        onclick: () => flowDrawer(cfg, cats, scopes, {}, load) }, icon('plus'), cfg.addBtn) : null));

    // итоги
    const rowsWithRoom = data.rows.filter((r) => r.room_id);
    content.append(h('div', { class: 'kpis' },
      kpiCard(cfg.kind === 'expense' ? 'Расходов за период' : 'Доходов за период', fmtMoney(data.total)),
      kpiCard('Записей', String(data.rows.length)),
      kpiCard('Самая крупная категория', data.by_category[0] ? data.by_category[0].category_name : '—', null, null, true),
      kpiCard('Записано на номера', fmtMoney(rowsWithRoom.reduce((s, r) => s + Number(r.amount), 0)))));

    // список
    const table = h('div', { class: 'card' });
    if (!data.rows.length) {
      table.append(h('div', { class: 'empty' }, h('h3', {}, cfg.emptyList), 'Измените период или фильтры.'));
    } else {
      table.append(h('div', { class: 'card-head' }, h('h2', {}, cfg.listTitle), h('b', {}, fmtMoney(data.total))),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' },
          h('thead', {}, h('tr', {}, ['Дата', 'Категория', 'Относится к', 'Сумма', 'Комментарий', 'Добавил'].map((t) => h('th', {}, t)))),
          h('tbody', {}, data.rows.map((r) => h('tr', { class: 'click', onclick: () => flowDrawer(cfg, cats, scopes, r, load) },
            h('td', { class: 'num', 'data-l': 'Дата' }, fmtShort(r.date)),
            h('td', { 'data-l': 'Категория' }, h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, h('i', { class: 'dot', style: { background: r.category_color } }), r.category_name)),
            h('td', { class: 'muted small', 'data-l': 'Относится к' }, scopeLabel(r)),
            h('td', { class: 'num strong', 'data-l': 'Сумма' }, fmtMoney(r.amount)),
            h('td', { class: 'muted small', 'data-l': 'Комментарий' }, r.comment),
            h('td', { class: 'muted small', 'data-l': 'Добавил' }, r.created_by_name || '—')))))));
    }
    content.append(table);

    // итоги по категориям и по номерам
    const summaryRow = h('div', { class: 'grid-2' });
    if (data.by_category.length) {
      const maxAmt = Math.max(1, ...data.by_category.map((x) => Number(x.amount)));
      summaryRow.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'По категориям')),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, data.by_category.map((x) => h('tr', {},
          h('td', {}, h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, h('i', { class: 'dot', style: { background: x.category_color } }), x.category_name)),
          h('td', { class: 'num' }, x.count), h('td', { class: 'num' }, fmtMoney(x.amount)),
          h('td', { style: { width: '30%' } }, h('div', { class: 'bar-h' }, h('i', { style: { width: `${(Number(x.amount) / maxAmt) * 100}%`, background: x.category_color } }))))))))));
    }
    if (rowsWithRoom.length) {
      const byRoom = {};
      rowsWithRoom.forEach((r) => {
        const k = r.room_id;
        const e = byRoom[k] ||= { name: r.room_name, property: r.property_name, amount: 0, count: 0 };
        e.amount += Number(r.amount); e.count += 1;
      });
      const list = Object.values(byRoom).sort((a, b) => b.amount - a.amount);
      const maxRoom = Math.max(1, ...list.map((x) => x.amount));
      summaryRow.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, cfg.byRoomTitle)),
        h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, list.map((x) => h('tr', {},
          h('td', {}, `№${x.name}`, state.me.properties.length > 1 ? h('div', { class: 'muted small' }, x.property) : null),
          h('td', { class: 'num' }, x.count), h('td', { class: 'num' }, fmtMoney(x.amount)),
          h('td', { style: { width: '30%' } }, h('div', { class: 'bar-h' }, h('i', { style: { width: `${(x.amount / maxRoom) * 100}%`, background: 'var(--pine)' } }))))))))));
    }
    if (summaryRow.children.length) content.append(summaryRow);

    // категории (владелец управляет, остальные видят список)
    content.append(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, cfg.catTitle),
      can('owner') ? h('button', { class: 'btn small', onclick: () => categoryDrawer({ onSaved: load }, cfg) }, icon('plus'), 'Своя категория') : null),
      h('div', { class: 'card-pad', style: { display: 'flex', gap: '8px', flexWrap: 'wrap', paddingTop: '10px' } },
        cats.map((c) => h('button', { class: 'btn small' + (can('owner') ? '' : ' ghost'), style: { borderColor: c.color },
          onclick: () => can('owner') && categoryDrawer({ ...c, onSaved: load }, cfg) }, h('i', { class: 'dot', style: { background: c.color } }), c.name))),
      !can('owner') ? h('p', { class: 'muted small card-pad', style: { paddingTop: 0 } }, 'Свои категории добавляет владелец аккаунта.') : null));

    // повторяющиеся расходы (только для расходов)
    if (cfg.kind === 'expense') {
      const recurring = await api('GET', '/api/expense-recurring');
      const recCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Повторяющиеся расходы'),
        can('owner') ? h('button', { class: 'btn small', onclick: () => recurringDrawer(cats, {}, state.me.properties, load) }, icon('plus'), 'Добавить') : null));
      if (!recurring.length) {
        recCard.append(h('div', { class: 'empty' }, 'Пока нет ни одного шаблона. Например: аренда 1-го числа или интернет 10-го.'));
      } else {
        recCard.append(h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, recurring.map((r) => h('tr', { class: can('owner') ? 'click' : '', onclick: () => can('owner') && recurringDrawer(cats, r, state.me.properties, load) },
          h('td', {}, h('span', { style: { display: 'inline-flex', gap: '7px', alignItems: 'center' } }, h('i', { class: 'dot', style: { background: r.category_color } }), r.category_name),
            !r.active ? h('span', { class: 'pill none', style: { marginLeft: '8px' } }, 'выключен') : null),
          h('td', { class: 'muted small' }, r.property_name || 'Общий'),
          h('td', { class: 'num' }, fmtMoney(r.amount)),
          h('td', { class: 'muted small' }, `${r.day_of_month}-го числа`),
          h('td', { class: 'muted small' }, r.comment)))))));
      }
      content.append(recCard);
    }
  }
  const run = () => { content.innerHTML = ''; content.append(loadingBox()); load().catch((ex) => { content.innerHTML = ''; content.append(h('div', { class: 'card empty' }, ex.message)); }); };
  run();
}
