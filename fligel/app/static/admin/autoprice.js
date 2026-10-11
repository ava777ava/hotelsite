// Флигель — интерфейс администратора (раздел «автоцены»). ES-модуль без сборки.
import { api, closeModal, fmtDateTime, fmtMoney, fmtShort, h, icon, openModal, toast } from './core.js';
import { plural } from './ui.js';

const KIND_SHORT = { low_occupancy: 'Низкая загрузка', weekend: 'Выходные', holiday: 'Праздники', last_room: 'Последний номер' };
const WD = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const dayLabel = (s) => `${fmtShort(s)}, ${WD[new Date(s + 'T00:00').getDay()]}`;
const signedPct = (p) => `${Number(p) > 0 ? '+' : ''}${String(Number(p)).replace('.', ',')} %`;

function ruleText(r, data) {
  const t = r.room_type_id ? ` · ${(data.types.find((x) => x.id === r.room_type_id) || {}).name || 'категория'}` : ' · все категории';
  if (r.kind === 'low_occupancy') return `Ближайшие ${r.days_ahead} ${plural(r.days_ahead, ['день', 'дня', 'дней'])}: если занято меньше ${r.threshold} % номеров категории — ${signedPct(r.percent)}${t}`;
  if (r.kind === 'weekend') return `Пятница и суббота: ${signedPct(r.percent)}${t}`;
  if (r.kind === 'holiday') return `Праздничные даты: ${signedPct(r.percent)}${t}`;
  return `Остался один свободный номер категории: ${signedPct(r.percent)}${t}`;
}

function ruleDialog(rule, data, onDone) {
  const isNew = !rule.id;
  const kind = h('select', { class: 'input', disabled: !isNew, onchange: sync }, Object.entries(data.kinds).map(([k, l]) => h('option', { value: k, selected: (rule.kind || 'low_occupancy') === k }, l)));
  const pct = h('input', { class: 'input', type: 'number', step: '1', value: rule.percent != null ? Number(rule.percent) : -10 });
  const days = h('input', { class: 'input', type: 'number', min: 0, max: 180, value: rule.days_ahead ?? 14 });
  const th = h('input', { class: 'input', type: 'number', min: 1, max: 100, value: rule.threshold ?? 40 });
  const type = h('select', { class: 'input' }, h('option', { value: '' }, 'Все категории'), data.types.map((t) => h('option', { value: t.id, selected: t.id === rule.room_type_id }, `${t.name}${data.types.some((x) => x !== t && x.name === t.name) ? ` (${t.property_name})` : ''}`)));
  const lowBox = h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'На сколько дней вперёд'), days), h('label', { class: 'field' }, h('span', {}, 'Если занято меньше, %'), th));
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  function sync() {
    lowBox.style.display = kind.value === 'low_occupancy' ? '' : 'none';
    if (isNew) pct.value = kind.value === 'low_occupancy' ? -10 : 15;
  }
  openModal(isNew ? 'Новое правило цен' : 'Правило цен', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Что должно произойти'), kind), lowBox,
    h('label', { class: 'field' }, h('span', {}, 'На сколько процентов изменить цену (минус — скидка)'), pct),
    h('label', { class: 'field' }, h('span', {}, 'Для какой категории'), type)),
  [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
    const body = { kind: kind.value, percent: pct.value, days_ahead: days.value, threshold: th.value, room_type_id: type.value || null };
    try { if (isNew) await api('POST', '/api/autoprice/rules', body); else await api('PATCH', `/api/autoprice/rules/${rule.id}`, body); closeModal(); toast('Сохранено'); onDone(); }
    catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  } }, 'Сохранить')]);
  sync();
  if (!isNew) pct.value = Number(rule.percent);
}

