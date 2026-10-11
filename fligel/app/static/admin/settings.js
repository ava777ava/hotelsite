// Флигель — интерфейс администратора (раздел «настройки»). ES-модуль без сборки.
import { render, switchProperty } from './app.js';
import { ROLE, SOURCE, api, closeDrawer, closeModal, downloadCsv, fmtMoney, h, icon, nightsWord, openDrawer, openModal, pad, state, store, toast } from './core.js';
import { templatesCard } from './guests.js';
import { count } from './ui.js';

// ---------- добавление объекта ----------
export function addPropertyDrawer() {
  const types = [{ name: 'Стандарт', count: 4, capacity: 2, base_price: 3000 }];
  const g = {};
  const list = h('div');
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const drawTypes = () => {
    list.innerHTML = '';
    types.forEach((t, i) => {
      const inp = (key, label, type = 'text') => h('label', { class: 'field' }, h('span', {}, label),
        h('input', { class: 'input', type, value: t[key], min: type === 'number' ? 0 : null, oninput: (e) => { t[key] = e.target.value; } }));
      list.append(h('div', { class: 'type-row' }, inp('name', 'Категория'), inp('count', 'Номеров', 'number'),
        inp('capacity', 'Гостей', 'number'), inp('base_price', 'Цена за ночь', 'number'),
        h('button', { class: 'btn icon ghost del', type: 'button', title: 'Убрать категорию', 'aria-label': 'Убрать категорию', disabled: types.length === 1,
          onclick: () => { types.splice(i, 1); drawTypes(); } }, icon('close'))));
    });
  };
  drawTypes();
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; err.style.display = 'none';
    try {
      const prop = await api('POST', '/api/setup', {
        name: g.name.value, address: g.address.value, phone: g.phone.value, first_number: g.first.value, room_types: types,
      });
      state.me = await api('GET', '/api/me');
      closeDrawer();
      switchProperty(prop.id);
      toast('Объект добавлен');
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; } finally { save.disabled = false; }
  } }, 'Создать объект');
  openDrawer('Новый объект', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Название'), g.name = h('input', { class: 'input', required: true })),
    h('div', { class: 'row2' },
      h('label', { class: 'field' }, h('span', {}, 'Адрес'), g.address = h('input', { class: 'input' })),
      h('label', { class: 'field' }, h('span', {}, 'Телефон для гостей'), g.phone = h('input', { class: 'input', type: 'tel' }))),
    h('h3', { style: { margin: '4px 0 10px' } }, 'Номера'),
    list,
    h('div', { style: { display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', margin: '4px 0' } },
      h('button', { class: 'btn small', type: 'button', onclick: () => { types.push({ name: '', count: 1, capacity: 2, base_price: 3000 }); drawTypes(); } }, icon('plus'), 'Категория'),
      h('label', { class: 'check small' }, 'Первый номер', g.first = h('input', { class: 'input', type: 'number', value: 101, style: { width: '90px', height: '32px' } })))),
  [h('span', { class: 'spacer' }), save]);
}

// ---------- фото категории номеров ----------
// Фото сжимаются прямо в браузере (до 1600 px, JPEG) — на сервер уходит ~200–400 КБ вместо 5–10 МБ с телефона.
export async function compressImage(file, maxSide = 1600, quality = 0.82) {
  const bmp = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bmp.width * scale); canvas.height = Math.round(bmp.height * scale);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); // прозрачные PNG не должны стать чёрными
  ctx.drawImage(bmp, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', quality));
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.onerror = rej; r.readAsDataURL(blob); });
}

