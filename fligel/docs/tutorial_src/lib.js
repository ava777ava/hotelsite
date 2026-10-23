const d = require('docx');
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, AlignmentType, HeadingLevel, LevelFormat, PageBreak, Footer, PageNumber, TabStopType } = d;

const FONT = 'Arial', MONO = 'Courier New';
const GREEN = '2F5D50', INK = '1C2420', GREY = '5B6559';
const PAGE_W = 11906, PAGE_H = 16838, MARGIN = 1134;            // A4, поля 2 см
const CONTENT_W = PAGE_W - 2 * MARGIN;                           // 9638

// **жирный**, `код` внутри строки
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: FONT, ...base }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ text: t.slice(2, -2), bold: true, font: FONT, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), font: MONO, size: (base.size || 22) - 2, color: '8A2D12', ...base, font: MONO }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: FONT, ...base }));
  return out;
}

const p = (text, o = {}) => new Paragraph({ spacing: { after: 120, line: 300 }, ...o, children: runs(text, o.run || {}) });
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, spacing: { before: 0, after: 200 }, children: [new TextRun({ text: t, font: FONT })] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, keepNext: true, spacing: { before: 280, after: 120 }, children: [new TextRun({ text: t, font: FONT })] });
const h3 = (t) => new Paragraph({ keepNext: true, spacing: { before: 200, after: 80 }, children: [new TextRun({ text: t, font: FONT, bold: true, size: 23, color: GREEN })] });

const noBorder = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const box = (fill, edge, title, lines) => new Table({
  width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [CONTENT_W],
  rows: [new TableRow({ children: [new TableCell({
    width: { size: CONTENT_W, type: WidthType.DXA },
    shading: { fill, type: ShadingType.CLEAR, color: 'auto' },
    margins: { top: 100, bottom: 100, left: 180, right: 180 },
    borders: { top: noBorder, bottom: noBorder, right: noBorder, left: { style: BorderStyle.SINGLE, size: 24, color: edge } },
    children: [new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: title, bold: true, font: FONT, color: edge })] }),
      ...lines.map((l) => new Paragraph({ spacing: { after: 60, line: 290 }, children: runs(l, { size: 21 }) }))],
  })] })],
});
const spacer = () => new Paragraph({ spacing: { after: 100 }, children: [] });

const code = (text) => {
  const lines = text.split('\n');
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [CONTENT_W],
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({
      width: { size: CONTENT_W, type: WidthType.DXA },
      shading: { fill: 'F1F3EE', type: ShadingType.CLEAR, color: 'auto' },
      margins: { top: 100, bottom: 100, left: 160, right: 160 },
      borders: { top: { style: BorderStyle.SINGLE, size: 4, color: 'D8DDD1' }, bottom: { style: BorderStyle.SINGLE, size: 4, color: 'D8DDD1' }, left: { style: BorderStyle.SINGLE, size: 4, color: 'D8DDD1' }, right: { style: BorderStyle.SINGLE, size: 4, color: 'D8DDD1' } },
      children: lines.map((l) => new Paragraph({ spacing: { after: 0, line: 270 }, children: [new TextRun({ text: l || ' ', font: MONO, size: 19 })] })),
    })] })],
  });
};

function table(widths, header, rows) {
  const total = widths.reduce((a, b) => a + b, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: 'D8DDD1' };
  const borders = { top: border, bottom: border, left: border, right: border };
  const cell = (t, w, head) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders,
    shading: head ? { fill: GREEN, type: ShadingType.CLEAR, color: 'auto' } : undefined,
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: String(t).split('\n').map((line) => new Paragraph({ spacing: { after: 30 }, children: runs(line, head ? { bold: true, color: 'FFFFFF', size: 20 } : { size: 20 }) })),
  });
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: header.map((t, i) => cell(t, widths[i], true)) }),
      ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((t, i) => cell(t, widths[i], false)) }))],
  });
}

let listId = 0;
const numberings = [{ reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }];
const bullets = (items) => items.map((t) => new Paragraph({ numbering: { reference: 'bul', level: 0 }, spacing: { after: 70, line: 290 }, children: runs(t) }));
const numbered = (items) => {
  const ref = 'num' + (++listId);
  numberings.push({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] });
  return items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 80, line: 290 }, children: runs(t) }));
};
const checks = (items) => items.map((t) => new Paragraph({ spacing: { after: 70, line: 290 }, indent: { left: 540, hanging: 400 }, children: [new TextRun({ text: '☐  ', font: 'DejaVu Sans', size: 24 }), ...runs(t)] }));

function build(title, sub, content, outFile) {
  const children = [];
  for (const [kind, ...a] of content) {
    switch (kind) {
      case 'h1': children.push(h1(a[0])); break;
      case 'h1n': children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 240, after: 200 }, children: [new TextRun({ text: a[0], font: FONT })] })); break;
      case 'h2': children.push(h2(a[0])); break;
      case 'h3': children.push(h3(a[0])); break;
      case 'p': children.push(p(a[0])); break;
      case 'b': children.push(...bullets(a[0])); break;
      case 'n': children.push(...numbered(a[0])); break;
      case 'c': children.push(...checks(a[0])); break;
      case 'code': children.push(code(a[0]), spacer()); break;
      case 'tip': children.push(box('E6F1EC', GREEN, a[0], a[1]), spacer()); break;
      case 'warn': children.push(box('FBEFD9', 'B7791F', a[0], a[1]), spacer()); break;
      case 'danger': children.push(box('F8E3DA', 'B4562E', a[0], a[1]), spacer()); break;
      case 'table': children.push(table(a[0], a[1], a[2]), spacer()); break;
      case 'raw': children.push(...a[0]); break;
      default: throw new Error('unknown ' + kind);
    }
  }
  return new Document({
    creator: 'Флигель', title,
    styles: {
      default: { document: { run: { font: FONT, size: 22, color: INK } } },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 36, bold: true, color: GREEN, font: FONT }, paragraph: { spacing: { before: 0, after: 200 }, outlineLevel: 0 } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 27, bold: true, color: INK, font: FONT }, paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1 } },
      ],
    },
    numbering: { config: numberings },
    sections: [{
      properties: { page: { size: { width: PAGE_W, height: PAGE_H }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
      footers: { default: new Footer({ children: [new Paragraph({ tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }], children: [new TextRun({ text: title, font: FONT, size: 17, color: GREY }), new TextRun({ text: '\t', font: FONT }), new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 17, color: GREY })] })] }) },
      children,
    }],
  });
}
module.exports = { build, Packer, Paragraph, TextRun, AlignmentType, p, runs, FONT, GREEN, GREY, PAGE_W, CONTENT_W, PageBreak };
