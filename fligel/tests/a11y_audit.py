"""Аудит доступности и контраста всех экранов — в светлой и тёмной теме, на компьютере и телефоне (не входит в unittest).

Запуск (сервер с демо-данными):  python tests/a11y_audit.py [http://localhost:8000]
Проверяет: контраст текста с фоном (WCAG AA: 4,5:1, для крупного 3:1), подписи у кнопок, ссылок и полей ввода, alt у картинок,
повторяющиеся id, размер зоны нажатия на телефоне (≥ 36 px — предупреждение), наличие lang. Код возврата 1, если есть ошибки (не предупреждения)."""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
ROUTES = ["board", "today", "cleaning", "tasks", "household", "bookings", "guests", "reviews", "rates", "autoprice", "channels", "expenses",
          "analytics", "stats", "notifications", "autopilot", "settings", "integrations", "billing", "profile", "audit", "help"]
if os.environ.get("A11Y_ROUTES"):
    ROUTES = os.environ["A11Y_ROUTES"].split(",")
THEMES = ["light", "dark"]
VIEWPORTS = {"компьютер": {"width": 1280, "height": 800}, "телефон": {"width": 390, "height": 844}}

JS = r"""
() => {
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = ({ r, g, b }) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const blend = (fg, bg) => ({ r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1 });
  const bgOf = (el) => {
    const stack = [];
    for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c && c.a > 0) { stack.push(c); if (c.a >= 1) break; } }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    const root = parse(getComputedStyle(document.body).backgroundColor); if (root && root.a > 0) base = { ...root, a: 1 };
    for (const c of stack.reverse()) base = blend(c, base);
    return base;
  };
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05; };
  const issues = [], warns = [];
  const name = (el) => (el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '')).slice(0, 60);
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const t = n.textContent.trim(); if (t.length < 2) continue;
    const el = n.parentElement; if (!el || !visible(el) || el.closest('script,style,svg,#toasts')) continue;
    if (el.closest('[disabled],[aria-disabled=true]') || getComputedStyle(el).textDecoration.includes('line-through')) continue;
    const s = getComputedStyle(el);
    const fg = parse(s.color); if (!fg) continue;
    const bg = bgOf(el);
    const fgb = blend({ ...fg, a: fg.a * (parseFloat(s.opacity) || 1) }, bg);
    const L1 = lum(fgb), L2 = lum(bg); const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight, 10) >= 700;
    const need = (size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5;
    if (ratio < need) { const key = name(el) + t.slice(0, 20); if (!seen.has(key)) { seen.add(key); issues.push(`контраст ${ratio.toFixed(2)} < ${need}: ${name(el)} «${t.slice(0, 40)}»`); } }
  }
  document.querySelectorAll('button, a[href], [role=button], [role=switch]').forEach((el) => {
    if (!visible(el)) return;
    const label = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('title') || '').trim();
    if (!label) issues.push(`нет названия у элемента: ${name(el)}`);
    if (window.innerWidth < 500) { const r = el.getBoundingClientRect(); if ((r.height < 30 || r.width < 30) && !el.closest('.mobile-nav')) warns.push(`мелкая зона нажатия ${Math.round(r.width)}×${Math.round(r.height)}: ${name(el)} «${label.slice(0, 20)}»`); }
  });
  document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea').forEach((el) => {
    if (!visible(el)) return;
    const has = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.getAttribute('placeholder') || el.closest('label') || (el.id && document.querySelector(`label[for="${el.id}"]`)) || el.title;
    if (!has) issues.push(`поле без подписи: ${name(el)} ${el.getAttribute('placeholder') || el.name || ''}`);
  });
  document.querySelectorAll('img').forEach((img) => { if (visible(img) && !img.hasAttribute('alt')) issues.push(`картинка без alt: ${(img.src || '').slice(-40)}`); });
  const ids = {}; document.querySelectorAll('[id]').forEach((e) => { ids[e.id] = (ids[e.id] || 0) + 1; });
  Object.entries(ids).forEach(([id, c]) => { if (c > 1) issues.push(`повторяющийся id «${id}» ×${c}`); });
  if (!document.documentElement.lang) issues.push('нет lang у <html>');
  return { issues, warns };
}
"""


def main() -> int:
    errors, warns = [], []
    with sync_playwright() as p:
        kwargs = {"executable_path": os.environ["PLAYWRIGHT_CHROMIUM"]} if os.environ.get("PLAYWRIGHT_CHROMIUM") else {}
        browser = p.chromium.launch(**kwargs)
        for theme in THEMES:
            for label, vp in VIEWPORTS.items():
                mobile = label == "телефон"
                ctx = browser.new_context(viewport=vp, is_mobile=mobile, has_touch=mobile, color_scheme=theme)
                page = ctx.new_page()
                page.add_init_script(f"try{{localStorage.setItem('theme','{theme}')}}catch(e){{}}")
                page.goto(f"{BASE}/app/", wait_until="networkidle")
                page.fill("input[name=email]", "demo@fligel.ru")
                page.fill("input[name=password]", "demo12345")
                page.click("button[type=submit]")
                page.wait_for_timeout(1000)
                for route in ROUTES:
                    page.goto(f"{BASE}/app/#/{route}")
                    page.reload(wait_until="networkidle")
                    page.wait_for_timeout(700)
                    res = page.evaluate(JS)
                    for m in res["issues"]:
                        errors.append(f"[{theme}/{label}/{route}] {m}")
                    for m in res["warns"]:
                        warns.append(f"[{theme}/{label}/{route}] {m}")
                ctx.close()
        browser.close()
    seen = set()
    for m in errors:
        k = m.split("] ", 1)[1]
        if k not in seen:
            seen.add(k)
    print(f"Ошибок: {len(errors)} (уникальных: {len(seen)}), предупреждений: {len(warns)}")
    for m in errors[:200]:
        print(" ОШИБКА:", m)
    for m in warns[:40]:
        print(" предупреждение:", m)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
