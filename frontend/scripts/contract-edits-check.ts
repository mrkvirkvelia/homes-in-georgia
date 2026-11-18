// npx esbuild scripts/contract-edits-check.ts --bundle --platform=node | node — self-check for the clause edits and the
// bank field (src/features/contracts/templates.ts editClause / buildContract, David 11-18)
import assert from 'node:assert/strict';
import { DRAFTS } from '../src/features/contracts/templates-david';
import { EMPTY, buildContract, clauseLang, editClause, type CxEdits, type DraftBlock } from '../src/features/contracts/templates';

const texts = (bs: DraftBlock[]): { k?: string; p: string }[] => bs.flatMap((b) => (typeof b === 'string' ? [{ p: b }]
  : 'p' in b ? [b] : b.t.flatMap((r) => r.flatMap((c) => texts(Array.isArray(c) ? c : c.c)))));
const find = (bs: DraftBlock[], start: string) => texts(bs).filter((x) => x.p.startsWith(start));

// bank details in 2.8 of every enabled template and both languages; empty = the blank line
const d = { ...EMPTY, bank_account: 'TBC Bank GE29TB7777777777777777' };
for (const lang of ['GEO', 'RU', 'EN'] as const) for (const with_pets of [false, true]) {
  const doc = buildContract(DRAFTS, 'rent', lang, { ...d, with_pets });
  const c28 = find(doc.body, '2.8.');
  assert.equal(c28.length, lang === 'GEO' ? 1 : 2, `${doc.key} 2.8 count`);
  for (const c of c28) assert.ok(c.p.endsWith('TBC Bank GE29TB7777777777777777'), `${doc.key}: ${c.p.slice(-60)}`);
  for (const c of find(buildContract(DRAFTS, 'rent', lang, { ...EMPTY, with_pets }).body, '2.8.')) assert.ok(c.p.endsWith('_____'), doc.key);
}

// edits: change / remove / add after (also after an added one), per language column, kept across a data change
let e: CxEdits = {};
const ru = buildContract(DRAFTS, 'rent', 'RU', d);
const [ka28, ru28] = find(ru.body, '2.8.');
assert.equal(clauseLang(ru, ka28.k!), 'GEO');
assert.equal(clauseLang(ru, ru28.k!), 'RU');
e = editClause(e, ru.key, ru28.k!, { text: '2.8. Оплата только наличными.' });
e = editClause(e, ru.key, ru28.k!, { add: '2.8.1. Первый новый' });
e = editClause(e, ru.key, `${ru28.k}+0`, { add: '2.8.2. Второй новый' });
e = editClause(e, ru.key, ka28.k!, { del: true });
const out = texts(buildContract(DRAFTS, 'rent', 'RU', { ...d, price_usd: '999' }, e).body).map((x) => x.p);
const i = out.indexOf('2.8. Оплата только наличными.');
assert.ok(i > 0);
assert.deepEqual(out.slice(i, i + 3), ['2.8. Оплата только наличными.', '2.8.1. Первый новый', '2.8.2. Второй новый']);
assert.equal(out.filter((x) => x.startsWith('2.8.')).length, 3);  // the Georgian 2.8 is gone
assert.ok(out.some((x) => x.includes('999')), 'fields still filled');
// remove an added one, reset the changed one
e = editClause(e, ru.key, `${ru28.k}+0`, { del: true });
e = editClause(e, ru.key, ru28.k!, { reset: true });
const back = texts(buildContract(DRAFTS, 'rent', 'RU', d, e).body).map((x) => x.p);
assert.ok(back.includes('2.8.2. Второй новый') && !back.includes('2.8.1. Первый новый'));
assert.ok(back.some((x) => x.startsWith('2.8. "**Арендатор**"')));
// edits of another draft (pets switched on) don't touch this one
assert.equal(texts(buildContract(DRAFTS, 'rent', 'RU', { ...d, with_pets: true }, e).body).filter((x) => x.p.startsWith('2.8.')).length, 2);
console.log('contract edits: ok');
