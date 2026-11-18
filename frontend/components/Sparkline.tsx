// A small 30-day trend line. Colour follows the direction of the period (green up, red
// down, or blue/orange in colour-blind mode); the text label carries the same
// information so colour is never the only signal.
export default function Sparkline({ values }: { values?: number[] }) {
  if (!values || values.length < 2) return <span className="muted">{"—"}</span>;
  const W = 96, H = 28, PAD = 3;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (values.length - 1);
  const y = (v: number) => H - PAD - ((v - min) * (H - 2 * PAD)) / span;
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const change = ((values[values.length - 1] - values[0]) / values[0]) * 100;
  const up = change >= 0;
  const label = `30-day trend: ${up ? "up" : "down"} ${Math.abs(change).toFixed(1)}%`;
  return (
    <svg className={`spark ${up ? "up" : "down"}`} width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <title>{label}</title>
      <polyline points={pts} fill="none" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r="3" />
    </svg>
  );
}
