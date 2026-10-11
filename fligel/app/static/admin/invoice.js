// Флигель — счёт на оплату тарифа (печатная форма; используется в приложении клиента и в панели оператора). ES-модуль без сборки.
import { fmtDate, fmtMoney, h } from './core.js';

const row = (label, value) => (value ? h('tr', {}, h('td', { style: { padding: '2px 12px 2px 0', color: '#555', whiteSpace: 'nowrap', verticalAlign: 'top' } }, label), h('td', { style: { padding: '2px 0' } }, value)) : null);

export function printInvoiceDoc(inv) {
  const s = inv.seller;
  const th = (t, right) => h('th', { style: { textAlign: right ? 'right' : 'left', padding: '6px 8px', borderBottom: '2px solid #000', fontSize: '13px' } }, t);
  const td = (t, right, bold) => h('td', { style: { textAlign: right ? 'right' : 'left', padding: '6px 8px', borderBottom: '1px solid #ccc', fontWeight: bold ? 700 : 400 } }, t);
  const months = `${inv.months} мес.`;
  document.getElementById('print-sheet')?.remove();
  document.body.append(h('div', { id: 'print-sheet' },
    s.configured ? null : h('p', { style: { color: '#B4562E', border: '1px solid #B4562E', padding: '8px' } }, 'Реквизиты продавца не заполнены (переменные SELLER_* в .env) — заполните их перед отправкой счёта клиенту.'),
    h('h1', { style: { fontSize: '22px', marginBottom: '2px' } }, `Счёт на оплату № ${inv.number}`),
    h('p', { style: { marginTop: 0, color: '#555' } }, `от ${fmtDate(inv.issued_on)} ${String(inv.issued_on).slice(0, 4)} г.`),
    h('table', { style: { borderCollapse: 'collapse', fontSize: '14px', marginBottom: '14px' } }, h('tbody', {},
      row('Поставщик:', [s.name, s.inn ? `ИНН ${s.inn}` : '', s.kpp ? `КПП ${s.kpp}` : '', s.ogrn ? `ОГРН(ИП) ${s.ogrn}` : '', s.address].filter(Boolean).join(', ')),
      row('Банк:', [s.bank, s.bik ? `БИК ${s.bik}` : ''].filter(Boolean).join(', ')),
      row('Расчётный счёт:', s.account), row('Корр. счёт:', s.corr_account),
      row('Контакты:', [s.phone, s.email].filter(Boolean).join(', ')),
      row('Покупатель:', inv.account_name))),
    h('table', { style: { borderCollapse: 'collapse', width: '100%', fontSize: '14px' } },
      h('thead', {}, h('tr', {}, th('Наименование'), th('Срок', 1), th('Сумма', 1))),
      h('tbody', {}, h('tr', {}, td(`Право использования сервиса «Флигель», тариф «${inv.plan_label}»`), td(months, 1), td(fmtMoney(inv.amount), 1)),
        h('tr', {}, td('Итого к оплате', 0, 1), td('', 1), td(fmtMoney(inv.amount), 1, 1)))),
    s.vat_note ? h('p', { style: { marginTop: '10px' } }, s.vat_note) : null,
    inv.note ? h('p', { style: { color: '#555' } }, inv.note) : null,
    h('p', { style: { marginTop: '14px' } }, `В назначении платежа укажите: «Оплата по счёту № ${inv.number}». После поступления оплаты доступ продлевается — вручную, обычно в течение рабочего дня.`),
    s.signer ? h('p', { style: { marginTop: '28px' } }, `Руководитель / ИП: ____________ ${s.signer}`) : null));
  window.print();
}
