// Флигель — «Площадки → Состояние синхронизации» и режим отладки (сырые .ics). ES-модуль без сборки.
import { ago, api, fmtDateTime, h, openDrawer, state, toast } from './core.js';

const download = (name, text) => {
  const a = h('a', { href: URL.createObjectURL(new Blob([text], { type: 'text/calendar;charset=utf-8' })), download: name });
  document.body.append(a); a.click(); a.remove();
};

function snapshotView(id, onBack) {
  const box = h('div', { class: 'stack' }, h('div', { class: 'muted' }, 'Загружаю…'));
  api('GET', `/api/sync/snapshots/${id}`).then((s) => {
    box.innerHTML = '';
    box.append(
      h('div', { class: 'muted small' }, `${s.kind === 'received' ? 'Получено от площадки' : 'Отдано площадке'} · ${fmtDateTime(s.created_at)} · ${s.size} байт · событий: ${s.events}${s.note ? ` · ${s.note}` : ''}`),
      h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
        h('button', { class: 'btn small', onclick: onBack }, 'К списку'),
        h('button', { class: 'btn small', onclick: () => download(`calendar-${s.channel}-${s.id}.ics`, s.body) }, 'Скачать .ics'),
        h('button', { class: 'btn small', onclick: async () => { try { await navigator.clipboard.writeText(s.body); toast('Скопировано'); } catch { toast('Не удалось скопировать', true); } } }, 'Копировать')),
      h('pre', { style: { whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: '12px', background: 'var(--surface-2)', padding: '10px', borderRadius: '8px', maxHeight: '60vh', overflow: 'auto', margin: 0 } }, s.body));
  }).catch((ex) => { box.innerHTML = ''; box.append(h('div', { class: 'empty' }, ex.message)); });
  return box;
}

// Сырые календари одной площадки: «получено» (мы забрали) и «отдано» (мы отдали)
export function rawDrawer(row) {
  const body = h('div', { class: 'stack' });
  let kind = 'received';
  const draw = async () => {
    body.innerHTML = '';
    const seg = h('div', { class: 'seg' }, [['received', 'Получено от площадки'], ['served', 'Отдано площадке']].map(([k, l]) =>
      h('button', { class: kind === k ? 'on' : '', onclick: () => { kind = k; draw(); } }, l)));
    body.append(seg);
    try {
      const q = kind === 'received' ? `kind=received&feed_id=${row.feed_id}` : `kind=served&target_id=${row.target_id}&channel=${row.channel}`;
      const items = (await api('GET', `/api/sync/snapshots?${q}`)).items;
      if (!items.length) { body.append(h('div', { class: 'empty' }, 'Пока ничего не сохранено. Календарь появится здесь после ближайшего обмена с площадкой.')); return; }
      body.append(h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, items.map((s) => h('tr', { class: 'click', onclick: () => { body.innerHTML = ''; body.append(snapshotView(s.id, draw)); } },
        h('td', {}, fmtDateTime(s.created_at), h('div', { class: 'muted small' }, s.seen_count > 1 ? `повторялся ${s.seen_count} раз, последний — ${ago(s.last_seen_at)}` : '')),
        h('td', {}, `событий: ${s.events}`), h('td', {}, s.status === 'error' ? h('span', { class: 'pill bad', title: s.note }, 'не разобран') : h('span', { class: 'pill ok' }, 'разобран')),
        h('td', { class: 'muted small' }, `${s.size} Б${s.user_agent ? ` · ${s.user_agent}` : ''}`)))))));
    } catch (ex) { body.append(h('div', { class: 'empty' }, ex.message)); }
  };
  draw();
  openDrawer(`Сырые календари: ${row.channel_label}, ${row.target_name}`, body);
}

