// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import Link from 'next/link';
import { Empty } from '@/components/Empty';
import { getRequest } from '@/lib/server';

export default async function NotFound() {
  const { fmt } = await getRequest();
  return (
    <section className="container page-pad">
      <Empty title={fmt.t('nf.title')}><Link className="btn btn-primary" href="/">{fmt.t('nf.home')}</Link></Empty>
    </section>
  );
}
