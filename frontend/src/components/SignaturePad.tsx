// The one finger / mouse signature pad of every signing page: the owner's /sign/<token>, the contract /esign/<token>,
// the agent's NDA /nda/<token> and the company signature in Управление → NDA.
import { useEffect, useRef } from 'react';
import { Button } from './ui';

export function SignaturePad({ onInk, padRef, clearLabel }: { onInk: (v: boolean) => void; padRef: React.RefObject<HTMLCanvasElement>; clearLabel: string }) {
  const last = useRef<[number, number] | null>(null);
  // where the pad stood on screen when the stroke began, and what scrolls it: content above it that settles meanwhile
  // (the owner page's registry list, a «saved» note…) would move it under the finger — the scroll takes it back
  const hold = useRef<{ top: number; box: Element | null } | null>(null);
  const inked = useRef(false);
  // the bitmap follows the canvas's real size: sized again before the first stroke (it may have mounted hidden or
  // before layout, or the phone was turned); strokes map CSS pixels onto whatever bitmap there is
  const fit = (force = false) => {
    const c = padRef.current!;
    const r = c.getBoundingClientRect(), k = window.devicePixelRatio || 1;
    const w = Math.round(r.width * k), h = Math.round(r.height * k);
    if (w > 0 && h > 0 && (force || (!inked.current && (c.width !== w || c.height !== h)))) { c.width = w; c.height = h; }
    const ctx = c.getContext('2d')!;
    ctx.setTransform(c.width / (r.width || 1), 0, 0, c.height / (r.height || 1), 0, 0);
    ctx.lineWidth = 2.5; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#1a1f2b';
    return ctx;
  };
  useEffect(() => {
    fit(true);
    // iPhone (Safari and in-app browsers — Instagram, Telegram): touch-action alone doesn't stop the page from scrolling
    // or the browser's swipe gestures under the finger, which cancels the stroke after a few millimetres
    const c = padRef.current!;
    const stop = (e: TouchEvent) => { if (e.cancelable) e.preventDefault(); };
    c.addEventListener('touchstart', stop, { passive: false });
    c.addEventListener('touchmove', stop, { passive: false });
    return () => { c.removeEventListener('touchstart', stop); c.removeEventListener('touchmove', stop); };
  }, [padRef]);  // eslint-disable-line react-hooks/exhaustive-deps
  const at = (e: React.PointerEvent): [number, number] => {
    const r = padRef.current!.getBoundingClientRect(), h = hold.current, d = h ? r.top - h.top : 0;
    if (Math.abs(d) > 0.5) (h!.box || window).scrollBy({ top: d, behavior: 'instant' });
    return [e.clientX - r.left, e.clientY - r.top + d];
  };
  const start = (e: React.PointerEvent) => {
    const c = e.currentTarget;
    try { c.setPointerCapture(e.pointerId); } catch { /* not capturable */ }
    // an open keyboard (the phone field just above) pans the page on its own while it stays up
    if (document.activeElement instanceof HTMLElement && document.activeElement !== document.body) document.activeElement.blur();
    let box: Element | null = c.parentElement;
    while (box && !(/(auto|scroll)/.test(getComputedStyle(box).overflowY) && box.scrollHeight > box.clientHeight)) box = box.parentElement;
    hold.current = { top: c.getBoundingClientRect().top, box };
    fit(); last.current = at(e);
  };
  const end = () => { last.current = null; hold.current = null; };
  const move = (e: React.PointerEvent) => {
    if (!last.current) return;
    const ctx = fit(), p = at(e);
    ctx.beginPath(); ctx.moveTo(...last.current); ctx.lineTo(...p); ctx.stroke();
    last.current = p;
    if (!inked.current) { inked.current = true; onInk(true); }  // not a page re-render per move
  };
  const clear = () => { const c = padRef.current!; c.getContext('2d')!.clearRect(0, 0, c.width, c.height); inked.current = false; onInk(false); };
  return (
    <div className="col gap-sm">
      <canvas ref={padRef} style={{ width: '100%', height: 180, border: '1.5px dashed var(--line, #c9d1e0)', borderRadius: 12, touchAction: 'none', background: '#fff', userSelect: 'none', WebkitUserSelect: 'none', overscrollBehavior: 'contain' }}
        onPointerDown={start} onPointerMove={move} onPointerUp={end} onPointerCancel={end} />
      <Button variant="secondary" size="sm" onClick={clear}>{clearLabel}</Button>
    </div>
  );
}

/** The drawn signature cropped to its ink (+ a small margin), transparent PNG at 1x CSS scale, at most 600 px wide:
 * a few KB. At the phone's devicePixelRatio (3 on Android) it was ~9x the pixels: a body that stalled on mobile data (11-18). */
export function signaturePng(c: HTMLCanvasElement): string {
  const { width: w, height: h } = c;
  const px = c.getContext('2d')!.getImageData(0, 0, w, h).data;
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (px[(y * w + x) * 4 + 3] > 0) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  }
  if (x1 < 0) return c.toDataURL('image/png');
  const dpr = window.devicePixelRatio || 1, m = Math.round(6 * dpr);
  x0 = Math.max(0, x0 - m); y0 = Math.max(0, y0 - m); x1 = Math.min(w - 1, x1 + m); y1 = Math.min(h - 1, y1 + m);
  const cw = x1 - x0 + 1, ch = y1 - y0 + 1, k = Math.min(1 / dpr, 600 / cw);
  const out = document.createElement('canvas');
  out.width = Math.max(1, Math.round(cw * k)); out.height = Math.max(1, Math.round(ch * k));
  const o = out.getContext('2d')!;
  o.drawImage(c, x0, y0, cw, ch, 0, 0, out.width, out.height);
  // the ink colour and 4 alpha levels: the downscale's antialiasing otherwise leaves hundreds of shades that PNG can't pack
  const im = o.getImageData(0, 0, out.width, out.height), d = im.data;
  for (let i = 0; i < d.length; i += 4) { d[i] = 0x1a; d[i + 1] = 0x1f; d[i + 2] = 0x2b; d[i + 3] = Math.round(d[i + 3] / 85) * 85; }
  o.putImageData(im, 0, 0);
  return out.toDataURL('image/png');
}