export function photoManager(typeId, onChange) {
  const box = h('div', { class: 'photo-box' });
  const status = h('div', { class: 'muted small' });
  const fileInp = h('input', { type: 'file', accept: 'image/jpeg,image/png,image/webp', multiple: true, style: { display: 'none' }, onchange: async () => {
    const files = [...fileInp.files]; fileInp.value = '';
    for (let i = 0; i < files.length; i++) {
      status.textContent = `Загружаю ${i + 1} из ${files.length}…`;
      try { await api('POST', `/api/room-types/${typeId}/photos`, { data: await compressImage(files[i]) }); }
      catch (ex) { toast(`${files[i].name}: ${ex.message}`, true); }
    }
    status.textContent = ''; draw(); onChange?.();
  } });
  async function draw() {
    let photos = [];
    try { photos = await api('GET', `/api/room-types/${typeId}/photos`); } catch (ex) { box.textContent = ex.message; return; }
    box.innerHTML = '';
    const grid = h('div', { class: 'photo-grid' });
    photos.forEach((p, i) => {
      const img = h('img', { alt: 'Фото номера', loading: 'lazy' });
      fetch(`/api/photos/${p.id}/file`, { headers: { Authorization: `Bearer ${store.get('token')}` } })
        .then((r) => r.blob()).then((b) => { img.src = URL.createObjectURL(b); }).catch(() => {});
      grid.append(h('div', { class: 'photo-item' + (i === 0 ? ' main' : '') }, img,
        i === 0 ? h('span', { class: 'photo-tag' }, 'Главное') : h('button', { class: 'photo-act first', title: 'Сделать главным', type: 'button', onclick: async () => {
          const ids = [p.id, ...photos.filter((x) => x.id !== p.id).map((x) => x.id)];
          await api('PUT', `/api/room-types/${typeId}/photos/order`, { ids }); draw(); onChange?.();
        } }, '★'),
        h('button', { class: 'photo-act del', title: 'Удалить фото', type: 'button', onclick: async () => {
          if (!confirm('Удалить это фото?')) return;
          await api('DELETE', `/api/photos/${p.id}`); draw(); onChange?.();
        } }, '✕')));
    });
    box.append(grid, h('div', { style: { display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' } },
      photos.length < 8 ? h('button', { class: 'btn small', type: 'button', onclick: () => fileInp.click() }, icon('plus'), 'Добавить фото') : h('span', { class: 'muted small' }, 'Максимум 8 фото'),
      status, fileInp));
  }
  draw();
  return h('div', { class: 'field' }, h('span', {}, 'Фото для страницы бронирования'), box,
    h('span', { class: 'muted small', style: { fontWeight: 400 } }, 'Гости увидят их в карточке номера. Первое фото — главное.'));
}

// Справочник дополнительных услуг (завтрак, трансфер…): добавляются в бронь одним выбором
export function servicesCard() {
  const card = h('div', { class: 'card card-pad' });
  async function draw() {
    const list = await api('GET', '/api/services');
    card.innerHTML = '';
    const name = h('input', { class: 'input', placeholder: 'Например: Завтрак' });
    const price = h('input', { class: 'input', money: true, type: 'number', min: 0, placeholder: 'Цена, ₽', style: { maxWidth: '140px' } });
    card.append(h('h2', { style: { marginBottom: '6px' } }, 'Дополнительные услуги'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Завтрак, трансфер, поздний выезд, доп. место — добавляются в бронь одним выбором и входят в счёт.'),
      list.length ? h('div', { class: 'pay-list' }, list.map((x) => h('div', { class: 'pay-row' },
        h('span', { class: 'pay-sum', style: { flex: 1 } }, x.name + (x.active ? '' : ' (скрыта)')),
        h('span', { class: 'muted small' }, fmtMoney(x.price)),
        h('button', { class: 'btn small ghost', type: 'button', onclick: async () => { await api('PATCH', `/api/services/${x.id}`, { active: !x.active }); draw(); } }, x.active ? 'Скрыть' : 'Показать'),
        h('button', { class: 'btn icon ghost small', type: 'button', 'aria-label': 'Удалить услугу', onclick: async () => {
          if (confirm(`Удалить услугу «${x.name}»? В уже созданных бронях она останется.`)) { await api('DELETE', `/api/services/${x.id}`); draw(); }
        } }, icon('trash')))))
        : h('div', { class: 'muted small', style: { marginBottom: '10px' } }, 'Пока пусто. Добавьте первую услугу.'),
      h('div', { class: 'money-actions' }, name, price, h('button', { class: 'btn small primary', type: 'button', onclick: async () => {
        if (!name.value.trim()) { toast('Введите название услуги', true); return; }
        try { await api('POST', '/api/services', { name: name.value, price: price.value || 0 }); draw(); } catch (ex) { toast(ex.message, true); }
      } }, icon('plus'), 'Добавить')));
  }
  draw().catch((ex) => { card.textContent = ex.message; });
  return card;
}

// Тарифы категории: невозвратный, с завтраком… (± % и ± ₽ к цене ночи)
export function plansManager(typeId) {
  const box = h('div', { class: 'field' });
  async function draw() {
    const plans = await api('GET', `/api/room-types/${typeId}/plans`);
    box.innerHTML = '';
    box.append(h('span', {}, 'Тарифы'),
      plans.length ? h('div', { class: 'pay-list' }, plans.map((p) => h('div', { class: 'pay-row' },
        h('span', { class: 'pay-sum', style: { flex: 1, minWidth: 0 } }, p.name + (p.active ? '' : ' (скрыт)')),
        h('span', { class: 'muted small' }, [Number(p.percent_delta) ? `${Number(p.percent_delta) > 0 ? '+' : ''}${Number(p.percent_delta)}%` : '', Number(p.fixed_delta) ? `${Number(p.fixed_delta) > 0 ? '+' : ''}${Math.round(p.fixed_delta)} ₽/ночь` : '', p.refundable ? '' : 'невозвратный', p.breakfast ? 'завтрак' : ''].filter(Boolean).join(' · ') || 'как базовая'),
        h('button', { class: 'btn small ghost', type: 'button', onclick: () => planDialog(typeId, p, draw) }, 'Изменить'))))
        : h('div', { class: 'muted small', style: { marginBottom: '8px' } }, 'Тарифов нет — гости видят одну цену. Добавьте, например, «Невозвратный −10%» или «С завтраком +500 ₽».'),
      h('div', {}, h('button', { class: 'btn small', type: 'button', onclick: () => planDialog(typeId, null, draw) }, icon('plus'), 'Тариф')));
  }
  draw().catch((ex) => { box.textContent = ex.message; });
  return box;
}

export function planDialog(typeId, plan, onDone) {
  const p = plan || { name: '', description: '', percent_delta: 0, fixed_delta: 0, refundable: true, breakfast: false, active: true };
  const f = {
    name: h('input', { class: 'input', value: p.name, placeholder: 'Например: Невозвратный' }),
    description: h('input', { class: 'input', value: p.description, placeholder: 'Что видит гость (необязательно)' }),
    percent: h('input', { class: 'input', type: 'number', step: '1', value: Number(p.percent_delta) || '', placeholder: '0' }),
    fixed: h('input', { class: 'input', type: 'number', step: '50', value: Number(p.fixed_delta) || '', placeholder: '0' }),
    refundable: h('input', { type: 'checkbox', checked: p.refundable }), breakfast: h('input', { type: 'checkbox', checked: p.breakfast }),
    active: h('input', { type: 'checkbox', checked: p.active }),
  };
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const save = h('button', { class: 'btn primary', onclick: async () => {
    const payload = { name: f.name.value, description: f.description.value, percent_delta: f.percent.value || 0, fixed_delta: f.fixed.value || 0,
      refundable: f.refundable.checked, breakfast: f.breakfast.checked, active: f.active.checked };
    try {
      if (plan) await api('PATCH', `/api/plans/${plan.id}`, payload); else await api('POST', `/api/room-types/${typeId}/plans`, payload);
      closeModal(); toast('Тариф сохранён'); onDone?.();
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; }
  } }, 'Сохранить');
  openModal(plan ? 'Тариф' : 'Новый тариф', h('div', {}, err,
    h('label', { class: 'field' }, h('span', {}, 'Название'), f.name), h('label', { class: 'field' }, h('span', {}, 'Описание'), f.description),
    h('div', { class: 'row2' }, h('label', { class: 'field' }, h('span', {}, 'Изменение цены, %'), f.percent), h('label', { class: 'field' }, h('span', {}, 'Изменение, ₽ за ночь'), f.fixed)),
    h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Отрицательное число — скидка: −10 даёт цену на 10% ниже. Применяется к цене каждой ночи.'),
    h('label', { class: 'check' }, f.refundable, 'Бесплатная отмена'), h('label', { class: 'check' }, f.breakfast, 'Завтрак включён'),
    h('label', { class: 'check' }, f.active, 'Показывать гостям на сайте')),
  [plan ? h('button', { class: 'btn ghost danger', onclick: async () => { if (confirm('Удалить тариф? В созданных бронях он останется.')) { await api('DELETE', `/api/plans/${plan.id}`); closeModal(); onDone?.(); } } }, 'Удалить') : null,
    h('span', { class: 'spacer' }), h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), save]);
}

// ---------- настройки ----------
// Диалог номера: название, постоянный код двери (подставляется в сообщения гостю как {код двери}), удаление
function roomDialog(r, onDone) {
  const name = h('input', { class: 'input', value: r.name, maxlength: 50 });
  const code = h('input', { class: 'input', value: r.door_code || '', maxlength: 100, autocomplete: 'off', placeholder: 'Например, 4821#' });
  openModal(`Номер ${r.name}`, h('div', {},
    h('label', { class: 'field' }, h('span', {}, 'Название или номер'), name),
    h('label', { class: 'field' }, h('span', {}, 'Постоянный код двери или сейфа'), code),
    h('div', { class: 'muted small' }, 'Если у брони свой код, в сообщении будет он. Горничной код не показывается.')),
  [h('button', { class: 'btn danger', onclick: async () => {
    if (!confirm(`Удалить номер ${r.name}? Брони этого номера тоже удалятся.`)) return;
    try { await api('DELETE', `/api/rooms/${r.id}`); closeModal(); onDone(); } catch (ex) { toast(ex.message, true); }
  } }, 'Удалить'), h('span', { class: 'spacer' }), h('button', { class: 'btn', onclick: () => closeModal() }, 'Отмена'),
  h('button', { class: 'btn primary', onclick: async () => {
    if (!name.value.trim()) { toast('Укажите название номера', true); return; }
    try { await api('PATCH', `/api/rooms/${r.id}`, { name: name.value.trim(), door_code: code.value }); closeModal(); toast('Сохранено'); onDone(); }
    catch (ex) { toast(ex.message, true); }
  } }, 'Сохранить')]);
}

export async function viewSettings(main) {
  const content = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Настройки')), content);
  async function load() {
    const [prop, users] = await Promise.all([api('GET', `/api/properties/${state.propertyId}`), api('GET', '/api/users')]);
    content.innerHTML = '';
    const bookingUrl = `${location.origin}/book/${prop.public_slug}`;
    const f = {};
    const field = (key, label, attrs = {}) => h('label', { class: 'field' }, h('span', {}, label), f[key] = h('input', { class: 'input', value: prop[key] ?? '', ...attrs }));
    f.booking_enabled = h('input', { type: 'checkbox', checked: prop.booking_enabled });
    content.append(h('div', { class: 'card' },
      h('div', { class: 'card-head' }, h('h2', {}, 'Объекты'),
        h('button', { class: 'btn small', onclick: addPropertyDrawer }, icon('plus'), 'Добавить объект')),
      h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {},
        state.me.properties.map((p) => h('tr', { class: 'click', onclick: () => switchProperty(p.id) },
          h('td', {}, p.id === state.propertyId ? h('b', {}, p.name) : p.name),
          h('td', { style: { textAlign: 'right' } }, p.id === state.propertyId ? h('span', { class: 'pill ok' }, 'выбран') : null))))))));
    content.append(h('div', { class: 'grid-2' },
      h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '14px' } }, 'Объект'),
        field('name', 'Название'), field('address', 'Адрес'), field('phone', 'Телефон для гостей', { type: 'tel' }),
        h('div', { class: 'row2' }, field('check_in_time', 'Заезд с', { type: 'time', value: prop.check_in_time.slice(0, 5) }), field('check_out_time', 'Выезд до', { type: 'time', value: prop.check_out_time.slice(0, 5) })),
        h('button', { class: 'btn primary', onclick: async () => {
          try {
            await api('PATCH', `/api/properties/${prop.id}`, { name: f.name.value, address: f.address.value, phone: f.phone.value, check_in_time: f.check_in_time.value, check_out_time: f.check_out_time.value });
            state.me = await api('GET', '/api/me'); toast('Сохранено'); render();
          } catch (ex) { toast(ex.message, true); }
        } }, 'Сохранить')),
      h('div', { class: 'card card-pad' }, h('h2', { style: { marginBottom: '8px' } }, 'Бронирование на сайте'),
        h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Страница, где гость сам выбирает даты и отправляет заявку. Заявки появляются в шахматке со статусом «Заявка» (штриховка) — подтвердите или отклоните их в разделе «Брони». Неподтверждённая заявка сама снимается через 48 часов.'),
        h('label', { class: 'check', style: { marginBottom: '12px' } }, f.booking_enabled, 'Принимать заявки', h('span', { class: 'muted small' }, ''),),
        h('div', { class: 'field' }, h('span', {}, 'Ссылка для гостей и соцсетей'), h('div', { class: 'copy-line' }, h('input', { class: 'input', readonly: true, value: bookingUrl }),
          h('a', { class: 'btn small', href: bookingUrl, target: '_blank' }, 'Открыть'))),
        h('div', { class: 'field' }, h('span', {}, 'Код для вставки на ваш сайт'),
          h('textarea', { class: 'input', readonly: true, style: { fontSize: '12px', minHeight: '64px' } }, `<iframe src="${bookingUrl}?embed=1" style="width:100%;min-height:720px;border:0" loading="lazy"></iframe>`)),
        h('p', { class: 'muted small', style: { marginBottom: 0 } }, 'Онлайн-оплату (ЮKassa и т.п.) подключим следующим шагом вместе с чеками по 54-ФЗ.'))));
    f.booking_enabled.addEventListener('change', async () => {
      await api('PATCH', `/api/properties/${prop.id}`, { booking_enabled: f.booking_enabled.checked });
      toast(f.booking_enabled.checked ? 'Приём заявок включён' : 'Приём заявок выключен');
    });

    // категории и номера
    const typesCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Категории и номера'),
      h('button', { class: 'btn small', onclick: () => typeDrawer({ property_id: prop.id }) }, icon('plus'), 'Категория')));
    const typeDrawer = (t) => {
      const g = {};
      const fld = (k, l, a = {}) => h('label', { class: 'field' }, h('span', {}, l), g[k] = h('input', { class: 'input', value: t[k] ?? '', ...a }));
      openDrawer(t.id ? t.name : 'Новая категория', h('div', {},
        fld('name', 'Название'), fld('description', 'Описание для гостей'),
        h('div', { class: 'row3' }, fld('capacity', 'Гостей', { money: true, type: 'number', min: 1, value: t.capacity ?? 2 }), fld('base_price', 'Цена, ₽', { type: 'number', min: 0, value: t.base_price != null ? Math.round(t.base_price) : '' }), fld('min_stay', 'Мин. ночей', { type: 'number', min: 1, value: t.min_stay ?? 1 })),
        h('h3', { style: { margin: '14px 0 6px' } }, 'Доплаты и скидки'),
        h('div', { class: 'row2' }, fld('included_guests', 'Гостей в цене', { money: true, type: 'number', min: 0, value: t.included_guests || '', placeholder: 'все' }), fld('extra_guest_price', 'Доплата за гостя, ₽/ночь', { type: 'number', min: 0, value: t.extra_guest_price ? Math.round(t.extra_guest_price) : '', placeholder: '0' })),
        h('div', { class: 'row2' }, fld('week_discount_percent', 'Скидка от 7 ночей, %', { type: 'number', min: 0, max: 90, value: Number(t.week_discount_percent) || '', placeholder: '0' }), fld('month_discount_percent', 'Скидка от 28 ночей, %', { type: 'number', min: 0, max: 90, value: Number(t.month_discount_percent) || '', placeholder: '0' })),
        h('h3', { style: { margin: '14px 0 6px' } }, 'Границы для автоцен'),
        h('div', { class: 'row2' }, fld('min_price', 'Не ниже, ₽', { type: 'number', min: 0, value: t.min_price != null ? Math.round(t.min_price) : '', placeholder: 'без границы' }), fld('max_price', 'Не выше, ₽', { type: 'number', min: 0, value: t.max_price != null ? Math.round(t.max_price) : '', placeholder: 'без границы' })),
        h('div', { class: 'muted small' }, 'Автоцены (раздел «Автоцены») не выйдут за эти границы.'),
        t.id ? plansManager(t.id) : null,
        t.id ? photoManager(t.id) : h('p', { class: 'muted small' }, 'Фото и тарифы можно добавить после сохранения категории.')),
      [t.id ? h('button', { class: 'btn ghost danger', onclick: async () => { try { await api('DELETE', `/api/room-types/${t.id}`); closeDrawer(); load(); } catch (ex) { toast(ex.message, true); } } }, 'Удалить') : null,
        h('span', { class: 'spacer' }),
        h('button', { class: 'btn primary', onclick: async () => {
          const payload = Object.fromEntries(Object.entries(g).map(([k, el]) => [k, el.value]));
          try { if (t.id) await api('PATCH', `/api/room-types/${t.id}`, payload); else await api('POST', '/api/room-types', { ...payload, property_id: prop.id }); closeDrawer(); toast('Сохранено'); load(); }
          catch (ex) { toast(ex.message, true); }
        } }, 'Сохранить')]);
    };
    typesCard.append(h('table', { class: 'list' }, h('tbody', {}, prop.room_types.map((t) => h('tr', {},
      h('td', { style: { width: '32%' } }, h('b', {}, t.name), h('div', { class: 'muted small' }, `до ${t.capacity} гостей · ${fmtMoney(t.base_price)} · от ${t.min_stay} ${nightsWord(t.min_stay)}`)),
      h('td', {}, h('div', { style: { display: 'flex', gap: '6px', flexWrap: 'wrap' } },
        t.rooms.map((r) => h('button', { class: 'btn small', title: 'Название, код двери, удаление', onclick: () => roomDialog(r, load) }, r.name, r.door_code ? ' 🔑' : '')),
        h('button', { class: 'btn small ghost', onclick: async () => {
          const name = prompt('Название или номер комнаты'); if (!name) return;
          try { await api('POST', '/api/rooms', { room_type_id: t.id, name }); load(); } catch (ex) { toast(ex.message, true); }
        } }, icon('plus'), 'номер'))),
      h('td', { style: { textAlign: 'right' } }, h('button', { class: 'btn small ghost', onclick: () => typeDrawer(t) }, 'Изменить')))))));
    content.append(typesCard);

    // сотрудники
    const staffCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Сотрудники'),
      h('button', { class: 'btn small', onclick: () => {
        const g = {};
        const fld = (k, l, a = {}) => h('label', { class: 'field' }, h('span', {}, l), g[k] = h('input', { class: 'input', ...a }));
        g.role = h('select', { class: 'input', onchange: () => { propBox.style.display = g.role.value === 'landlord' ? '' : 'none'; } }, h('option', { value: 'manager' }, 'Администратор — брони, цены, площадки'), h('option', { value: 'housekeeper' }, 'Горничная — уборка, шахматка и заезды'), h('option', { value: 'landlord' }, 'Собственник — только чтение своих объектов и отчёт'));
        const propChecks = state.me.properties.map((pr) => [pr.id, h('input', { type: 'checkbox' }), pr.name]);
        const propBox = h('div', { class: 'field', style: { display: 'none' } }, h('span', {}, 'Какие объекты видит собственник'), propChecks.map(([, cb, name]) => h('label', { class: 'check' }, cb, name)));
        openDrawer('Новый сотрудник', h('div', {}, fld('name', 'Имя'), fld('email', 'Email для входа', { type: 'email' }), fld('password', 'Временный пароль', { type: 'text' }),
          h('label', { class: 'field' }, h('span', {}, 'Доступ'), g.role), propBox),
        [h('span', { class: 'spacer' }), h('button', { class: 'btn primary', onclick: async () => {
          try { await api('POST', '/api/users', { name: g.name.value, email: g.email.value, password: g.password.value, role: g.role.value, property_ids: propChecks.filter(([, cb]) => cb.checked).map(([id]) => id) }); closeDrawer(); toast('Сотрудник добавлен'); load(); }
          catch (ex) { toast(ex.message, true); }
        } }, 'Добавить')]);
      } }, icon('plus'), 'Сотрудник')),
    h('table', { class: 'list' }, h('tbody', {}, users.map((u) => h('tr', {},
      h('td', {}, h('b', {}, u.name), h('div', { class: 'muted small' }, u.email)), h('td', {}, ROLE[u.role], u.role === 'landlord' ? h('div', { class: 'muted small' }, state.me.properties.filter((pr) => (u.property_ids || []).includes(pr.id)).map((pr) => pr.name).join(', ') || 'объекты не выбраны') : null),
      h('td', { style: { textAlign: 'right' } }, u.role !== 'owner' ? h('button', { class: 'btn small ghost danger', onclick: async () => {
        if (!confirm(`Удалить доступ для ${u.name}?`)) return;
        await api('DELETE', `/api/users/${u.id}`); load();
      } }, 'Удалить') : null))))));
    content.append(staffCard);

    // комиссии площадок — используются в финансовых отчётах
    const CHANNEL_LIST = ['avito', 'yandex', 'sutochno', 'ostrovok', 'other'];
    const commissions = await api('GET', '/api/channel-commissions');
    const cf = {};
    const commissionsCard = h('div', { class: 'card card-pad' },
      h('h2', { style: { marginBottom: '6px' } }, 'Комиссии площадок'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Учитываются в отчётах: чистая выручка по источнику = выручка минус комиссия.'),
      h('div', { class: 'row3' }, CHANNEL_LIST.map((ch) => {
        const row = commissions.find((x) => x.channel === ch) || { percent: 0 };
        return h('label', { class: 'field' }, h('span', {}, SOURCE[ch]),
          cf[ch] = h('input', { class: 'input', type: 'number', min: 0, max: 100, step: '0.1', value: Number(row.percent) }));
      })),
      h('button', { class: 'btn primary', onclick: async () => {
        try {
          await api('PUT', '/api/channel-commissions', { items: CHANNEL_LIST.map((ch) => ({ channel: ch, percent: cf[ch].value })) });
          toast('Сохранено');
        } catch (ex) { toast(ex.message, true); }
      } }, 'Сохранить'));
    content.append(commissionsCard);

    content.append(servicesCard(), templatesCard());

    // данные аккаунта: выгрузка и удаление
    content.append(h('div', { class: 'card card-pad' },
      h('h2', { style: { marginBottom: '6px' } }, 'Данные аккаунта'),
      h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Вы вправе в любой момент забрать все свои данные или удалить аккаунт целиком — со всеми объектами, бронями, расходами и сотрудниками. Удаление необратимо.'),
      h('div', { style: { display: 'flex', gap: '10px', flexWrap: 'wrap' } },
        h('button', { class: 'btn', onclick: () => downloadCsv('/api/account/export', 'fligel_data.json') }, icon('download'), 'Скачать все данные (JSON)'),
        h('button', { class: 'btn danger', onclick: deleteAccountDialog }, icon('trash'), 'Удалить аккаунт'))));
  }
  load().catch((ex) => content.append(h('div', { class: 'card empty' }, ex.message)));
}

