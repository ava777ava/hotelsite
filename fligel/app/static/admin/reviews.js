// Флигель — интерфейс администратора (раздел «отзывы гостей»). ES-модуль без сборки.
import { jumpToBooking, scopeSeg } from './app.js';
import { api, fmtDateTime, fmtShort, h, qs, state, toast } from './core.js';
import { plural } from './ui.js';

const stars = (avg) => (avg == null ? '—' : Number(avg).toFixed(1).replace('.', ','));
const reviewsWord = (n) => `${n} ${plural(n, ['отзыв', 'отзыва', 'отзывов'])}`;
const kpi = (label, value, unit) => h('div', { class: 'kpi' }, h('div', { class: 'l' }, label), h('div', { class: 'v' }, value, unit ? h('small', {}, unit) : null));

export async function viewReviews(main) {
  const body = h('div', { class: 'stack' });
  const scope = { value: 'current' };
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Отзывы гостей'), state.me.properties.length > 1 ? scopeSeg(scope, () => load()) : null), body);

  const openBooking = async (id) => {
    try { jumpToBooking(await api('GET', `/api/bookings/${id}`)); } catch (ex) { toast(ex.message, true); }
  };

  function distribution(data) {
    const max = Math.max(...data.distribution.map((x) => x.n), 1);
    return h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Оценки')), h('div', { class: 'card-pad' }, [5, 4, 3, 2, 1].map((r) => {
      const n = (data.distribution.find((x) => x.rating === r) || {}).n || 0;
      return h('div', { class: 'dist-row' }, h('span', { class: 'dist-l' }, `${r} из 5`),
        h('span', { class: 'dist-bar' }, h('i', { style: { width: `${(n / max) * 100}%` }, class: r <= data.low_rating ? 'low' : '' })),
        h('span', { class: 'dist-n' }, n));
    })));
  }

  function table(title, rows, label) {
    const trs = rows.map((r) => h('tr', {}, h('td', {}, label(r)), h('td', { class: 'muted small' }, reviewsWord(r.n)),
      h('td', { style: { textAlign: 'right' } }, h('b', {}, stars(r.avg)))));
    return h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, title)), h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, trs))));
  }

  function latest(data) {
    const items = data.items.map((it) => h('div', { class: 'review-item' },
      h('div', { class: 'review-head' },
        h('span', { class: `pill ${it.rating <= data.low_rating ? 'bad' : 'ok'}` }, `${it.rating} из 5`),
        h('b', {}, it.guest_name || 'Гость'),
        h('span', { class: 'muted small' }, `номер ${it.room_name} · ${fmtShort(it.check_in)}–${fmtShort(it.check_out)} · ${fmtDateTime(it.submitted_at)}`),
        h('button', { class: 'link', onclick: () => openBooking(it.booking_id) }, 'бронь')),
      it.comment ? h('div', { class: 'review-text' }, it.comment) : null));
    return h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Последние отзывы')), h('div', { class: 'card-pad' }, items));
  }

  function draw(data) {
    const o = data.overall;
    if (!o.n) {
      body.append(h('div', { class: 'card empty' }, h('h3', {}, 'Отзывов пока нет'),
        'Включите сценарий «Просьба об отзыве» в разделе «Автопилот» — гостю уйдёт письмо со ссылкой после выезда. Отзывы видны только вам и не публикуются.',
        data.waiting ? h('div', { class: 'muted small', style: { marginTop: '8px' } }, `Ссылок отправлено, ответа ждём: ${data.waiting}`) : null));
      return;
    }
    const multi = data.by_property.length > 1;
    body.append(
      h('div', { class: 'kpis' }, kpi('Средняя оценка', stars(o.avg), ' из 5'), kpi('Всего отзывов', o.n),
        kpi(`Низких (${data.low_rating} и ниже)`, o.low), data.waiting ? kpi('Ждём ответа', data.waiting) : null),
      distribution(data),
      h('div', { class: 'grid-2' },
        data.by_property.length > 1 ? table('По объектам', data.by_property, (p) => p.name) : null,
        table('По номерам (сначала худшие)', data.by_room.slice(0, 20), (r) => [r.name, multi ? h('span', { class: 'muted small' }, ` · ${r.property_name}`) : null])),
      latest(data));
  }

  async function load() {
    const data = await api('GET', '/api/reviews?' + qs({ property_id: scope.value === 'all' ? '' : state.propertyId }));
    body.innerHTML = '';
    draw(data);
  }
  load().catch((ex) => body.append(h('div', { class: 'card empty' }, ex.message)));
}
