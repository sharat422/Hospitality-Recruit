module.exports = {
  root: true,
  env: { browser: true, es2021: true },
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint'],
  extends: ['eslint:recommended'],
  ignorePatterns: ['dist', 'coverage', '*.config.*', '*.d.ts'],
  rules: {
    // TypeScript checks these with full type information in npm run type-check.
    'no-undef': 'off',
    'no-redeclare': 'off',
    '@typescript-eslint/no-redeclare': ['error', { builtinGlobals: false }],
    'no-unused-vars': 'off',
  },
};
