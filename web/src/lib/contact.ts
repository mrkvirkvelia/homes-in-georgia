// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
/** «Contact us» leads to the contact block at the bottom of the page. Lists may still grow while the page settles, so aim again a few times. */
export function showContact() {
  const aim = () => document.getElementById('contact')?.scrollIntoView({ behavior: 'auto', block: 'start' });
  aim();
  [120, 300, 600].forEach(ms => setTimeout(aim, ms));
}
