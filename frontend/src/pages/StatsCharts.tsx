// Charts + month picker for «Аналитика» → «Бизнес» (Stanislav 11-14): plain SVG/CSS, no chart library in the app.
// Which chart = which block of David's workbook: docs/STATS-BLOCKS.md («Charts»).
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const ym = (y: number, m: number) => `${y}-${String(m).padStart(2, '0')}`;

/** «‹ Ноябрь 2026 ›»; the label opens a 3×4 grid of months with a year switch. Months after `max` are disabled. */
export function MonthPicker({ value, max, onChange }: { value: string; max: string; onChange: (v: string) => void }) {
  const [y, m] = value.split('-').map(Number);
  const [open, setOpen] = useState(false);
  const [year, setYear] = useState(y);
  const maxY = Number(max.slice(0, 4));
  const shift = (d: number) => { const k = y * 12 + m - 1 + d; const v = ym(Math.floor(k / 12), (k % 12) + 1); if (v <= max) onChange(v); };
  return (
    <div className="mp">
      <button type="button" className="mp-arrow" aria-label="Предыдущий месяц" onClick={() => shift(-1)}><ChevronLeft size={18} /></button>
      <button type="button" className="mp-label" aria-haspopup="dialog" aria-expanded={open} onClick={() => { setYear(y); setOpen(!open); }}>
        {MONTHS[m - 1]} {y}
      </button>
      <button type="button" className="mp-arrow" aria-label="Следующий месяц" disabled={value >= max} onClick={() => shift(1)}><ChevronRight size={18} /></button>
      {open && <>
        <div className="mp-backdrop" onClick={() => setOpen(false)} />
        <div className="mp-pop" role="dialog" aria-label="Выбор месяца">
          <div className="mp-year">
            <button type="button" className="mp-arrow" aria-label="Предыдущий год" onClick={() => setYear(year - 1)}><ChevronLeft size={18} /></button>
            <b>{year}</b>
            <button type="button" className="mp-arrow" aria-label="Следующий год" disabled={year >= maxY} onClick={() => setYear(year + 1)}><ChevronRight size={18} /></button>
          </div>
          <div className="mp-grid">
            {MONTHS.map((name, i) => { const v = ym(year, i + 1); return (
              <button key={v} type="button" disabled={v > max} className={v === value ? 'active' : ''} onClick={() => { onChange(v); setOpen(false); }}>{name.slice(0, 3)}</button>
            ); })}
          </div>
        </div>
      </>}
    </div>
  );
}

export type Series = { label: string; color: string };
export const C = { brand: 'var(--brand)', accent: 'var(--accent)', ok: 'var(--ok)', warn: 'var(--warn)', sky: '#7A9CC6', faint: 'var(--faint)' };
const PALETTE = [C.brand, C.accent, C.ok, C.warn, C.sky, C.faint];

export function Legend({ series }: { series: Series[] }) {
  return <div className="ch-legend">{series.map((s) => <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>)}</div>;
}

/** Column chart, one column per row; several values per row are stacked (bottom first). The total sits on top. */
export function Columns({ rows, series, fmt }: { rows: { k: string; v: number[] }[]; series: Series[]; fmt: (v: number) => string }) {
  const sum = (r: { v: number[] }) => r.v.reduce((a, b) => a + b, 0);
  const max = Math.max(1, ...rows.map(sum));
  return (
    <div className="table-wrap"><div style={{ minWidth: 560 }}>{/* 12 columns don't fit 375 px: scroll inside the card */}
      <div className="vbars" role="img" aria-label={rows.map((r) => `${r.k} ${fmt(sum(r))}`).join(', ')}>
        {rows.map((r) => (
          <div key={r.k} className="vbar" title={`${r.k}: ${series.map((s, i) => `${s.label} ${fmt(r.v[i] || 0)}`).join(' · ')}`}>
            {sum(r) > 0 && <em>{fmt(sum(r))}</em>}
            <div className="ch-stack" style={{ height: `${(sum(r) / max) * 100}%` }}>
              {[...r.v].map((v, i) => ({ v, i })).reverse().map(({ v, i }) => v > 0 && <span key={i} style={{ flexGrow: v, background: series[i].color }} />)}
            </div>
            <span>{r.k}</span>
          </div>
        ))}
      </div>
    </div></div>
  );
}

