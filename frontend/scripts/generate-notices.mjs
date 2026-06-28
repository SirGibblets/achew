// Generate a third-party license notices file for the frontend dependencies
// that get compiled into the shipped bundle (the production dependency closure
// plus their transitive deps). Build tools in devDependencies are not emitted
// to dist/, so they are excluded.
//
// Usage (run from frontend/, after `npm ci`):
//   node scripts/generate-notices.mjs > frontend-notices.txt

import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const NODE_MODULES = join(ROOT, 'node_modules');
const LICENSE_RE = /^(LICENSE|LICENCE|COPYING|NOTICE)/i;
const SEP = '\n' + '='.repeat(80) + '\n';

// Build tools (devDependencies) emit nothing to dist/ and need no attribution —
// except Svelte, whose runtime is compiled into the shipped bundle. Seed the
// closure with it explicitly so its (and its transitive deps') licenses ship.
const BUNDLED_DEV_DEPS = ['svelte'];

// Resolve the production dependency closure from package.json `dependencies`
// (plus BUNDLED_DEV_DEPS), walking each package's own `dependencies` transitively.
function prodClosure() {
  const root = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
  const seen = new Set();
  const queue = [...Object.keys(root.dependencies ?? {}), ...BUNDLED_DEV_DEPS];
  while (queue.length) {
    const name = queue.shift();
    if (seen.has(name)) continue;
    const pkgPath = join(NODE_MODULES, name, 'package.json');
    if (!existsSync(pkgPath)) continue;
    seen.add(name);
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'));
    queue.push(...Object.keys(pkg.dependencies ?? {}));
  }
  return [...seen].sort();
}

function licenseText(dir) {
  const files = readdirSync(dir).filter((f) => LICENSE_RE.test(f));
  return files
    .filter((f) => statSync(join(dir, f)).isFile())
    .map((f) => `--- ${f} ---\n${readFileSync(join(dir, f), 'utf8').trimEnd()}`)
    .join('\n\n');
}

const blocks = [];
for (const name of prodClosure()) {
  const dir = join(NODE_MODULES, name);
  const pkg = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'));
  const lic = pkg.license ?? (pkg.licenses ?? []).map((l) => l.type).join(' / ') ?? 'UNKNOWN';
  const text = licenseText(dir);
  const header = `${name} ${pkg.version ?? '?'}\nLicense: ${lic}`;
  blocks.push(text ? `${header}\n\n${text}` : `${header}\n\n(No license text file was bundled with this package.)`);
}

process.stdout.write(
  '#'.repeat(80) + '\n# Achew — Frontend (bundled) dependencies\n' + '#'.repeat(80) + '\n\n' + blocks.join(SEP) + '\n',
);
