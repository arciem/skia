#!/usr/bin/env node
import { existsSync, lstatSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { resolve, dirname, isAbsolute, basename } from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const digest = body => createHash('sha256').update(body).digest('hex');
export function packageEngine(buildPath, typesPath, outputPath, npmPath) {
  const output = resolve(outputPath);
  if (existsSync(output) || (() => { try { return lstatSync(output).isSymbolicLink(); } catch (e) { if (e.code === 'ENOENT') return false; throw e; } })()) throw new Error('Output must be fresh');
  if (!isAbsolute(npmPath) || !existsSync(npmPath)) throw new Error('An existing absolute npm executable is required');
  const build = realpathSync(buildPath);
  const types = realpathSync(typesPath);
  const parent = realpathSync(dirname(output));
  if (parent === build || parent.startsWith(build + '/')) throw new Error('Output must be outside build inputs');
  const files = new Map([
    ['canvaskit.js', readFileSync(resolve(build, 'canvaskit.js'))],
    ['canvaskit.wasm', readFileSync(resolve(build, 'canvaskit.wasm'))],
    ['index.d.ts', readFileSync(types)],
  ]);
  if (!files.get('canvaskit.wasm').subarray(0, 4).equals(Buffer.from([0, 97, 115, 109]))) throw new Error('Invalid WASM input');
  if (!files.get('index.d.ts').toString().includes('getParagraphInfo')) throw new Error('Custom paragraph declarations are required');
  mkdirSync(output);
  const manifest = { name: 'canvaskit', version: '2.0.0', source_files: Object.fromEntries([...files].map(([name, body]) => [name, { bytes: body.length, sha256: digest(body) }])), artifacts: {} };
  for (const variant of ['original', 'node']) {
    const folder = resolve(output, variant); mkdirSync(folder);
    for (const [name, body] of files) writeFileSync(resolve(folder, name), body);
    const pkg = { name: 'canvaskit', version: '2.0.0', main: './canvaskit.js', types: './index.d.ts', files: [...files.keys()], dependencies: { '@webgpu/types': '0.1.64' } };
    if (variant === 'node') {
      writeFileSync(resolve(folder, 'index.d.mts'), files.get('index.d.ts'));
      writeFileSync(resolve(folder, 'wrapper.mjs'), 'import CanvasKitInit from "./canvaskit.js";\nexport default async function init(options) {\n  if (typeof CanvasKitInit !== "function") throw new Error("Failed to load CanvasKit: Module is not a function.");\n  return CanvasKitInit(options);\n}\n');
      Object.assign(pkg, { main: './wrapper.mjs', types: './index.d.mts', exports: { '.': { types: './index.d.mts', default: './wrapper.mjs' } } });
      pkg.files.push('index.d.mts', 'wrapper.mjs');
    }
    writeFileSync(resolve(folder, 'package.json'), JSON.stringify(pkg, null, 2) + '\n');
    const packed = spawnSync(npmPath, ['pack', '--ignore-scripts', '--json', '--pack-destination', folder], { cwd: folder, encoding: 'utf8' });
    if (packed.status !== 0) throw new Error('npm pack failed: ' + packed.stdout + packed.stderr);
    const rows = JSON.parse(packed.stdout); if (rows.length !== 1) throw new Error('Unexpected pack output');
    const archive = resolve(folder, rows[0].filename);
    const body = readFileSync(archive);
    manifest.artifacts[variant] = { file: variant + '/' + basename(archive), bytes: body.length, sha256: digest(body), integrity: rows[0].integrity, files: rows[0].files.map(x => x.path).sort() };
  }
  writeFileSync(resolve(output, 'PACKAGING.json'), JSON.stringify(manifest, null, 2) + '\n');
  return manifest;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  if (process.argv.length !== 6) throw new Error('Usage: package-custom-canvaskit.mjs BUILD_DIR TYPES_FILE FRESH_OUTPUT_DIR ABSOLUTE_NPM');
  console.log(JSON.stringify(packageEngine(...process.argv.slice(2))));
}
