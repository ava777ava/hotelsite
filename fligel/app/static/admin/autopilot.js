// Флигель — интерфейс администратора (раздел «автопилот»). ES-модуль без сборки.
import { api, closeModal, fmtDateTime, fmtShort, h, icon, openModal, toast } from './core.js';
import { plural } from './ui.js';

const DAYS = ['день', 'дня', 'дней'];
const STATUS = { done: ['ok', 'выполнено'], skipped: ['warn', 'пропущено'], error: ['bad', 'ошибка'] };
const SOURCE_LABEL = { manual: 'вручную', direct: 'сайт', avito: 'Авито', yandex: 'Яндекс', sutochno: 'Суточно', ostrovok: 'Островок', other: 'другое' };

// Человеческое описание правила: «За 1 день до заезда (после 12:00), если есть долг → письмо гостю»
export function describe(r, data) {
  const n = r.offset_days;
  const when = {
    before_checkin: `За ${n} ${plural(n, DAYS)} до заезда`, checkin_day: 'В день заезда', checkout_day: 'В день выезда',
    after_checkout: n ? `Через ${n} ${plural(n, DAYS)} после выезда` : 'В день выезда',
    new_booking: 'Сразу, как появилась новая бронь', debt: n ? `Через ${n} ${plural(n, DAYS)} после выезда, если остался долг` : 'В день выезда, если остался долг',
  }[r.event];
  const bits = [r.event === 'new_booking' ? when : `${when}, после ${String(r.at_hour).padStart(2, '0')}:00`];
  if (r.only_unpaid && r.event !== 'debt') bits.push('если есть долг');
  if (r.sources.length) bits.push(`только: ${r.sources.map((s) => SOURCE_LABEL[s] || s).join(', ')}`);
  if (r.property_id) bits.push(`объект «${(data.properties.find((p) => p.id === r.property_id) || {}).name || '—'}»`);
  return `${bits.join(', ')} → ${data.actions[r.action].replace(/ \(.*\)/, '').toLowerCase()}`;
}

