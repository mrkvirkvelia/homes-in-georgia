// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import { ICON_PATHS } from './icon-paths';
import { BRAND_PATHS } from './brand-paths';

const inner = (name: string) => ICON_PATHS[name] || ICON_PATHS.sparkles;

export function Icon({ name, className = '' }: { name: string; className?: string }) {
  return <svg className={`i ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{ __html: inner(name) }} />;
}

/** The same icon as an HTML string, for Leaflet marker icons. */
export const iconHtml = (name: string) =>
  `<svg class="i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner(name)}</svg>`;

/** A service logo (Telegram, Instagram…) on its own 24px grid; unknown names fall back to a stroke icon. */
export function BrandMark({ name }: { name: string }) {
  const path = BRAND_PATHS[name];
  if (!path) return <Icon name={name === 'tel' ? 'phone' : name} />;
  return <svg className="i" viewBox="0 0 24 24" aria-hidden="true" dangerouslySetInnerHTML={{ __html: path }} />;
}
export const hasBrand = (name: string) => name in BRAND_PATHS;

// Vector logo traced from the brand files (public/assets/img/brand/).
export const logoSrc = (light = false) => `/assets/img/brand/${light ? 'logo-white' : 'logo'}.svg`;
export function Logo({ className = '' }: { className?: string }) {
  return <img className={`logo ${className}`} src={logoSrc(className.includes('logo-light'))} alt="Homes in Georgia" width={132} height={40} />;
}
