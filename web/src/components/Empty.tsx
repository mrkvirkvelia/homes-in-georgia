// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
import { Icon } from './Icon';

export function Empty({ title, text, children }: { title: string; text?: string; children?: React.ReactNode }) {
  return (
    <div className="empty"><div className="empty-ico"><Icon name="search" /></div><h3>{title}</h3><p>{text}</p>{children}</div>
  );
}

export function Skeletons({ n }: { n: number }) {
  return Array.from({ length: n }, (_, i) => <div key={i} className="card skeleton"><div className="card-media" /><div className="card-body"><i /><i /><i /></div></div>);
}

/** First load of a list that needs the browser (saved listings): placeholder cards instead of an empty page. */
export function LoadingView({ text }: { text: string }) {
  return <div className="container page-pad" aria-busy="true"><p className="loading-line" role="status">{text}</p><div className="grid"><Skeletons n={6} /></div></div>;
}