export function deleteAccountDialog() {
  const pass = h('input', { class: 'input', type: 'password', autocomplete: 'current-password' });
  const word = h('input', { class: 'input', placeholder: 'УДАЛИТЬ' });
  const err = h('div', { class: 'note bad', style: { display: 'none' } });
  const go = h('button', { class: 'btn primary', disabled: true, style: { background: 'var(--clay)', borderColor: 'var(--clay)' }, onclick: async () => {
    go.disabled = true;
    try {
      await api('POST', '/api/account/delete', { password: pass.value });
      closeModal(); store.set('token', null); state.me = null; location.hash = ''; render(); toast('Аккаунт удалён');
    } catch (ex) { err.textContent = ex.message; err.style.display = ''; go.disabled = false; }
  } }, 'Удалить навсегда');
  word.addEventListener('input', () => { go.disabled = word.value.trim().toUpperCase() !== 'УДАЛИТЬ'; });
  openModal('Удалить аккаунт навсегда?', h('div', {}, err,
    h('p', { class: 'muted small', style: { marginTop: 0 } }, 'Будут удалены все объекты, номера, брони, расходы, доходы, сотрудники и настройки. Отменить это нельзя — сначала скачайте данные, если они могут понадобиться.'),
    h('label', { class: 'field' }, h('span', {}, 'Ваш пароль'), pass),
    h('label', { class: 'field' }, h('span', {}, 'Для подтверждения введите слово УДАЛИТЬ'), word)),
  [h('button', { class: 'btn', onclick: () => closeModal(true) }, 'Отмена'), h('span', { class: 'spacer' }), go]);
}