export async function viewAutoprice(main) {
  const box = h('div', { class: 'stack' });
  let data = null;
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Автоцены'), h('a', { class: 'btn', href: '#/rates' }, 'Календарь цен')), box);

  const reload = () => load().catch((ex) => toast(ex.message, true));
  const modeCard = () => {
    const owner = data.can_edit;
    const horizon = h('input', { class: 'input', type: 'number', min: 7, max: 180, value: data.settings.horizon_days, style: { width: '110px' }, disabled: !owner });
    const modeSeg = h('div', { class: 'seg', style: { flexWrap: 'wrap' } }, Object.entries(data.modes).map(([k, l]) => h('button', {
      type: 'button', class: data.settings.mode === k ? 'on' : '', disabled: !owner, onclick: async () => {
        if (k === 'auto' && !confirm('Автоцены начнут сами менять цены в календаре на ближайшие дни. Каждое изменение сохраняется в журнале, а цену можно вернуть вручную. Включить?')) return;
        try { const r = await api('PUT', '/api/autoprice/settings', { mode: k, horizon_days: horizon.value }); toast(r.applied ? `Цены обновлены: ${r.applied}` : (r.proposed ? `Предложений: ${r.proposed}` : 'Сохранено')); reload(); }
        catch (ex) { toast(ex.message, true); }
      } }, l)));
    return h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Режим')),
      h('div', { class: 'card-pad' }, modeSeg,
        h('div', { class: 'row-inline', style: { marginTop: '12px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' } }, h('span', {}, 'Считать цены на'), horizon, h('span', {}, 'дней вперёд')),
        h('p', { class: 'muted small', style: { marginBottom: 0 } }, data.note), owner ? null : h('p', { class: 'muted small' }, 'Менять настройки может только владелец.')));
  };
  const rulesCard = () => h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Правила'),
    data.can_edit ? h('button', { class: 'btn small', onclick: () => ruleDialog({}, data, reload) }, icon('plus'), 'Правило') : null),
  data.rules.length ? h('div', { class: 'card-pad' }, data.rules.map((r) => h('div', { class: `rule-card${r.enabled ? '' : ' off'}` },
    h('button', { type: 'button', class: `switch${r.enabled ? ' on' : ''}`, role: 'switch', 'aria-checked': String(r.enabled), 'aria-label': `Правило «${KIND_SHORT[r.kind]}»`, disabled: !data.can_edit,
      onclick: async () => { try { await api('PATCH', `/api/autoprice/rules/${r.id}`, { enabled: !r.enabled }); reload(); } catch (ex) { toast(ex.message, true); } } }, h('i')),
    h('div', { class: 'rule-body' }, h('b', {}, KIND_SHORT[r.kind]), h('div', { class: 'muted small' }, ruleText(r, data))),
    data.can_edit ? h('button', { class: 'btn small ghost', onclick: () => ruleDialog(r, data, reload) }, 'Изменить') : null,
    data.can_edit ? h('button', { class: 'btn small ghost', 'aria-label': 'Удалить правило', onclick: async () => { if (!confirm('Удалить правило?')) return; try { await api('DELETE', `/api/autoprice/rules/${r.id}`); reload(); } catch (ex) { toast(ex.message, true); } } }, icon('trash')) : null)))
    : h('div', { class: 'card-pad muted' }, 'Правил пока нет. Например: «в ближайшие 7 дней, если занято меньше 40 % — скидка 10 %» или «пятница и суббота — плюс 15 %».'));

  const suggestionsCard = () => {
    const sg = data.suggestions;
    const act = (label, cls, fn) => h('button', { class: `btn small ${cls}`, onclick: async () => { try { const r = await fn(); toast(r); reload(); } catch (ex) { toast(ex.message, true); } } }, label);
    return h('div', { class: 'card' }, h('div', { class: 'card-head', style: { flexWrap: 'wrap' } }, h('h2', {}, `Предложения${sg.length ? ` · ${sg.length}` : ''}`),
      data.can_edit && sg.length ? h('span', { style: { display: 'flex', gap: '8px' } },
        act('Отклонить все', '', async () => `Отклонено: ${(await api('POST', '/api/autoprice/dismiss', { ids: 'all' })).count}`),
        act('Применить все', 'primary', async () => `Цены применены: ${(await api('POST', '/api/autoprice/apply', { ids: 'all' })).count}`)) : null),
    sg.length ? h('div', { class: 'card-pad' }, sg.map((s) => h('div', { class: 'sg-row' },
      h('div', { class: 'sg-main' }, h('b', {}, dayLabel(s.date)), h('span', { class: 'muted small' }, ` · ${s.type_name}`)),
      h('div', { class: 'sg-price' }, fmtMoney(s.current_price), ' → ', h('b', {}, fmtMoney(s.suggested_price))),
      h('div', { class: 'sg-why small muted' }, s.reasons),
      data.can_edit ? h('div', { class: 'sg-act' }, act('Применить', '', async () => { await api('POST', '/api/autoprice/apply', { ids: [s.id] }); return 'Цена применена'; }),
        h('button', { class: 'btn small ghost', 'aria-label': 'Отклонить', onclick: async () => { try { await api('POST', '/api/autoprice/dismiss', { ids: [s.id] }); reload(); } catch (ex) { toast(ex.message, true); } } }, icon('close'))) : null)))
      : h('div', { class: 'card-pad muted' }, data.settings.mode === 'suggest' ? 'Сейчас предложений нет — цены соответствуют правилам.' : (data.settings.mode === 'auto' ? 'В режиме «менять цены самим» предложений нет — смотрите журнал ниже.' : 'Включите режим «Только предлагать» — здесь появятся предложения.')));
  };
  const journalCard = () => h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Журнал изменений цен')),
    data.changes.length ? h('div', { class: 'card-pad' }, data.changes.map((c) => h('div', { class: 'sg-row' },
      h('div', { class: 'sg-main' }, h('b', {}, dayLabel(c.date)), h('span', { class: 'muted small' }, ` · ${c.type_name}`)),
      h('div', { class: 'sg-price' }, c.old_price != null ? fmtMoney(c.old_price) : 'базовая', ' → ', h('b', {}, fmtMoney(c.new_price))),
      h('div', { class: 'sg-why small muted' }, c.reasons, ' · ', c.source === 'auto' ? 'автоматически' : `применил(а) ${c.user_name || '—'}`, ' · ', fmtDateTime(c.created_at)))))
      : h('div', { class: 'card-pad muted' }, 'Изменений пока не было.'));

  async function load() {
    data = await api('GET', '/api/autoprice');
    box.innerHTML = '';
    box.append(h('p', { class: 'muted' }, 'Цены подстраиваются под загрузку: скидка, когда ближайшие даты пустуют, и наценка на выходные, праздники и последний свободный номер. Сначала включите режим «Только предлагать» и посмотрите, что система хочет изменить.'),
      modeCard(), rulesCard(), suggestionsCard(), journalCard());
  }
  load().catch((ex) => box.append(h('div', { class: 'card empty' }, ex.message)));
}
