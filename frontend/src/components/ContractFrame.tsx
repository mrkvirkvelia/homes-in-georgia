// The contract / NDA text on its signing page (/esign/<token>, /nda/<token>).
import { useEffect, useRef, useState } from 'react';

/** The contract as stored (cleaned server-side), in a sandboxed frame — no scripts; sized once to its content.
 *  (Measured from the body, not the frame's own viewport: that grows with the frame and never settles.)
 *  col: a two-column (Georgian | second language) document on a phone shows only that column, not the two interleaved. */
export function ContractFrame({ html, col }: { html: string; col?: 1 | 2 }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [h, setH] = useState(600);
  const fit = () => {
    const d = ref.current?.contentDocument;
    if (!d?.body) return;
    const want = Math.ceil(d.body.getBoundingClientRect().height) + 24;  // + the body padding
    setH((x) => (Math.abs(x - want) > 4 ? want : x));
  };
  useEffect(() => {
    // fonts / images settle shortly after load; then the frame keeps its size (nothing moves under the finger)
    const ids = [300, 1000, 2500].map((t) => setTimeout(fit, t));
    return () => ids.forEach(clearTimeout);
  }, [html, col]);  // eslint-disable-line react-hooks/exhaustive-deps
  const one = col ? `@media (max-width:700px){.cols>tbody>tr>td:nth-child(${3 - col}):not([colspan]){display:none}}` : '';
  const doc = html.replace('</head>', `<style>html,body{height:auto!important}body{margin:0;padding:12px;background:#fff;color:#111;overflow-x:hidden}.cd-p{overflow-wrap:anywhere}${one}</style></head>`);
  return <iframe ref={ref} title="contract" srcDoc={doc} sandbox="allow-same-origin" onLoad={fit} scrolling="no"
    style={{ width: '100%', height: h, border: '1px solid var(--line, #dfe4ee)', borderRadius: 12, background: '#fff', display: 'block' }} />;
}
