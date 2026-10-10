// Небольшие помощники интерфейса без привязки к приложению: склонения, даты по-человечески,
// поля денег с пробелами, праздники РФ, скелетоны. Подключается из app.js как модуль.

export const plural = (n, [one, few, many]) => {
  const a = Math.abs(n) % 10, b = Math.abs(n) % 100;
  return a === 1 && b !== 11 ? one : (a >= 2 && a <= 4 && (b < 10 || b >= 20) ? few : many);
};
export const WORDS = {
  night: ['ночь', 'ночи', 'ночей'], guest: ['гость', 'гостя', 'гостей'], booking: ['бронь', 'брони', 'броней'],
  day: ['день', 'дня', 'дней'], room: ['номер', 'номера', 'номеров'], visit: ['визит', 'визита', 'визитов'],
};
export const count = (n, key) => `${n} ${plural(n, WORDS[key])}`;

const pad = (n) => String(n).padStart(2, '0');
const parse = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
const isoOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const ON_WEEKDAY = ['в воскресенье', 'в понедельник', 'во вторник', 'в среду', 'в четверг', 'в пятницу', 'в субботу'];

// «сегодня», «завтра», «в пятницу», «через 9 дней», «3 дня назад» — а дальше обычная дата
export function humanDay(s, ref = new Date()) {
  const base = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate());
  const diff = Math.round((parse(s) - base) / 86400000);
  if (diff === 0) return 'сегодня';
  if (diff === 1) return 'завтра';
  if (diff === 2) return 'послезавтра';
  if (diff === -1) return 'вчера';
  if (diff === -2) return 'позавчера';
  if (diff > 2 && diff < 7) return ON_WEEKDAY[parse(s).getDay()];
  if (diff >= 7 && diff <= 30) return `через ${count(diff, 'day')}`;
  if (diff < -2 && diff >= -30) return `${count(-diff, 'day')} назад`;
  const d = parse(s);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// «12–15 октября» / «30 октября – 2 ноября»
export function dateRange(a, b) {
  const x = parse(a), y = parse(b);
  if (x.getMonth() === y.getMonth() && x.getFullYear() === y.getFullYear()) return `${x.getDate()}–${y.getDate()} ${MONTHS[y.getMonth()]}`;
  return `${x.getDate()} ${MONTHS[x.getMonth()]} – ${y.getDate()} ${MONTHS[y.getMonth()]}`;
}

// ---------- поля денег: «12 500» при вводе, а .value отдаёт «12500» ----------
const nativeValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
const group = (digits) => digits.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
export function moneyize(el) {
  el.type = 'text';
  el.inputMode = 'decimal';
  el.autocomplete = 'off';
  const format = (raw) => {
    const s = String(raw ?? '').replace(/[^\d.,]/g, '').replace(',', '.');
    const [int, frac] = s.split('.');
    return group((int || '').replace(/^0+(?=\d)/, '')) + (frac !== undefined ? '.' + frac.slice(0, 2) : '');
  };
  Object.defineProperty(el, 'value', {
    get() { return nativeValue.get.call(el).replace(/\s/g, ''); },
    set(v) { nativeValue.set.call(el, format(v)); },
    configurable: true,
  });
  el.addEventListener('input', () => {
    const before = nativeValue.get.call(el);
    const pos = el.selectionStart ?? before.length;
    const digitsLeft = before.slice(0, pos).replace(/[^\d.,]/g, '').length;
    nativeValue.set.call(el, format(before));
    // вернуть курсор на то же место среди цифр
    let seen = 0, np = 0;
    const now = nativeValue.get.call(el);
    while (np < now.length && seen < digitsLeft) { if (/[\d.]/.test(now[np])) seen++; np++; }
    try { el.setSelectionRange(np, np); } catch { /* не поддерживается */ }
  });
  el.addEventListener('focus', () => { setTimeout(() => { try { el.select(); } catch { /* ignore */ } }, 0); });
  if (nativeValue.get.call(el)) nativeValue.set.call(el, format(nativeValue.get.call(el)));
  return el;
}

// ---------- праздники РФ (только даты с фиксированным числом; переносы выходных назначает правительство каждый год) ----------
const FIXED = {
  '01-01': 'Новый год', '01-02': 'Новогодние каникулы', '01-03': 'Новогодние каникулы', '01-04': 'Новогодние каникулы',
  '01-05': 'Новогодние каникулы', '01-06': 'Новогодние каникулы', '01-07': 'Рождество', '01-08': 'Новогодние каникулы',
  '02-23': 'День защитника Отечества', '03-08': 'Международный женский день', '05-01': 'Праздник Весны и Труда',
  '05-09': 'День Победы', '06-12': 'День России', '11-04': 'День народного единства',
};
export const holidayName = (s) => FIXED[s.slice(5, 10)] || '';

// ---------- скелетоны ----------
export function skeleton(rows = 5, kind = 'row') {
  const wrap = document.createElement('div');
  wrap.className = `skeleton skeleton-${kind}`;
  wrap.setAttribute('aria-busy', 'true');
  wrap.setAttribute('aria-label', 'Загрузка');
  for (let i = 0; i < rows; i++) {
    const r = document.createElement('div');
    r.className = 'sk-line';
    r.style.width = `${60 + ((i * 17) % 35)}%`;
    wrap.append(r);
  }
  return wrap;
}

// Короткая метка площадки вместо текста там, где мало места; цвета те же, что на шахматке
export const SOURCE_ABBR = { manual: '✎', direct: 'С', avito: 'А', yandex: 'Я', sutochno: 'Су', ostrovok: 'О', other: '•' };
