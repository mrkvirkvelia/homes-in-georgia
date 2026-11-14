import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTs from 'eslint-config-next/typescript';

const config = [
  ...nextVitals,
  ...nextTs,
  // Photos come from the CRM as relative URLs with their own 640 px preview (?p=1): plain <img> on purpose.
  { rules: { '@next/next/no-img-element': 'off' } },
  { ignores: ['.next/**', 'scripts/**', 'next-env.d.ts'] },
];
export default config;
