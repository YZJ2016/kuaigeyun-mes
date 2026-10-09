#!/usr/bin/env node
/**
 * 删除 riveredge-frontend/dist 中未被 index/login 入口链引用的 assets 文件（含 .gz）。
 * 不删 dist 根目录下 static 拷贝的 fonts/img 等，除非位于 assets/ 且无引用。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.join(__dirname, '..');
const distDir = path.join(projectRoot, 'dist');

if (!fs.existsSync(distDir)) {
  console.error('dist 不存在，请先 build');
  process.exit(1);
}

/** @param {string} abs */
function relFromDist(abs) {
  return path.relative(distDir, abs).split(path.sep).join('/');
}

/** @param {string} ref from HTML/CSS/JS (may start with /) */
function resolveRef(fromFile, ref) {
  const clean = ref.split('?')[0].split('#')[0];
  if (!clean || clean.startsWith('data:')) return null;
  let target;
  if (clean.startsWith('/')) {
    target = path.join(distDir, clean.slice(1));
  } else if (clean.startsWith('assets/')) {
    target = path.join(distDir, clean);
  } else {
    target = path.resolve(path.dirname(fromFile), clean);
  }
  if (!target.startsWith(distDir)) return null;
  return target;
}

/** @type {Set<string>} */
const kept = new Set();
/** @type {string[]} */
const queue = [];

function enqueue(abs) {
  const norm = path.normalize(abs);
  if (!norm.startsWith(distDir) || kept.has(norm)) return;
  if (!fs.existsSync(norm) || !fs.statSync(norm).isFile()) return;
  kept.add(norm);
  queue.push(norm);
}

for (const name of ['index.html', 'login.html']) {
  const fp = path.join(distDir, name);
  if (fs.existsSync(fp)) enqueue(fp);
}

const htmlAttrRe = /\b(?:src|href)=["']([^"']+)["']/gi;
const cssUrlRe = /url\(\s*['"]?([^'")]+)['"]?\s*\)/gi;
const jsImportRe =
  /(?:from|import)\s*(?:\(\s*)?["']([^"']+\.(?:js|css|wasm|svg|png|jpg|jpeg|gif|webp))["']/gi;
const assetsPathRe = /["'](assets\/(?:js|css|wasm|media)\/[^"']+)["']/gi;

while (queue.length) {
  const fp = queue.pop();
  const ext = path.extname(fp).toLowerCase();
  const text = fs.readFileSync(fp, 'utf8');

  const scan = (re) => {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(text))) {
      const resolved = resolveRef(fp, m[1]);
      if (resolved) enqueue(resolved);
    }
  };

  if (ext === '.html') scan(htmlAttrRe);
  if (ext === '.css') scan(cssUrlRe);
  if (ext === '.js') {
    scan(jsImportRe);
    scan(assetsPathRe);
  }
}

for (const abs of [...kept]) {
  for (const suffix of ['.gz', '.br']) {
    const side = `${abs}${suffix}`;
    if (fs.existsSync(side)) kept.add(side);
  }
}

const assetsRoot = path.join(distDir, 'assets');
let removed = 0;
let freed = 0;

function unlinkSidecars(base) {
  for (const suffix of ['.gz', '.br']) {
    const side = `${base}${suffix}`;
    if (!fs.existsSync(side) || kept.has(side)) continue;
    freed += fs.statSync(side).size;
    fs.unlinkSync(side);
    removed += 1;
  }
}

function walkRemove(dir) {
  if (!fs.existsSync(dir)) return;
  for (const name of fs.readdirSync(dir)) {
    const fp = path.join(dir, name);
    if (!fs.existsSync(fp)) continue;
    const st = fs.statSync(fp);
    if (st.isDirectory()) {
      walkRemove(fp);
      if (fs.readdirSync(fp).length === 0) fs.rmdirSync(fp);
      continue;
    }
    if (kept.has(fp)) continue;
    if (fp.endsWith('.gz') || fp.endsWith('.br')) {
      freed += st.size;
      fs.unlinkSync(fp);
      removed += 1;
      continue;
    }
    freed += st.size;
    fs.unlinkSync(fp);
    removed += 1;
    unlinkSidecars(fp);
  }
}

walkRemove(assetsRoot);

const mb = (freed / (1024 * 1024)).toFixed(2);
console.log(`保留 assets 文件: ${[...kept].filter((p) => p.includes(`${path.sep}assets${path.sep}`)).length}`);
console.log(`删除过期 assets 文件: ${removed}（约 ${mb} MiB）`);
