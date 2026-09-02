/** Stripe-supported TypeScript and formatting rules for the app declaration. */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import eslint from '@eslint/js';
import { defineConfig } from 'eslint/config';
import tseslint from 'typescript-eslint';
import workspaces from 'eslint-plugin-workspaces';
import eslintConfigPrettier from 'eslint-config-prettier/flat';

import globals from 'globals';

import stripeAppsConfig from '@stripe/extensibility-eslint-plugin';

// Read additional ignore globs from package.json (written by the generate plugin
// to exclude generated SDK directories from linting).
let stripeGlobsToIgnore: string[] = [];
try {
  const configDir = dirname(fileURLToPath(import.meta.url));
  const packageJsonPath = resolve(configDir, './package.json');
  const pkg = JSON.parse(readFileSync(packageJsonPath, 'utf8'));
  const globs = pkg?.stripe?.eslintIgnoreGlobs;
  if (Array.isArray(globs)) {
    stripeGlobsToIgnore = globs.filter(
      (g: unknown): g is string => typeof g === 'string'
    );
  }
} catch {
  // package.json not found or unparseable — ignore
}

export default defineConfig([
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...stripeAppsConfig,

  // Global ignores
  {
    ignores: [
      '.build',
      '**/dist',
      '**/generated',
      '**/node_modules',
      'extensions/**',
      'custom-objects',
      'ui',
      ...stripeGlobsToIgnore,
    ],
  },

  // Common rules for all files
  {
    plugins: { workspaces },
    rules: {
      ...workspaces.configs.recommended.rules,
    },
  },

  // Config files (vitest.config.ts, eslint.config.ts, etc.)
  {
    name: 'ts-configs',
    files: ['extensions/*/*.config.m?ts', '*.config.m?ts', 'eslint.config.mts'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
      parserOptions: {
        projectService: false,
      },
    },
    rules: {
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },

  // JavaScript/MJS files (scripts, configs)
  {
    name: 'js-configs',
    files: ['**/*.js', '**/*.mjs'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
      parserOptions: {
        projectService: false,
      },
    },
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      'no-unused-vars': 'off',
    },
  },

  eslintConfigPrettier,
]);
