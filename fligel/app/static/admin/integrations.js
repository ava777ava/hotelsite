// Флигель — интерфейс администратора (раздел «Интеграции»: ключи API и вебхуки). ES-модуль без сборки.
import { api, closeModal, copyText, fmtDateTime, h, icon, openModal, toast } from './core.js';

const EVENT_LABEL = { 'booking.created': 'новая бронь', 'booking.updated': 'бронь изменена', 'booking.cancelled': 'бронь отменена' };
const SCOPE = { read: 'только чтение', write: 'чтение и запись' };

export async function viewIntegrations(main) {
  const box = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Интеграции'), h('a', { class: 'btn', href: '/api/docs', target: '_blank', rel: 'noopener' }, 'Документация API')), box);
  const bad = (ex) => toast(ex.message, true);

  function keyDialog() {
    const name = h('input', { class: 'input', maxlength: 80, placeholder: 'Например: мой сайт, бот, таблица' });
    const scope = h('select', { class: 'input' }, Object.entries(SCOPE).map(([k, l]) => h('option', { value: k }, l)));
    const err = h('div', { class: 'note bad', style: { display: 'none' } });
    openModal('Новый ключ API', h('div', {}, err, h('label', { class: 'field' }, h('span', {}, 'Название'), name), h('label', { class: 'field' }, h('span', {}, 'Права'), scope),
      h('div', { class: 'muted small' }, 'Ключ будет показан один раз — сохраните его. Ключ с правом записи может создавать и менять брони и цены.')),
    [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
      try {
        const k = await api('POST', '/api/keys', { name: name.value, scope: scope.value });
        closeModal(true);
        openModal('Ключ создан', h('div', {}, h('p', {}, 'Скопируйте ключ сейчас — потом он не будет показан:'),
          h('code', { style: { display: 'block', padding: '10px', wordBreak: 'break-all', userSelect: 'all', background: 'var(--surface-2)', borderRadius: '8px' } }, k.key)),
        [h('button', { class: 'btn', onclick: () => copyText(k.key, 'Ключ скопирован') }, icon('copy'), 'Скопировать'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: () => { closeModal(); load(); } }, 'Готово')]);
      } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
    } }, 'Создать')]);
  }

  function hookDialog(events) {
    const url = h('input', { class: 'input', type: 'url', placeholder: 'https://example.com/fligel-webhook' });
    const picked = new Set(events);
    const chips = h('div', { class: 'chips' }, events.map((e) => { const b = h('button', { type: 'button', class: 'chip on', onclick: () => { if (picked.has(e)) picked.delete(e); else picked.add(e); b.classList.toggle('on'); } }, EVENT_LABEL[e] || e); return b; }));
    const err = h('div', { class: 'note bad', style: { display: 'none' } });
    openModal('Новый вебхук', h('div', {}, err, h('label', { class: 'field' }, h('span', {}, 'Адрес вашего сервера (https)'), url), h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'События'), chips),
      h('div', { class: 'muted small' }, 'На адрес придёт POST с JSON и подписью. Подробности и пример проверки подписи — в документации API.')),
    [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
      try { await api('POST', '/api/webhooks', { url: url.value, events: [...picked] }); closeModal(); toast('Вебхук добавлен'); load(); } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
    } }, 'Добавить')]);
  }

  async function deliveries(w) {
    const r = await api('GET', `/api/webhooks/${w.id}/deliveries`).catch((ex) => { bad(ex); return null; });
    if (!r) return;
    openModal('Последние доставки', h('div', {}, r.items.length ? r.items.map((x) => h('div', { class: 'move-row small', style: { gridTemplateColumns: '110px 1fr 90px' } }, h('span', { class: 'muted' }, fmtDateTime(x.created_at)), h('span', {}, x.event, x.last_error ? h('div', { class: 'muted' }, x.last_error) : null),
      h('span', { class: `pill ${x.status === 'sent' ? 'ok' : (x.status === 'failed' ? 'bad' : 'warn')}` }, { sent: 'доставлено', failed: 'не доставлено', pending: 'в очереди' }[x.status]))) : h('div', { class: 'muted' }, 'Доставок пока не было.')),
    [h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: () => closeModal() }, 'Закрыть')]);
  }

  async function load() {
    const d = await api('GET', '/api/integrations');
    box.innerHTML = '';
    box.append(
      h('p', { class: 'muted' }, 'Подключайте свой сайт, таблицу или другую программу: ключ API даёт доступ к броням, номерам и ценам, вебхуки сообщают о новых и изменённых бронях сразу.'),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Ключи API'), h('button', { class: 'btn small', onclick: keyDialog }, icon('plus'), 'Ключ')),
        d.keys.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, d.keys.map((k) => h('tr', { style: k.revoked_at ? { opacity: .5 } : {} },
          h('td', {}, h('b', {}, k.name), h('div', { class: 'muted small' }, `${k.prefix}… · ${SCOPE[k.scope]}`)),
          h('td', { class: 'small muted' }, k.revoked_at ? 'отозван' : (k.last_used_at ? `использован ${fmtDateTime(k.last_used_at)}` : 'ещё не использовался')),
          h('td', { style: { textAlign: 'right' } }, k.revoked_at ? null : h('button', { class: 'btn small ghost', onclick: async () => { if (!confirm(`Отозвать ключ «${k.name}»? Программы, которые его используют, перестанут работать.`)) return; try { await api('DELETE', `/api/keys/${k.id}`); load(); } catch (ex) { bad(ex); } } }, 'Отозвать')))))))
          : h('div', { class: 'card-pad muted' }, 'Ключей нет.')),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Вебхуки'), h('button', { class: 'btn small', onclick: () => hookDialog(d.events.filter((e) => EVENT_LABEL[e])) }, icon('plus'), 'Вебхук')),
        d.webhooks.length ? h('div', { class: 'card-pad' }, d.webhooks.map((w) => {
          const secret = h('code', { class: 'small', style: { display: 'none', userSelect: 'all' } }, w.secret);
          return h('div', { class: `rule-card${w.enabled ? '' : ' off'}` },
            h('button', { type: 'button', class: `switch${w.enabled ? ' on' : ''}`, role: 'switch', 'aria-checked': String(w.enabled), 'aria-label': 'Вебхук включён', onclick: async () => { try { await api('PATCH', `/api/webhooks/${w.id}`, { enabled: !w.enabled }); load(); } catch (ex) { bad(ex); } } }, h('i')),
            h('div', { class: 'rule-body' }, h('b', { style: { wordBreak: 'break-all' } }, w.url), h('div', { class: 'muted small' }, w.events.map((e) => EVENT_LABEL[e] || e).join(', ')),
              h('div', { class: 'muted small' }, w.last_status ? `Последняя отправка: ${w.last_status}` : 'Ещё не отправлялся'),
              h('div', { class: 'small' }, h('button', { class: 'link', onclick: () => { secret.style.display = secret.style.display === 'none' ? '' : 'none'; } }, 'секрет для проверки подписи'), ' ', secret)),
            h('div', { style: { display: 'flex', gap: '6px', flexWrap: 'wrap' } },
              h('button', { class: 'btn small', onclick: async () => { try { const r = await api('POST', `/api/webhooks/${w.id}/test`, {}); toast(r.note); } catch (ex) { bad(ex); } } }, 'Проверить'),
              h('button', { class: 'btn small ghost', onclick: () => deliveries(w) }, 'Доставки'),
              h('button', { class: 'btn small ghost', 'aria-label': 'Удалить вебхук', onclick: async () => { if (!confirm('Удалить вебхук?')) return; try { await api('DELETE', `/api/webhooks/${w.id}`); load(); } catch (ex) { bad(ex); } } }, icon('trash'))));
        })) : h('div', { class: 'card-pad muted' }, 'Вебхуков нет.')));
  }
  load().catch((ex) => box.append(h('div', { class: 'card empty' }, ex.message)));
}