function ruleDialog(rule, data, onDone) {
  const isNew = !rule.id;
  const preset = !!rule.preset;
  const p = rule.params || {};
  const f = {};
  f.name = h('input', { class: 'input', value: rule.name || '', maxlength: 120, disabled: preset, placeholder: 'Например: «Встретить гостя с детьми»' });
  f.event = h('select', { class: 'input', disabled: preset, onchange: sync }, Object.entries(data.events).map(([k, l]) => h('option', { value: k, selected: (rule.event || 'before_checkin') === k }, l)));
  f.offset_days = h('input', { class: 'input', type: 'number', min: 0, max: 60, value: rule.offset_days ?? 1 });
  f.at_hour = h('input', { class: 'input', type: 'number', min: 0, max: 23, value: rule.at_hour ?? 10 });
  f.only_unpaid = h('input', { type: 'checkbox', checked: !!rule.only_unpaid });
  f.property_id = h('select', { class: 'input' }, h('option', { value: '' }, 'Все объекты'), data.properties.map((x) => h('option', { value: x.id, selected: x.id === rule.property_id }, x.name)));
  const picked = new Set(rule.sources || []);
  const srcBox = h('div', { class: 'chips' }, data.sources.map((s) => {
    const b = h('button', { type: 'button', class: `chip${picked.has(s) ? ' on' : ''}`, onclick: () => { if (picked.has(s)) picked.delete(s); else picked.add(s); b.classList.toggle('on'); } }, SOURCE_LABEL[s] || s);
    return b;
  }));
  f.action = h('select', { class: 'input', disabled: preset, onchange: sync }, Object.entries(data.actions).map(([k, l]) => h('option', { value: k, selected: (rule.action || 'notify_staff') === k }, l)));

  // поля действия
  const lastText = { el: null };
  const text = (label, key, rows = 3, ph = '') => {
    const el = h('textarea', { class: 'input', rows, placeholder: ph, onfocus: () => { lastText.el = el; } }, p[key] || '');
    f[key] = el; return h('label', { class: 'field' }, h('span', {}, label), el);
  };
  const line = (label, key, ph = '') => {
    const el = h('input', { class: 'input', value: p[key] || '', placeholder: ph, onfocus: () => { lastText.el = el; } });
    f[key] = el; return h('label', { class: 'field' }, h('span', {}, label), el);
  };
  const staffSel = h('select', { class: 'input' }, h('option', { value: '' }, 'Любой сотрудник'), data.staff.map((u) => h('option', { value: u.id, selected: u.id === p.assignee_id }, u.name)));
  const chk = (key, label, def = true) => { f['p_' + key] = h('input', { type: 'checkbox', checked: p[key] ?? def }); return h('label', { class: 'check' }, f['p_' + key], ' ' + label); };
  const statusSel = h('select', { class: 'input' }, [['dirty', 'Нужна уборка'], ['inspect', 'Ждёт проверки']].map(([k, l]) => h('option', { value: k, selected: (p.status || 'dirty') === k }, l)));
  const dueIn = h('input', { class: 'input', type: 'number', min: 0, max: 60, value: p.due_in_days ?? 0 });
  // готовые шаблоны сообщений гостю (раздел «Гости») можно взять за основу текста письма
  const tplPick = h('label', { class: 'field' }, h('span', {}, 'Взять текст из шаблона'));
  const tplSel = h('select', { class: 'input', onchange: () => { const t = tpls.find((x) => x.id === tplSel.value); if (t) { f.body.value = t.body; if (!f.subject.value) f.subject.value = t.name; } tplSel.value = ''; } }, h('option', { value: '' }, 'Выбрать…'));
  let tpls = [];
  tplPick.append(tplSel);
  api('GET', '/api/message-templates').then((r) => { tpls = r.items; tpls.forEach((t) => tplSel.append(h('option', { value: t.id }, t.name))); }).catch(() => { tplPick.style.display = 'none'; });
  const paramBox = {
    notify_staff: h('div', {}, text('Текст сообщения сотрудникам', 'text', 3, 'Гость {гость} выезжает, не оплачено {сумма к оплате}')),
    email_guest: h('div', {}, line('Тема письма', 'subject', '{объект}: как заселиться'), tplPick, text('Текст письма', 'body', 7), chk('notify_if_missing', 'Если у гостя нет email — напомнить сотрудникам')),
    create_task: h('div', {}, line('Название задачи', 'title', 'Подготовить номер {номер} для {гость}'), text('Описание (необязательно)', 'description', 2),
      h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Кому'), staffSel), h('label', { class: 'field' }, h('span', {}, 'Срок: через сколько дней'), dueIn)), chk('notify', 'Сообщить сотрудникам о новой задаче')),
    set_cleaning: h('div', {}, h('label', { class: 'field' }, h('span', {}, 'Какой статус поставить номеру'), statusSel), chk('notify', 'Сообщить сотрудникам'),
      h('div', { class: 'muted small' }, 'Если номер уже убран после выезда или у него уже есть статус, ничего не меняется.')),
  };
  const offsetField = h('label', { class: 'field' }, h('span', {}, 'Сколько дней'), f.offset_days);
  const hourField = h('label', { class: 'field' }, h('span', {}, 'Не раньше (час)'), f.at_hour);
  const unpaidField = h('label', { class: 'check', style: { marginBottom: '10px' } }, f.only_unpaid, ' Только если по брони есть долг');
  function sync() {
    const ev = f.event.value;
    offsetField.style.display = ['before_checkin', 'after_checkout', 'debt'].includes(ev) ? '' : 'none';
    hourField.style.display = ev === 'new_booking' ? 'none' : '';
    unpaidField.style.display = ev === 'debt' ? 'none' : '';
    Object.entries(paramBox).forEach(([k, el]) => { el.style.display = f.action.value === k ? '' : 'none'; });
  }
  const chips = h('div', { class: 'chips ph-chips' }, data.placeholders.map((x) => h('button', { type: 'button', class: 'chip', title: 'Вставить в текст', onclick: () => {
    const el = lastText.el; if (!el) { toast('Сначала щёлкните в поле текста', true); return; }
    const a = el.selectionStart ?? el.value.length; el.value = el.value.slice(0, a) + `{${x}}` + el.value.slice(el.selectionEnd ?? a); el.focus();
  } }, `{${x}}`)));
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const save = async () => {
    const params = {};
    const a = f.action.value;
    if (a === 'notify_staff') params.text = f.text.value;
    if (a === 'email_guest') Object.assign(params, { subject: f.subject.value, body: f.body.value, notify_if_missing: f.p_notify_if_missing.checked });
    if (a === 'create_task') Object.assign(params, { title: f.title.value, description: f.description.value, assignee_id: staffSel.value || null, due_in_days: dueIn.value || 0, notify: f.p_notify.checked });
    if (a === 'set_cleaning') Object.assign(params, { status: statusSel.value, notify: f.p_notify.checked });
    const body = { event: f.event.value, action: a, offset_days: f.offset_days.value || 0, at_hour: f.at_hour.value || 0, only_unpaid: f.only_unpaid.checked,
      sources: [...picked], property_id: f.property_id.value || null, params };
    if (!preset) body.name = f.name.value;
    try {
      if (isNew) await api('POST', '/api/automation/rules', { ...body, enabled: true }); else await api('PATCH', `/api/automation/rules/${rule.id}`, body);
      closeModal(); toast('Сохранено'); onDone();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  };
  openModal(isNew ? 'Новый сценарий' : (preset ? 'Настроить готовый сценарий' : 'Сценарий'), h('div', { class: 'rule-form' }, err,
    preset ? h('div', { class: 'note' }, h('b', {}, rule.name), h('div', { class: 'muted small' }, rule.hint)) : h('label', { class: 'field' }, h('span', {}, 'Название'), f.name),
    h('h3', {}, '1. Когда'), h('label', { class: 'field' }, h('span', {}, 'Событие'), f.event),
    h('div', { class: 'row2' }, offsetField, hourField),
    h('h3', {}, '2. Условия (необязательно)'), unpaidField,
    h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Только брони с источников (ничего не выбрано — любые)'), srcBox),
    data.properties.length > 1 ? h('label', { class: 'field' }, h('span', {}, 'Объект'), f.property_id) : null,
    h('h3', {}, '3. Что сделать'), h('label', { class: 'field' }, h('span', {}, 'Действие'), f.action),
    ...Object.values(paramBox),
    h('div', { class: 'muted small', style: { marginTop: '4px' } }, 'Подставляются данные брони — нажмите на подстановку, чтобы вставить её в текст:'), chips),
  [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: save }, 'Сохранить')]);
  sync();
}

