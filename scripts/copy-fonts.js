// Copies PDFportal's two fonts from node_modules into src/fonts, so the app
// works fully offline (the page may only load files it ships with).
//
//   Oswald   the condensed capitals of every heading  (SIL Open Font License)
//   DM Mono  small text, chips and numbers in captions (SIL Open Font License)
//
// Both licences let us bundle and redistribute the fonts; their texts are
// copied next to the files, as the licence asks.
//
//   npm run fonts

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const out = path.join(root, 'src', 'fonts');
const files = [
  ['@fontsource-variable/oswald/files/oswald-latin-wght-normal.woff2', 'oswald.woff2'],
  ['@fontsource/dm-mono/files/dm-mono-latin-400-normal.woff2', 'dm-mono-400.woff2'],
  ['@fontsource/dm-mono/files/dm-mono-latin-500-normal.woff2', 'dm-mono-500.woff2'],
  ['@fontsource-variable/oswald/LICENSE', 'OFL-oswald.txt'],
  ['@fontsource/dm-mono/LICENSE', 'OFL-dm-mono.txt'],
];

fs.mkdirSync(out, { recursive: true });
for (const [from, to] of files) {
  fs.copyFileSync(path.join(root, 'node_modules', from), path.join(out, to));
  console.log(`src/fonts/${to}`);
}
