// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
import { useRouter } from 'next/navigation';
import { Empty } from './Empty';
import { useFmt } from './Providers';

/** The feed could not be loaded: a message and a retry button (draws the page again). `onRetry` replaces the default. */
export default function ErrorView({ onRetry }: { onRetry?: () => void }) {
  const { t } = useFmt();
  const router = useRouter();
  return (
    <div className="container page-pad">
      <Empty title={t('error.t')} text={t('error')}>
        <button type="button" className="btn btn-primary" onClick={onRetry ?? (() => router.refresh())}>{t('retry')}</button>
      </Empty>
    </div>
  );
}
