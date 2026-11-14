// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
/** 640 px preview of a CRM photo (cards, rails, map); the full size is used in the gallery. */
export const thumb = (src: string) => (String(src).startsWith('/api/public/') ? src + '?p=1' : src);
