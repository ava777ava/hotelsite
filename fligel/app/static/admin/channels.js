// Флигель — интерфейс администратора (раздел «площадки»). ES-модуль без сборки.
import { ago, api, fmtShort, h, icon, pad, qs, state, store, toast } from './core.js';
import { drawSyncState } from './syncstate.js';

// ---------- площадки ----------
export const CHANNEL_HELP = {
  avito: [
    'На Авито откройте «Мои объявления», у нужного объявления нажмите «Управлять календарём» → «Синхронизация календарей».',
    'Скопируйте ссылку «Ваш календарь на Авито» и вставьте её сюда в поле «Ссылка с площадки».',
    'Нашу ссылку (кнопка «Копировать») вставьте на Авито в поле «Добавить календарь».',
  ],
  yandex: [
    'В Экстранете Яндекс Путешествий откройте категорию номеров → раздел «Синхронизация календарей». Для гостиницы календарь подключается к каждой категории.',
    'Ссылку календаря Яндекса вставьте сюда в строку этой категории, а нашу ссылку — в Экстранет.',
    'После подключения откройте доступность в Экстранете и проверьте, что Яндекс видит правильное число свободных номеров.',
  ],
  sutochno: [
    'На Суточно.ру: «Мои объекты» → шестерёнка у объекта → «Синхронизация календаря».',
    'Ссылку для экспорта с Суточно вставьте сюда, нашу ссылку — в поле импорта на Суточно.',
  ],
  ostrovok: [
    'В личном кабинете партнёра Островка найдите синхронизацию календаря по iCal.',
    'Обменяйтесь ссылками так же, как с другими площадками.',
  ],
  other: ['Подойдёт любая площадка, которая умеет импорт и экспорт календаря в формате iCal (.ics).'],
};

