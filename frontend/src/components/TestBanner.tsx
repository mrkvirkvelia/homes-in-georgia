// The test server (backend TEST_MODE, deploy/test-push.sh): a fixed strip on every page so it is never mistaken for
// the working CRM. Demo data only; Telegram is switched off there.
import { useQuery } from '@tanstack/react-query';
import { api } from '../api';

export function TestBanner() {
  const q = useQuery({ queryKey: ['app-config'], queryFn: api.config, staleTime: Infinity, retry: false });
  if (!q.data?.test_mode) return null;
  return (
    <div role="note" style={{
      position: 'fixed', top: 0, left: '50%', transform: 'translateX(-50%)', zIndex: 10000, pointerEvents: 'none',
      background: '#E8A317', color: '#1a1f2b', font: '700 11px/1 Montserrat, Arial, sans-serif', letterSpacing: '.08em',
      padding: '4px 12px', borderRadius: '0 0 8px 8px', boxShadow: '0 2px 6px rgba(0,0,0,.2)', whiteSpace: 'nowrap',
    }}>
      ТЕСТ · выдуманные данные
    </div>
  );
}
