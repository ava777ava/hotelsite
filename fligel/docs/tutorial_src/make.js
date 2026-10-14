const fs = require('fs');
const { build, Packer } = require('./lib');
const { C } = require('./content');
const TITLE = 'Флигель — туториал по запуску';
const doc = build(TITLE, '', C);
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(process.argv[2], b); console.log('written', process.argv[2], b.length); });
