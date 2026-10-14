const { C } = require('./content');
const out = C.map((x) => (x[0] === 'raw' ? ['cover'] : x));
require('fs').writeFileSync('content.json', JSON.stringify(out));
console.log(out.length);