export async function viewAutopilot(main) {
  const box = h('div', { class: 'stack' });
  let data = null;
  const runBtn = h('button', { class: 'btn', title: 'Не ждать планировщик: проверить правила прямо сейчас', onclick: async () => {
    runBtn.disabled = true;
    try { const r = await api('POST', '/api/automation/run', {}); toast(r.fired ? `Сработало: ${r.fired}` : 'Сейчас ничего не подходит под правила'); await load(); }
    catch (ex) { toast(ex.message, true); } finally { runBtn.disabled = false; }
  } }, icon('sync'), 'Проверить сейчас');
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Автопилот'), runBtn,
    h('button', { class: 'btn primary', onclick: () => ruleDialog({}, data, load) }, icon('plus'), 'Новый сценарий')), box);

  const toggle = (r) => {
    const sw = h('button', { type: 'button', class: `switch${r.enabled ? ' on' : ''}`, role: 'switch', 'aria-checked': String(r.enabled), 'aria-label': `Сценарий «${r.name}»: ${r.enabled ? 'включён' : 'выключен'}`, onclick: async () => {
      sw.disabled = true;
      try { await api('PATCH', `/api/automation/rules/${r.id}`, { enabled: !r.enabled }); await load(); } catch (ex) { toast(ex.message, true); sw.disabled = false; }
    } }, h('i'));
    return sw;
  };
  const ruleCard = (r) => h('div', { class: `rule-card${r.enabled ? '' : ' off'}` },
    toggle(r),
    h('div', { class: 'rule-body' }, h('b', {}, r.name), h('div', { class: 'muted small' }, describe(r, data)),
      r.hint ? h('div', { class: 'muted small' }, r.hint) : null,
      h('div', { class: 'hk-tags' }, r.runs ? h('span', { class: 'tag' }, `сработало: ${r.runs}`) : h('span', { class: 'tag' }, 'ещё не срабатывало'),
        r.errors ? h('span', { class: 'tag bad' }, `ошибок: ${r.errors}`) : null, r.last_run_at ? h('span', { class: 'tag' }, `последний раз ${fmtDateTime(r.last_run_at)}`) : null)),
    h('button', { class: 'btn small ghost', onclick: () => ruleDialog(r, data, load) }, 'Настроить'),
    r.preset ? null : h('button', { class: 'btn small ghost', 'aria-label': 'Удалить сценарий', onclick: async () => {
      if (!confirm(`Удалить сценарий «${r.name}»?`)) return;
      try { await api('DELETE', `/api/automation/rules/${r.id}`); load(); } catch (ex) { toast(ex.message, true); }
    } }, icon('trash')));

  function runsTable(items) {
    if (!items.length) return h('div', { class: 'card-pad muted' }, 'Пока ничего не срабатывало. Сценарии проверяются несколько раз в час.');
    return h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, items.map((x) => {
      const [cls, label] = STATUS[x.status];
      return h('tr', {}, h('td', { class: 'muted small', style: { whiteSpace: 'nowrap' } }, fmtDateTime(x.created_at)),
        h('td', {}, h('b', {}, x.rule_name), h('div', { class: 'muted small' }, `${x.guest_name || 'Гость'} · номер ${x.room_name} · ${fmtShort(x.check_in)}–${fmtShort(x.check_out)}`)),
        h('td', { class: 'small' }, x.detail), h('td', {}, h('span', { class: `pill ${cls}` }, label)));
    }))));
  }

  async function load() {
    const [d, runs] = await Promise.all([api('GET', '/api/automation'), api('GET', '/api/automation/runs')]);
    data = d;
    box.innerHTML = '';
    const presets = d.rules.filter((r) => r.preset);
    const custom = d.rules.filter((r) => !r.preset);
    box.append(h('p', { class: 'muted' }, 'Автопилот сам делает рутину: пишет гостю, ставит задачи и статусы уборки. Каждое правило срабатывает по брони один раз; всё, что произошло, видно в журнале ниже. Выключайте любые сценарии, которые вам не нужны.'),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Готовые сценарии')), h('div', { class: 'card-pad' }, presets.map(ruleCard))),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Свои сценарии')),
        h('div', { class: 'card-pad' }, custom.length ? custom.map(ruleCard) : h('div', { class: 'muted' }, 'Здесь появятся сценарии, которые вы создадите сами — например, «если бронь с Авито — поставить задачу подготовить номер».'))),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Журнал срабатываний')), runsTable(runs.items)));
  }
  load().catch((ex) => box.append(h('div', { class: 'card empty' }, ex.message)));
}
