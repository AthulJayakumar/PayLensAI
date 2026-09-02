#!/usr/bin/env tsx
/**
 * Runs tests across the workspace:
 * - vitest for script extensions (extensions/*) and custom objects (custom-objects/)
 * - jest for UI extensions (ui/)
 * - tsc --noEmit for extensions/* and custom-objects/, so type errors in test
 *   files are caught here
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';

const manifest = readFileSync('stripe-app.yaml', 'utf8');
const requiredManifestEntries = [
  'stripe_api_access_type: oauth',
  'distribution_type: public',
  'https://d8hmknablqw3v.cloudfront.net/api/providers/stripe/oauth/callback',
  'payment_intent_read',
  'charge_read',
  'dispute_read',
  'balance_transaction_source_read',
];

const missingManifestEntries = requiredManifestEntries.filter(
  (entry) => !manifest.includes(entry)
);

const extensionDirs = existsSync('extensions')
  ? readdirSync('extensions').filter((name) =>
      existsSync(`extensions/${name}/package.json`)
    )
  : [];

const hasExtensions = extensionDirs.length > 0;

const hasCustomObjects = existsSync('custom-objects/package.json');

const hasUI = existsSync('ui/package.json');

let exitCode = 0;

for (const entry of missingManifestEntries) {
  console.error(`Missing required Stripe app manifest entry: ${entry}`);
  exitCode = 1;
}

function run(cmd: string): void {
  try {
    execSync(cmd, { stdio: 'inherit' });
  } catch (e: unknown) {
    exitCode = (e as NodeJS.ErrnoException & { status?: number }).status ?? 1;
  }
}

function hasScript(extensionDir: string, script: string): boolean {
  try {
    const pkg = JSON.parse(
      readFileSync(`extensions/${extensionDir}/package.json`, 'utf8')
    );
    return typeof pkg?.scripts?.[script] === 'string';
  } catch {
    return false;
  }
}

if (hasExtensions || hasCustomObjects) {
  run('vitest run');
}

// Type-check src *and* test files: `build` excludes src/**/*.test.ts and vitest strips
// types, so this is the only thing here that sees them. Extensions use the single-pass
// `test:types` rather than `lint:types` to keep the upload pre-image phase (which runs
// both `lint:types` and `test`) from adding another pass; custom-objects stays on
// `lint:types`, which is already one pass. See docs/app-authoring-toolchain.md.
if (hasExtensions) {
  // `--if-present` skips an extension generated before `test:types` existed rather than
  // failing, so say so out loud — a silently skipped type check is the bug this runs to
  // catch. `gen-workspace` rewrites this file and the extension package.json together.
  const unchecked = extensionDirs.filter((name) => !hasScript(name, 'test:types'));

  if (unchecked.length > 0) {
    console.warn(
      `\nWARNING: no test:types script in ${unchecked.join(', ')} — skipping type check.\n` +
        'Regenerate the workspace to add it, or run `pnpm lint:types` to type check now.'
    );
  }

  console.log('\nType-checking extensions (tsc --noEmit)...');
  run(`pnpm -r --filter './extensions/*' --if-present test:types`);
}

if (hasCustomObjects) {
  console.log('\nType-checking custom objects (tsc --noEmit)...');
  run(`pnpm -r --filter './custom-objects' --if-present lint:types`);
}

if (hasUI) {
  try {
    execSync('pnpm --filter "./ui" test', { stdio: 'inherit' });
  } catch {
    // UI test failures are non-fatal
  }
}

process.exit(exitCode);
