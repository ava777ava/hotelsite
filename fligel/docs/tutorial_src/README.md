# Исходники туториала по запуску

`content.js` — единственный источник текста (раздел за разделом). Из него собираются оба файла в папке `docs/`:

```bash
cd docs/tutorial_src
npm install docx                     # единственный npm-пакет
node make.js ../Fligel_Tutorial.docx  # Word
node dump.js                          # content.json для PDF
pip install reportlab
python mkpdf.py ../Fligel_Tutorial.pdf   # PDF (шрифты Liberation Sans/Mono)
```

После правок текста пересоберите оба файла, чтобы PDF и Word не расходились.
