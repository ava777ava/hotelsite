// Флигель — интерфейс администратора (раздел «задачи команды»). ES-модуль без сборки.
import { autoRefresh, refreshBadges } from './app.js';
import { api, can, closeModal, fmtDate, h, icon, openModal, qs, state, todayISO, toast } from './core.js';
import { plural } from './ui.js';

const SCOPES = [['open', 'Открытые'], ['overdue', 'Просроченные'], ['done', 'Сделанные']];

// Подпись срока: «сегодня», «завтра», «просрочено на 3 дня»
function dueLabel(t) {
  if (!t.due_date) return null;
  const days = Math.round((new Date(t.due_date + 'T00:00') - new Date(todayISO() + 'T00:00')) / 86400000);
  if (t.done_at) return `срок был ${fmtDate(t.due_date)}`;
  if (days < 0) return `просрочено на ${-days} ${plural(-days, 'день', 'дня', 'дней')}`;
  if (days === 0) return 'сегодня';
  if (days === 1) return 'завтра';
  return `до ${fmtDate(t.due_date)}`;
}

export function taskDialog(task, data, onDone) {
  const isNew = !task.id;
  const title = h('input', { class: 'input', value: task.title || '', maxlength: 200, placeholder: 'Например: заменить лампочку в 101' });
  const desc = h('textarea', { class: 'input', placeholder: 'Подробности (необязательно)' }, task.description || '');
  const assignee = h('select', { class: 'input' }, h('option', { value: '' }, 'Не назначено (любой сотрудник)'),
    data.staff.map((u) => h('option', { value: u.id, selected: u.id === task.assignee_id }, u.name)));
  const due = h('input', { class: 'input', type: 'date', value: task.due_date || '' });
  const room = h('select', { class: 'input' }, h('option', { value: '' }, 'Без привязки к номеру'),
    data.rooms.map((r) => h('option', { value: r.id, selected: r.id === task.room_id }, `${r.name} · ${r.property_name}`)));
  const rec = h('select', { class: 'input' }, Object.entries(data.recurrence).map(([k, l]) => h('option', { value: k, selected: (task.recurrence || 'none') === k }, l)));
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const save = async () => {
    const body = { title: title.value, description: desc.value, assignee_id: assignee.value || null, due_date: due.value || null, room_id: room.value || null, recurrence: rec.value };
    try {
      if (isNew) await api('POST', '/api/tasks', body); else await api('PATCH', `/api/tasks/${task.id}`, body);
      closeModal(); toast('Сохранено'); onDone();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  };
  openModal(isNew ? 'Новая задача' : 'Задача', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Что нужно сделать'), title),
    h('label', { class: 'field' }, h('span', {}, 'Описание'), desc),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Кому'), assignee), h('label', { class: 'field' }, h('span', {}, 'Срок'), due)),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Номер'), room), h('label', { class: 'field' }, h('span', {}, 'Повтор'), rec)),
    h('div', { class: 'muted small' }, 'Повторяющаяся задача после отметки «Сделано» сразу появляется снова — через неделю или месяц от срока.')),
  [isNew ? null : h('button', { class: 'btn danger', onclick: async () => {
    if (!confirm('Удалить задачу?')) return;
    try { await api('DELETE', `/api/tasks/${task.id}`); closeModal(); onDone(); } catch (ex) { toast(ex.message, true); }
  } }, 'Удалить'), h('span', { class: 'spacer' }), h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'),
  h('button', { class: 'btn primary', onclick: save }, 'Сохранить')]);
}

