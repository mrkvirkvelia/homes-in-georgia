import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';

// src/legacy is the old site's modules ported as they are (plain JS, string templates): not linted, only built.
const config = [...nextVitals, ...nextTs, { ignores: ['src/legacy/**', '.next/**', 'scripts/**', 'next-env.d.ts'] }];
export default config;
