// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import type { NextConfig } from 'next';

const API_URL = process.env.API_URL || 'http://api:8000';

const config: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  async redirects() {
    return [
      // Old OG preview pages: the listing page itself now carries the preview.
      { source: '/share/:id.html', destination: '/listing/:id', statusCode: 301 },
    ];
  },
  // Production: Caddy serves /api/public/* from the CRM on the same domain. Local dev: proxy it to API_URL.
  async rewrites() {
    return [{ source: '/api/public/:path*', destination: `${API_URL}/api/public/:path*` }];
  },
};

export default config;
