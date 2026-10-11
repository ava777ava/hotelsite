// Флигель — интерфейс администратора (раздел «уведомления»). ES-модуль без сборки.
import { ago, api, closeDrawer, copyText, fmtDateTime, h, icon, openDrawer, pad, state, toast } from './core.js';

// ---------- уведомления в Telegram ----------
export const CHANNEL_HELP_TEXT = {
  telegram: {
    off: ['Не настроены на сервере: администратору сервиса нужно создать бота через @BotFather и указать токен ', h => h('code', {}, 'TELEGRAM_BOT_TOKEN'), ' в файле .env (см. deploy/DEPLOY.md).'],
    how: 'Откройте бота в Telegram и отправьте ему сообщение:',
  },
  max: {
    off: ['Не настроены на сервере. Боты MAX создаются только от верифицированного юридического лица или ИП в РФ (правило платформы MAX): зарегистрируйте бота на платформе MAX для бизнеса, получите токен и укажите его в файле .env как ', h => h('code', {}, 'MAX_BOT_TOKEN'), ' (см. deploy/DEPLOY.md). Пока токена нет, всё остальное в сервисе работает как обычно.'],
    how: 'Откройте бота в MAX по ссылке ниже (или отправьте боту сообщение):',
  },
};

// Каналы уведомлений (Telegram и MAX): каждый сотрудник подключает свои чаты и сам выбирает, куда и что получать
export async function viewNotifications(main) {
  const content = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Уведомления')), content);
  async function load() {
    const s = await api('GET', '/api/notify/status');
    content.innerHTML = '';
    const flags = {};
    const channelCard = (ch) => {
      const help = CHANNEL_HELP_TEXT[ch.name];
      const card = h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '6px' } }, `${ch.label}-уведомления`));
      if (!ch.server_enabled) {
        card.append(h('p', { class: 'muted small', style: { marginTop: 0 } }, ...help.off.map((x) => (typeof x === 'function' ? x(h) : x))));
        return card;
      }
      if (ch.linked) {
        flags[ch.name] = h('input', { type: 'checkbox', checked: ch.user_enabled });
        card.append(h('p', {}, h('span', { class: 'pill ok' }, 'Подключено'), ch.linked_at ? ` · с ${fmtDateTime(ch.linked_at)}` : ''),
          h('label', { class: 'check', style: { marginBottom: '10px' } }, flags[ch.name], `Присылать сюда уведомления`),
          h('button', { class: 'btn small ghost danger', onclick: async () => {
            if (!confirm(`Отключить ${ch.label}? Чат можно будет подключить заново.`)) return;
            await api('POST', `/api/notify/${ch.name}/unlink`); load();
          } }, 'Отвязать чат'));
      } else {
        const codeBox = h('div');
        const draw = () => {
          codeBox.innerHTML = '';
          if (ch.pending_code) {
            const text = ch.name === 'telegram' ? `/start ${ch.pending_code}` : (ch.deep_link || `/start ${ch.pending_code}`);
            codeBox.append(...[h('p', {}, help.how),
              h('div', { class: 'copy-line' }, h('input', { class: 'input', readonly: true, value: text }),
                h('button', { class: 'btn small', 'aria-label': 'Скопировать', onclick: () => copyText(text) }, icon('copy'))),
              ch.deep_link ? h('p', {}, h('a', { class: 'btn small', href: ch.deep_link, target: '_blank', rel: 'noopener' }, 'Открыть в MAX')) : null,
              h('p', { class: 'muted small' }, `Код действует 30 минут (до ${fmtDateTime(ch.pending_code_expires_at)}). После отправки обновите страницу.`)].filter(Boolean));
          }
        };
        draw();
        card.append(codeBox, h('button', { class: 'btn primary', style: { marginTop: '8px' }, onclick: async () => {
          const r = await api('POST', `/api/notify/${ch.name}/link`);
          Object.assign(ch, r.channels.find((x) => x.name === ch.name)); draw();
        } }, ch.pending_code ? 'Получить новый код' : `Подключить ${ch.label}`));
      }
      return card;
    };
    content.append(h('div', { class: 'card card-pad' }, h('p', { style: { margin: 0 } },
      'Новые заявки, отмены, конфликты, поломки и утренний дайджест можно получать в Telegram, в MAX или в оба мессенджера сразу. Внутри сервиса их всегда видно в колокольчике.')),
      ...s.channels.map(channelCard));
    if (s.channels.some((c) => c.server_enabled)) {
      const eventsCard = h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '10px' } }, 'Какие события присылать мне'));
      const boxes = {};
      s.available_events.forEach((e) => {
        eventsCard.append(h('label', { class: 'check', style: { display: 'block', marginBottom: '8px' } },
          boxes[e.key] = h('input', { type: 'checkbox', checked: s.events.includes(e.key) }), ' ' + e.label));
      });
      eventsCard.append(h('button', { class: 'btn primary', onclick: async () => {
        const events = Object.entries(boxes).filter(([, el]) => el.checked).map(([k]) => k);
        const channels = {};
        s.channels.forEach((c) => { channels[c.name] = flags[c.name] ? flags[c.name].checked : c.user_enabled; });
        try { await api('PUT', '/api/notify/settings', { events, channels }); toast('Сохранено'); } catch (ex) { toast(ex.message, true); }
      } }, 'Сохранить'));
      content.append(eventsCard);
    }
  }
  load().catch((ex) => content.append(h('div', { class: 'card empty' }, ex.message)));
}

// Колокольчик: последние события аккаунта (новые заявки, конфликты, поломки…)
export async function bellDrawer() {
  let r;
  try { r = await api('GET', '/api/notifications'); } catch (ex) { toast(ex.message, true); return; }
  openDrawer('Уведомления', r.items.length
    ? h('div', {}, r.items.map((n) => h('a', { class: 'bell-item' + (n.unread ? ' unread' : ''), href: n.link || '#/today', onclick: () => closeDrawer() },
      h('div', {}, n.text), h('div', { class: 'muted small' }, `${ago(n.created_at)}`))))
    : h('div', { class: 'empty' }, h('h3', {}, 'Пока тихо'), 'Здесь появятся новые заявки с сайта, конфликты площадок, поломки в номерах и другие события.'),
  [h('a', { class: 'btn small ghost', href: '#/notifications', onclick: () => closeDrawer() }, 'Настроить уведомления'), h('span', { class: 'spacer' }), h('button', { class: 'btn foot-close', onclick: closeDrawer }, 'Закрыть')]);
  if (r.unread) { try { await api('POST', '/api/notifications/seen'); state.bell = 0; document.querySelectorAll('[data-bell]').forEach((el) => { el.style.display = 'none'; }); } catch { /* ничего */ } }
}
