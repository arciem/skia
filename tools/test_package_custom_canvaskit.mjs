import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, symlinkSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { packageEngine } from './package-custom-canvaskit.mjs';

function fixture() {
  const root = mkdtempSync(resolve(tmpdir(), 'engine-packaging-'));
  const input = resolve(root, 'input'); mkdirSync(input);
  writeFileSync(resolve(input, 'canvaskit.js'), 'module.exports = async () => ({fixture: true});\n');
  writeFileSync(resolve(input, 'canvaskit.wasm'), Buffer.from([0, 97, 115, 109, 1, 0, 0, 0]));
  const types = resolve(input, 'index.d.ts'); writeFileSync(types, 'export interface Paragraph { getParagraphInfo(text: string): unknown }\n');
  return { root, input, types, output: resolve(root, 'output') };
}
const npm = process.env.npm_execpath;
if (!npm) throw new Error('Run through npm exec with the selected npm executable');

test('existing and dangling output refuse without modifying inputs or targets', () => {
  const f = fixture();
  try {
    mkdirSync(f.output); writeFileSync(resolve(f.output, 'keep'), 'original');
    assert.throws(() => packageEngine(f.input, f.types, f.output, npm), /fresh/);
    assert.equal(readFileSync(resolve(f.output, 'keep'), 'utf8'), 'original');
    const link = resolve(f.root, 'link'); symlinkSync(resolve(f.root, 'absent'), link);
    assert.throws(() => packageEngine(f.input, f.types, link, npm), /fresh/);
    assert.equal(existsSync(resolve(f.root, 'absent')), false);
  } finally { rmSync(f.root, { recursive: true }); }
});
test('nested or invalid inputs refuse before creating output', () => {
  const f = fixture();
  try {
    assert.throws(() => packageEngine(f.input, f.types, resolve(f.input, 'output'), npm), /outside/);
    assert.throws(() => packageEngine(f.input, f.types, f.output, 'npm'), /absolute/);
    writeFileSync(resolve(f.input, 'canvaskit.wasm'), 'invalid');
    assert.throws(() => packageEngine(f.input, f.types, f.output, npm), /WASM/);
    assert.equal(existsSync(f.output), false);
  } finally { rmSync(f.root, { recursive: true }); }
});
test('raw and normalized packages preserve bodies and execute the ESM wrapper', async () => {
  const f = fixture();
  try {
    const result = packageEngine(f.input, f.types, f.output, npm);
    assert.equal(result.version, '2.0.0');
    assert.deepEqual(readFileSync(resolve(f.output, 'node/index.d.mts')), readFileSync(f.types));
    for (const variant of ['original', 'node']) {
      for (const name of ['canvaskit.js', 'canvaskit.wasm']) assert.deepEqual(readFileSync(resolve(f.output, variant, name)), readFileSync(resolve(f.input, name)));
      const listing = spawnSync('tar', ['-tzf', resolve(f.output, result.artifacts[variant].file)], { encoding: 'utf8' });
      assert.equal(listing.status, 0, listing.stderr);
      assert.deepEqual(listing.stdout.trim().split('\n').sort(), result.artifacts[variant].files.map(name => 'package/' + name).sort());
    }
    const { default: init } = await import(resolve(f.output, 'node/wrapper.mjs'));
    assert.deepEqual(await init({}), { fixture: true });
  } finally { rmSync(f.root, { recursive: true }); }
});