/** Line chart over months (the workbook's «Medium Price $$» charts). Zero = no data: the line skips it. */
export function Lines({ keys, lines, fmt }: { keys: string[]; lines: (Series & { v: number[] })[]; fmt: (v: number) => string }) {
  // drawn at the card's real width (min 640, scrolls on a phone) so the labels stay 11 px instead of scaling with a viewBox
  const [w, setW] = useState(760);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const W = Math.max(640, w), H = 220, L = 52, B = 26, T = 14;
  const all = lines.flatMap((l) => l.v).filter((v) => v > 0);
  if (!all.length) return <div className="muted" ref={box} style={{ padding: 12 }}>Нет данных</div>;
  const hi = Math.max(...all) * 1.1, lo = Math.min(...all) * 0.85;
  const x = (i: number) => L + ((W - L - 30) * i) / Math.max(1, keys.length - 1);
  const yy = (v: number) => T + (H - T - B) * (1 - (v - lo) / (hi - lo || 1));
  const ticks = [lo, (lo + hi) / 2, hi];
  return (
    <div className="table-wrap" ref={box}><svg width={W} height={H} style={{ display: 'block' }} role="img"
      aria-label={lines.map((l) => `${l.label}: ${l.v.map(fmt).join(', ')}`).join('; ')}>
      {ticks.map((t) => <g key={t}><line x1={L} x2={W - 4} y1={yy(t)} y2={yy(t)} stroke="var(--line)" />
        <text x={L - 6} y={yy(t) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{fmt(Math.round(t))}</text></g>)}
      {keys.map((k, i) => <text key={k} x={x(i)} y={H - 6} textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--muted)">{k}</text>)}
      {lines.map((l) => {
        const pts = l.v.map((v, i) => (v > 0 ? `${x(i)},${yy(v)}` : null));
        const path = pts.reduce<string>((d, p, i) => (p ? `${d}${d && pts[i - 1] ? ' L' : ' M'}${p}` : d), '');
        return <g key={l.label}>
          <path d={path} fill="none" stroke={l.color} strokeWidth="2.5" strokeLinejoin="round" />
          {l.v.map((v, i) => v > 0 && <circle key={i} cx={x(i)} cy={yy(v)} r="3.5" fill="var(--surface)" stroke={l.color} strokeWidth="2"><title>{`${keys[i]} · ${l.label}: ${fmt(v)}`}</title></circle>)}
        </g>;
      })}
    </svg></div>
  );
}

/** Donut + legend with shares (client sources). Small slices past the 5th go to «Другое». */
export function Donut({ rows }: { rows: { k: string; v: number }[] }) {
  const sorted = [...rows].sort((a, b) => b.v - a.v);
  const top = sorted.slice(0, 5), rest = sorted.slice(5).reduce((t, r) => t + r.v, 0);
  const parts = rest ? [...top, { k: 'Другое', v: rest }] : top;
  const total = parts.reduce((t, r) => t + r.v, 0);
  if (!total) return <div className="muted">Нет данных</div>;
  const R = 52, len = 2 * Math.PI * R;
  let at = 0;
  return (
    <div className="ch-donut">
      <svg viewBox="0 0 140 140" width="140" height="140" role="img" aria-label={parts.map((p) => `${p.k} ${p.v}`).join(', ')}>
        <g transform="rotate(-90 70 70)">
          {parts.map((p, i) => { const d = (p.v / total) * len; const el = (
            <circle key={p.k} cx="70" cy="70" r={R} fill="none" stroke={PALETTE[i % PALETTE.length]} strokeWidth="22"
              strokeDasharray={`${d} ${len - d}`} strokeDashoffset={-at}><title>{`${p.k}: ${p.v}`}</title></circle>); at += d; return el; })}
        </g>
        <text x="70" y="68" textAnchor="middle" fontSize="20" fontWeight="800" fill="var(--ink)">{total}</text>
        <text x="70" y="86" textAnchor="middle" fontSize="10" fill="var(--muted)">клиентов</text>
      </svg>
      <div className="ch-donut-list">
        {parts.map((p, i) => (
          <div key={p.k}><i style={{ background: PALETTE[i % PALETTE.length] }} /><span className="ellipsis">{p.k}</span>
            <b className="num">{p.v}</b><span className="muted num">{Math.round((p.v / total) * 100)}%</span></div>
        ))}
      </div>
    </div>
  );
}

/** Horizontal stacked bars per agent (cash-in = agent + platform), fits a phone. */
export function HStack({ rows, series, fmt }: { rows: { k: string; v: number[]; sub?: string }[]; series: Series[]; fmt: (v: number) => string }) {
  const sum = (r: { v: number[] }) => r.v.reduce((a, b) => a + b, 0);
  const max = Math.max(1, ...rows.map(sum));
  return (
    <div className="bars">
      {rows.map((r) => (
        <div key={r.k} className="bar-row" title={`${r.k}: ${series.map((s, i) => `${s.label} ${fmt(r.v[i] || 0)}`).join(' · ')}`}>
          <span className="ellipsis" style={{ fontWeight: 600 }}>{r.k}</span>
          <div className="bar-track ch-hstack"><div style={{ width: `${(sum(r) / max) * 100}%` }}>
            {r.v.map((v, i) => v > 0 && <span key={i} style={{ flexGrow: v, background: series[i].color }} />)}
          </div></div>
          <span className="num muted nowrap" style={{ fontSize: 12 }}><b style={{ color: 'var(--ink)' }}>{fmt(sum(r))}</b>{r.sub ? ` · ${r.sub}` : ''}</span>
        </div>
      ))}
    </div>
  );
}

/** The numbers under a chart, folded by default. */
export function Fold({ title = 'Таблица', children }: { title?: string; children: ReactNode }) {
  return <details className="ch-fold"><summary>{title}</summary>{children}</details>;
}
