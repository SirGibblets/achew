import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import svelte from 'eslint-plugin-svelte';
import svelteParser from 'svelte-eslint-parser';

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', '*.config.js', '*.config.ts'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...svelte.configs['flat/recommended'],
  {
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: {
        projectService: true,
        extraFileExtensions: ['.svelte'],
      },
    },
  },
  {
    files: ['**/*.svelte', '**/*.svelte.ts'],
    languageOptions: {
      parser: svelteParser,
      parserOptions: {
        parser: tseslint.parser,
        projectService: true,
        extraFileExtensions: ['.svelte'],
        svelteFeatures: { runes: true },
      },
    },
    rules: {
      // False positive on Svelte 5's `$bindable(default)` prop pattern
      'no-useless-assignment': 'off',
    },
  },
  {
    // Standalone Node build/tooling scripts:
    // lint without the type-aware project service, which is scoped to the typed
    // browser app via tsconfig and would otherwise reject these files.
    files: ['scripts/**/*.{js,mjs,cjs}'],
    languageOptions: {
      globals: { ...globals.node },
      parserOptions: { projectService: false },
    },
  },
  {
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',
      'svelte/require-each-key': 'off',
      'svelte/no-useless-mustaches': 'warn',
      'svelte/no-useless-children-snippet': 'warn',
      'svelte/no-unused-svelte-ignore': 'warn',
      'svelte/prefer-svelte-reactivity': 'warn',
      'no-useless-escape': 'warn',
      'no-empty': 'warn',
    },
  },
);