export async function drawSyncState(box) {
  box.innerHTML = '';
  const d = await api('GET', '/api/sync/state');
  const isOwner = state.me.role === 'owner';
  if (d.stale) {
    box.append(h('div', { class: 'note', role: 'alert', style: { background: 'var(--ochre-soft)', color: 'var(--ochre-ink)' } },
      `⚠ Площадка не забирала наш календарь больше ${d.stale_hours} ч (отмечено красным ниже). Проверьте, что наша ссылка вставлена на площадке и там включена синхронизация, — иначе брони из нашей системы туда не попадают.`));
  }
  if (!d.items.length) {
    box.append(h('div', { class: 'card empty' }, h('h3', {}, 'Календари площадок не подключены'), 'Подключите календарь на вкладке «Подключение» — здесь появится, когда его забирали и что в нём было.'));
  } else {
    box.append(h('div', { class: 'card' }, h('div', { class: 'table-wrap' }, h('table', { class: 'list cards-mobile' },
      h('thead', {}, h('tr', {}, ['Площадка', 'Что подключено', 'Мы забрали календарь площадки', 'Площадка забрала наш', 'Ошибки', ''].map((x) => h('th', {}, x)))),
      h('tbody', {}, d.items.map((r) => {
        const run = r.last_run;
        const stale = r.export_stale;
        return h('tr', {},
          h('td', { 'data-l': 'Площадка' }, h('b', {}, r.channel_label), !r.enabled ? h('div', { class: 'muted small' }, 'выключен') : null),
          h('td', { 'data-l': 'Что подключено' }, r.target_name),
          h('td', { 'data-l': 'Мы забрали календарь площадки' }, ago(r.last_synced_at), ' ',
            r.last_status === 'error' ? h('span', { class: 'pill bad' }, 'ошибка') : r.last_status === 'ok' ? h('span', { class: 'pill ok' }, 'ок') : null,
            run ? h('div', { class: 'muted small' }, `событий: ${run.events} · эхо отброшено: ${run.echoes} (за 7 дн.: ${Number(r.echoes_7d)})${run.skipped ? ` · не разобрано: ${run.skipped}` : ''}`) : null),
          h('td', { 'data-l': 'Площадка забрала наш', class: stale ? 'down' : '' }, r.exported_at ? ago(r.exported_at) : 'ещё ни разу',
            stale ? h('span', { class: 'pill bad', style: { marginLeft: '6px' } }, `> ${d.stale_hours} ч`) : null,
            h('div', { class: 'muted small' }, r.exported_at ? `раз: ${r.export_count}${r.last_user_agent ? ` · ${r.last_user_agent}` : ''}` : 'вставьте нашу ссылку на площадке')),
          h('td', { 'data-l': 'Ошибки', class: r.last_status === 'error' ? 'down' : 'muted small' }, r.last_status === 'error' ? r.last_error : (r.errors_24h ? `за сутки: ${r.errors_24h}` : '—')),
          h('td', { style: { textAlign: 'right' } }, isOwner ? h('button', { class: 'btn small', title: 'Последние сохранённые календари этой площадки', onclick: () => rawDrawer(r) }, 'Сырые календари') : null));
      }))))));
  }
  if (isOwner) {
    const sw = h('button', { type: 'button', class: `switch${d.debug ? ' on' : ''}`, role: 'switch', 'aria-checked': String(d.debug), 'aria-label': `Режим отладки: ${d.debug ? 'включён' : 'выключен'}`,
      onclick: async () => { try { await api('PUT', '/api/sync/debug', { enabled: !d.debug }); toast(d.debug ? 'Режим отладки выключен, сохранённые календари удалены' : 'Режим отладки включён'); drawSyncState(box); } catch (ex) { toast(ex.message, true); } } }, h('i'));
    box.append(h('div', { class: 'card card-pad', style: { display: 'flex', gap: '12px', alignItems: 'flex-start' } }, sw,
      h('div', {}, h('b', {}, 'Режим отладки площадок'),
        h('div', { class: 'muted small' }, `Хранит последние ${d.keep} сырых календарей (.ics) от каждой площадки и тех, что отдали мы, не дольше ${d.keep_days} дней — чтобы разбирать, как именно площадка отдаёт и забирает брони. В календарях могут быть имена гостей, поэтому они видны только владельцу; при выключении всё сохранённое удаляется.`))));
  }
}
