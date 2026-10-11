// Флигель — интерфейс администратора (раздел «профиль»). ES-модуль без сборки.
import { ROLE, api, applyTheme, can, fmtDate, h, pad, state, store, toast } from './core.js';

export async function viewProfile(main) {
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Профиль')));
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const ok = h('div', { class: 'note ok', style: { display: 'none' } });
  const current = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', required: true });
  const next = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', required: true });
  const emailBox = h('input', { type: 'checkbox', checked: state.me.notify_email !== false, onchange: async () => {
    try { await api('PATCH', '/api/me/preferences', { notify_email: emailBox.checked }); state.me.notify_email = emailBox.checked; toast('Сохранено'); }
    catch (ex) { emailBox.checked = !emailBox.checked; toast(ex.message, true); }
  } });
  const submit = h('button', { class: 'btn primary', type: 'submit' }, 'Сменить пароль');
  const form = h('form', { onsubmit: async (e) => {
    e.preventDefault(); submit.disabled = true; err.style.display = 'none'; ok.style.display = 'none';
    try {
      const r = await api('POST', '/api/auth/change-password', { current_password: current.value, new_password: next.value });
      if (r.token) store.set('token', r.token);
      ok.textContent = r.message; ok.style.display = 'block'; current.value = ''; next.value = '';
    } catch (ex) { err.textContent = ex.message; err.style.display = 'block'; } finally { submit.disabled = false; }
  } },
  h('label', { class: 'field' }, h('span', {}, 'Текущий пароль'), current),
  h('label', { class: 'field' }, h('span', {}, 'Новый пароль (не короче 8 символов)'), next),
  submit);
  main.append(
    h('div', { class: 'card card-pad', style: { marginBottom: '16px' } },
      h('h2', { style: { marginBottom: '6px' } }, state.me.name),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, state.me.email, ' · ', ROLE[state.me.role], ' · ', state.me.account_name),
      can('owner') ? h('p', { class: 'small', style: { marginBottom: 0 } }, 'Тариф: ',
        h('b', {}, state.me.plan_label || state.me.plan),
        state.me.trial_ends ? ` · пробный период до ${fmtDate(state.me.trial_ends)}` : (state.me.paid_until ? ` · оплачен до ${fmtDate(state.me.paid_until)}` : ''),
        ` · объектов ${state.me.properties.length} из ${state.me.properties_limit}`) : null),
    h('div', { class: 'card card-pad', style: { marginBottom: '16px' } }, h('h2', { style: { marginBottom: '8px' } }, 'Оформление'),
      h('div', { class: 'seg' }, [['auto', 'Как в системе'], ['light', 'Светлая'], ['dark', 'Тёмная']].map(([k, l]) => h('button', { type: 'button', class: (store.get('theme', 'auto') === k) ? 'on' : '', onclick: (e) => {
        store.set('theme', k); applyTheme(); e.currentTarget.parentNode.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === e.currentTarget));
      } }, l)))),
    can('manager') ? h('div', { class: 'card card-pad', style: { marginBottom: '16px' } },
      h('h2', { style: { marginBottom: '8px' } }, 'Письма о новых заявках'),
      h('label', { class: 'check' }, emailBox, ' Присылать на почту письмо, когда гость оставил заявку на сайте'),
      h('p', { class: 'muted small', style: { marginBottom: 0 } }, 'Работает, когда на сервере настроена почта (SMTP). Уведомления в Telegram настраиваются в разделе «Уведомления».')) : null,
    h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '14px' } }, 'Сменить пароль'), err, ok, form));
}