export async function viewTasks(main) {
  const manager = can('manager');
  let scope = 'open';
  let assignee = '';
  let data = null;
  const list = h('div', { class: 'stack' });
  const sum = h('div', { class: 'hk-sum' });
  const seg = h('div', { class: 'seg' });
  const who = h('select', { class: 'input', style: { maxWidth: '220px' }, 'aria-label': 'Исполнитель', onchange: (e) => { assignee = e.target.value; load(); } });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Задачи'),
    manager ? h('button', { class: 'btn primary', onclick: () => taskDialog({}, data || { staff: [], rooms: [], recurrence: { none: 'Не повторять' } }, load) }, icon('plus'), 'Новая задача') : null),
  sum, h('div', { class: 'toolbar', style: { display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '12px' } }, seg, manager ? who : null), list);
  const drawSeg = () => {
    seg.innerHTML = '';
    SCOPES.forEach(([k, l]) => seg.append(h('button', { type: 'button', class: scope === k ? 'on' : '', onclick: () => { scope = k; drawSeg(); load(); } },
      l, k === 'overdue' && data?.counts.overdue ? ` · ${data.counts.overdue}` : '')));
  };
  const setDone = async (t, undo) => {
    try { await api('POST', `/api/tasks/${t.id}/done`, { undo }); toast(undo ? 'Задача снова в работе' : 'Готово'); await load(); refreshBadges(); }
    catch (ex) { toast(ex.message, true); }
  };
  const card = (t) => h('div', { class: `task-card${t.overdue ? ' overdue' : ''}${t.done_at ? ' done' : ''}` },
    h('button', { type: 'button', class: 'task-check', 'aria-label': t.done_at ? 'Вернуть в работу' : 'Отметить сделанной', title: t.done_at ? 'Вернуть в работу' : 'Сделано',
      onclick: () => setDone(t, !!t.done_at) }, t.done_at ? '✓' : ''),
    h('div', { class: 'task-body', onclick: manager && !t.done_at ? () => taskDialog(t, data, load) : null },
      h('b', { class: 'task-title' }, t.title),
      t.description ? h('div', { class: 'muted small task-desc' }, t.description) : null,
      h('div', { class: 'hk-tags' },
        t.due_date ? h('span', { class: `tag${t.overdue ? ' bad' : ''}` }, dueLabel(t)) : null,
        t.assignee_name ? h('span', { class: 'tag' }, t.assignee_name) : (manager ? h('span', { class: 'tag' }, 'не назначено') : null),
        t.room_name ? h('span', { class: 'tag' }, `номер ${t.room_name}`) : null,
        t.recurrence === 'weekly' ? h('span', { class: 'tag' }, 'каждую неделю') : (t.recurrence === 'monthly' ? h('span', { class: 'tag' }, 'каждый месяц') : null),
        t.source === 'automation' ? h('span', { class: 'tag' }, 'автопилот') : null,
        t.done_at ? h('span', { class: 'tag ok' }, `сделал(а): ${t.done_by_name || '—'}`) : null)));
  function draw() {
    sum.innerHTML = '';
    sum.append(h('span', { class: 'hk-pill hk-inspect' }, `Открыто: ${data.counts.open}`));
    if (data.counts.today) sum.append(h('span', { class: 'hk-pill hk-cleaning' }, `На сегодня: ${data.counts.today}`));
    if (data.counts.overdue) sum.append(h('span', { class: 'hk-pill hk-repair' }, `Просрочено: ${data.counts.overdue}`));
    if (manager) {
      const keep = assignee;
      who.innerHTML = '';
      who.append(h('option', { value: '' }, 'Все сотрудники'), h('option', { value: 'me', selected: keep === 'me' }, 'Мои'),
        data.staff.map((u) => h('option', { value: u.id, selected: keep === u.id }, u.name)));
    }
    list.innerHTML = '';
    if (!data.items.length) {
      list.append(h('div', { class: 'card empty' }, h('h3', {}, scope === 'done' ? 'За последние 30 дней ничего не закрыто' : (scope === 'overdue' ? 'Просроченных задач нет' : 'Открытых задач нет')),
        manager && scope === 'open' ? 'Поручите сотруднику, например «заменить лампочку» или «принять бельё из прачечной» — он отметит выполнение с телефона.' : ''));
      return;
    }
    list.append(data.items.map(card));
  }
  async function load() {
    data = await api('GET', '/api/tasks?' + qs({ scope, assignee }));
    drawSeg(); draw();
  }
  drawSeg();
  load().catch((ex) => list.append(h('div', { class: 'card empty' }, ex.message)));
  autoRefresh(load);
}
