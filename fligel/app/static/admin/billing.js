// Флигель — интерфейс администратора (раздел «Тариф и счета» для владельца). ES-модуль без сборки.
import { api, fmtDate, fmtMoney, h, toast } from './core.js';
import { printInvoiceDoc } from './invoice.js';

const STATUS = { issued: ['warn', 'ждёт оплаты'], paid: ['ok', 'оплачен'], cancelled: ['none', 'отменён'] };

export async function viewBilling(main) {
  const box = h('div', { class: 'stack' });
  main.append(h('div', { class: 'page-head' }, h('h1', {}, 'Тариф и счета')), box);
  async function load() {
    const d = await api('GET', '/api/billing');
    box.innerHTML = '';
    const end = d.plan === 'trial' ? d.trial_ends : d.paid_until;
    const left = d.days_left;
    box.append(
      d.notice ? h('div', { class: `note ${d.notice.level === 'bad' ? 'bad' : 'warn'}` }, d.notice.text) : null,
      h('div', { class: 'kpis' },
        h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Тариф'), h('div', { class: 'v txt' }, d.plan_label)),
        h('div', { class: 'kpi' }, h('div', { class: 'l' }, d.plan === 'trial' ? 'Пробный период до' : 'Оплачено до'), h('div', { class: 'v txt' }, end ? fmtDate(end) : '—'),
          left != null ? h('div', { class: 'small muted' }, left >= 0 ? `осталось ${left} дн.` : `просрочено на ${-left} дн.`) : null),
        h('div', { class: 'kpi' }, h('div', { class: 'l' }, 'Объектов'), h('div', { class: `v${d.over_limit ? ' down' : ''}` }, d.objects_used, d.objects_limit ? h('small', {}, ` из ${d.objects_limit}`) : null))),
      d.is_demo ? h('div', { class: 'note' }, 'Это демо-версия: счета здесь не выставляются.') : h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Выбрать тариф и получить счёт')),
        h('div', { class: 'card-pad' }, h('p', { class: 'muted', style: { marginTop: 0 } }, 'Все функции доступны на любом тарифе — тариф зависит от числа объектов. Оплата по счёту (безналичный расчёт); после оплаты мы продлеваем доступ вручную. Данные сохраняются при любом сроке. Превышение лимита объектов работу не останавливает.'),
          h('div', { class: 'plan-pick' }, d.plans.map((p) => {
            const months = h('select', { class: 'input', 'aria-label': `Срок оплаты, тариф ${p.label}` }, [1, 3, 6, 12].map((m) => h('option', { value: m }, `${m} мес.`)));
            return h('div', { class: `plan-card${p.key === d.recommended_plan ? ' rec' : ''}` }, h('b', {}, p.label), h('div', { class: 'muted small' }, `до ${p.limit} объектов`), h('div', { class: 'plan-price' }, fmtMoney(p.price), h('small', {}, ' / мес')),
              p.key === d.recommended_plan ? h('span', { class: 'pill ok' }, 'подходит вам') : null, months,
              h('button', { class: 'btn small primary', onclick: async () => {
                try { const r = await api('POST', '/api/billing/invoices', { plan: p.key, months: months.value }); toast(`Счёт № ${r.number} выставлен`); load(); } catch (ex) { toast(ex.message, true); }
              } }, 'Выставить счёт'));
          })))),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Счета')),
        d.invoices.length ? h('div', { class: 'table-wrap' }, h('table', { class: 'list' }, h('tbody', {}, d.invoices.map((i) => h('tr', {},
          h('td', {}, h('b', {}, `№ ${i.number}`), h('div', { class: 'muted small' }, `от ${fmtDate(i.issued_on)}`)),
          h('td', {}, `${d.plans.find((p) => p.key === i.plan)?.label || i.plan}, ${i.months} мес.`, i.period_to ? h('div', { class: 'muted small' }, `доступ до ${fmtDate(i.period_to)}`) : null),
          h('td', { class: 'num' }, fmtMoney(i.amount)), h('td', {}, h('span', { class: `pill ${STATUS[i.status][0]}` }, STATUS[i.status][1])),
          h('td', { style: { textAlign: 'right' } }, h('button', { class: 'btn small', onclick: async () => { try { printInvoiceDoc(await api('GET', `/api/billing/invoices/${i.id}`)); } catch (ex) { toast(ex.message, true); } } }, 'Печать / PDF')))))))
          : h('div', { class: 'card-pad muted' }, 'Счетов пока нет.')),
      d.contact ? h('p', { class: 'muted small' }, `Вопросы по оплате: ${d.contact}`) : null);
  }
  load().catch((ex) => box.append(h('div', { class: 'card empty' }, ex.message)));
}
