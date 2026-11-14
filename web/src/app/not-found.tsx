// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import LegacyView from '@/components/LegacyView';
import { loadRequest, applyRequest } from '@/lib/server';
import { notFoundMarkup } from '@/legacy/pages/misc.js';

export default async function NotFound() {
  applyRequest(await loadRequest());
  return <LegacyView kind="notfound" html={notFoundMarkup()} />;
}