export async function viewChannels(main) {
  let channel = store.get('channel', 'avito');
  let tab = store.get('ch_tab', 'connect');
  const levelOverride = {};
  const content = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Площадки'),
    h('button', { class: 'btn', onclick: async (e) => {
      const btn = e.currentTarget; btn.disabled = true;
      try { const r = await api('POST', '/api/feeds/sync-all'); toast(r.feeds ? `Обновлено календарей: ${r.feeds}. Новых броней: ${r.added}${r.errors ? `, ошибок: ${r.errors}` : ''}` : 'Нет подключённых календарей', r.errors > 0); load(); }
      catch (ex) { toast(ex.message, true); } finally { btn.disabled = false; }
    } }, icon('sync'), 'Обновить всё')),
    h('div', { class: 'seg', style: { marginBottom: '12px' } }, [['connect', 'Подключение'], ['state', 'Состояние синхронизации']].map(([k, l]) => h('button', { class: k === tab ? 'on' : '', onclick: () => { tab = k; store.set('ch_tab', k); main.innerHTML = ''; viewChannels(main); } }, l))), content);

  const copy = async (text) => { try { await navigator.clipboard.writeText(text); toast('Ссылка скопирована'); } catch { prompt('Скопируйте ссылку:', text); } };

  function row(item, level, labels) {
    const ch = item.channels[channel];
    const feed = ch.feed;
    const input = h('input', { class: 'input', placeholder: 'https://… ссылка календаря с площадки', value: feed?.url || '' });
    const saveBtn = h('button', { class: 'btn small primary', onclick: async () => {
      saveBtn.disabled = true;
      try {
        const body = { channel, url: input.value, [level === 'type' ? 'room_type_id' : 'room_id']: item.id };
        const res = await api('POST', '/api/feeds', body);
        if (res.status === 'ok') toast(`Календарь подключён. Броней загружено: ${res.added}${res.conflicts ? `, конфликтов: ${res.conflicts}` : ''}`, res.conflicts > 0);
        else toast(`Ссылка сохранена, но календарь не загрузился: ${res.message}`, true);
        load();
      } catch (ex) { toast(ex.message, true); input.classList.add('invalid'); } finally { saveBtn.disabled = false; }
    } }, feed ? 'Заменить' : 'Подключить');
    let status;
    if (!feed) status = h('span', { class: 'pill none' }, 'не подключено');
    else if (feed.last_status === 'error') status = h('span', { class: 'pill bad', title: feed.last_error }, 'ошибка');
    else if (feed.last_error) status = h('span', { class: 'pill warn', title: feed.last_error }, 'есть конфликты');
    else status = h('span', { class: 'pill ok' }, 'работает');
    const modeSel = level === 'type' ? h('select', { class: 'input', style: { height: '32px', fontSize: '12.5px', marginTop: '6px' },
      title: 'Как площадка узнаёт о занятости категории',
      onchange: async (e) => { await api('PUT', '/api/channels/export-mode', { room_type_id: item.id, channel, mode: e.target.value }); toast('Сохранено'); } },
      h('option', { value: 'per_booking', selected: ch.export_mode === 'per_booking' }, 'Каждая бронь — отдельным событием'),
      h('option', { value: 'sold_out', selected: ch.export_mode === 'sold_out' }, 'Только даты, когда мест нет')) : null;
    return h('tr', {},
      h('td', { class: 'wide' }, level === 'type'
        ? [h('b', {}, item.name), h('div', { class: 'muted small' }, `${item.rooms_count} ${item.rooms_count === 1 ? 'номер' : 'номеров'}`)]
        : [h('b', { class: 'num' }, item.name), h('div', { class: 'muted small' }, item.room_type)]),
      h('td', { class: 'ch-cell wide', 'data-l': 'Наш календарь — вставьте на площадке' },
        h('div', { class: 'copy-line' }, h('input', { class: 'input', readonly: true, value: ch.export_url, onclick: (e) => e.target.select() }),
          h('button', { class: 'btn small icon', title: 'Копировать', onclick: () => copy(ch.export_url) }, icon('copy'))),
        h('div', { class: 'muted small', style: { marginTop: '4px' } }, 'площадка забирала: ', ago(ch.export_last_fetched_at)),
        modeSel),
      h('td', { class: 'ch-cell wide', 'data-l': 'Календарь площадки — вставьте сюда' }, h('div', { class: 'copy-line' }, input, saveBtn),
        feed?.last_status === 'error' ? h('div', { class: 'small', style: { color: 'var(--clay)', marginTop: '4px' } }, feed.last_error) : null),
      h('td', { class: 'wide', 'data-l': 'Состояние' }, h('div', { class: 'state' }, status),
        feed ? h('div', { class: 'muted small' }, 'обновлено: ', ago(feed.last_synced_at)) : null,
        feed ? h('div', { class: 'ch-actions', style: { marginTop: '6px' } },
          h('button', { class: 'btn small', onclick: async (e) => {
            e.currentTarget.disabled = true;
            try { const res = await api('POST', `/api/feeds/${feed.id}/sync`); toast(res.status === 'ok' ? `Готово: новых ${res.added}, изменено ${res.updated}, отменено ${res.removed}` : res.message, res.status !== 'ok'); load(); }
            catch (ex) { toast(ex.message, true); }
          } }, icon('sync'), 'Обновить'),
          h('button', { class: 'btn small ghost danger', onclick: async () => {
            if (!confirm(`Отключить календарь площадки «${labels[channel]}»? Брони, уже загруженные с неё, останутся в шахматке.`)) return;
            await api('DELETE', `/api/feeds/${feed.id}`); toast('Календарь отключён'); load();
          } }, 'Отключить')) : null));
  }

  async function load() {
    const [data, conflicts] = await Promise.all([
      api('GET', '/api/channels?' + qs({ property_id: state.propertyId })), api('GET', '/api/conflicts')]);
    state.conflicts = conflicts.length; state.channelIssues = conflicts.length + (state.exportStale || 0);
    const level = levelOverride[channel] || data.levels[channel];
    content.innerHTML = '';
    if (state.exportStale) {
      content.append(h('div', { class: 'note', role: 'alert', style: { background: 'var(--ochre-soft)', color: 'var(--ochre-ink)' } },
        `⚠ Площадка не забирала наш календарь больше 6 часов (календарей: ${state.exportStale}). `,
        h('a', { href: '#/channels', onclick: (e) => { e.preventDefault(); store.set('ch_tab', 'state'); main.innerHTML = ''; viewChannels(main); } }, 'Открыть «Состояние синхронизации»')));
    }
    if (conflicts.length) {
      content.append(h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', {}, 'Конфликты: двойное бронирование'), h('span', { class: 'pill bad' }, conflicts.length)),
        h('div', { class: 'card-pad', style: { paddingTop: '10px' } },
          h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Площадка продала даты, на которые у вас нет свободного номера. Свяжитесь с гостем площадки или переселите одну из броней, затем отметьте конфликт решённым.'),
          h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, conflicts.map((c) => h('tr', {},
            h('td', {}, h('b', {}, c.target_name)), h('td', { class: 'num' }, `${fmtShort(c.check_in)} — ${fmtShort(c.check_out)}`),
            h('td', {}, data.labels[c.channel] || '—'), h('td', { class: 'muted small' }, c.summary),
            h('td', { style: { textAlign: 'right' } }, h('button', { class: 'btn small', onclick: async () => { await api('POST', `/api/conflicts/${c.id}/resolve`); load(); } }, 'Решено'))))))))));
    }
    const tabs = h('div', { class: 'seg', style: { flexWrap: 'wrap' } }, Object.entries(data.labels).map(([k, l]) => {
      const connected = data.rooms.filter((r) => r.channels[k].feed).length + data.room_types.filter((t) => t.channels[k].feed).length;
      return h('button', { class: k === channel ? 'on' : '', onclick: () => { channel = k; store.set('channel', k); load(); } }, l, connected ? ` · ${connected}` : '');
    }));
    const anyFeeds = data.rooms.some((r) => r.channels[channel].feed) || data.room_types.some((t) => t.channels[channel].feed);
    const levelSeg = h('div', { class: 'seg' },
      [['room', 'По номерам'], ['type', 'По категориям']].map(([k, l]) => h('button', {
        class: level === k ? 'on' : '', disabled: anyFeeds && level !== k,
        title: anyFeeds && level !== k ? 'Сначала отключите текущие календари этой площадки' : '',
        onclick: () => { levelOverride[channel] = k; load(); },
      }, l)));
    const items = level === 'type' ? data.room_types : data.rooms;
    content.append(
      h('div', { class: 'board-tools' }, tabs),
      h('div', { class: 'card card-pad' },
        h('div', { style: { display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '10px' } },
          h('h3', { style: { marginRight: 'auto' } }, `Как подключить: ${data.labels[channel]}`), h('span', { class: 'muted small' }, 'На площадке у вас:'), levelSeg),
        h('ol', { class: 'steps small' }, CHANNEL_HELP[channel].map((st) => h('li', {}, st))),
        h('p', { class: 'muted small', style: { marginBottom: 0 } },
          level === 'type'
            ? 'Календарь категории: брони площадки мы сами расставляем по свободным номерам этой категории. Если площадка закрывает всю категорию при первой же брони, переключите способ передачи на «Только даты, когда мест нет».'
            : 'Календарь номера: одно объявление на площадке = один номер у нас.',
          ` Календари площадок обновляются каждые ${data.sync_interval_minutes} минут. Сама площадка забирает наш календарь по своему расписанию. Через iCal передаётся только занятость; цены меняются в кабинете площадки.`)),
      h('div', { class: 'card' }, h('div', { class: 'table-wrap' }, h('table', { class: 'list ch-table cards-mobile' },
        h('thead', {}, h('tr', {}, [level === 'type' ? 'Категория' : 'Номер', 'Ссылка для площадки (наш календарь)', 'Ссылка с площадки (их календарь)', 'Состояние'].map((t) => h('th', {}, t)))),
        h('tbody', {}, items.map((it) => row(it, level, data.labels)))))));
  }
  (tab === 'state' ? drawSyncState(content) : load()).catch((ex) => content.append(h('div', { class: 'card empty' }, ex.message)));
}
