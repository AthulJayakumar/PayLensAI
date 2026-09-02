/** Discover optional Stripe extension test projects when extensions are added. */

import { defineConfig } from 'vitest/config';
import { existsSync, readdirSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const rootDir = dirname(fileURLToPath(import.meta.url));
const extensionsDir = resolve(rootDir, 'extensions');

const extensionProjects = existsSync(extensionsDir)
  ? readdirSync(extensionsDir)
      .filter((name) => existsSync(resolve(extensionsDir, name, 'package.json')))
      .map((name) => resolve(extensionsDir, name))
  : [];

const coProjects = existsSync(resolve(rootDir, 'custom-objects/package.json'))
  ? [resolve(rootDir, 'custom-objects')]
  : [];

const projects = [...extensionProjects, ...coProjects];

if (projects.length === 0) {
  console.debug(`No vitest projects detected. This means either:
- You have no extension projects defined, in which case this warning is expected.
- There is an internal error detecting vitest projects relative to the project root
  ${rootDir}.
`);
}

export default projects.length > 0
  ? defineConfig({
      test: {
        projects,
        passWithNoTests: true,
        setupFiles: ['@stripe/extensibility-test-helpers/vitest'],

        // Only run tests from src, not compiled dist
        exclude: ['**/node_modules', '**/dist'],
        // Place snapshots alongside test files instead of in __snapshots__
        snapshotFormat: {
          escapeString: false,
          printBasicPrototype: false,
        },
        resolveSnapshotPath: (testPath, snapExtension) => {
          return testPath.replace(/\.test\.ts$/, `.test${snapExtension}`);
        },
      },
    })
  : defineConfig({ test: { passWithNoTests: true, include: [] } });
