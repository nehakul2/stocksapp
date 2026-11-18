"use client";
import { useEffect, useRef, useState } from "react";
import {
  AreaSeries, CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, createChart,
  type IChartApi, type Time,
} from "lightweight-charts";
import type { Bar } from "@/lib/api";
import { SMA_WINDOWS } from "@/lib/api";
import { fmtNum } from "@/lib/format";

export type ChartType = "Candles" | "Line" | "Area";
export const SMA_VARS: Record<number, string> = { 5: "--s1", 20: "--s2", 50: "--s3", 100: "--s4", 200: "--s5" };

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export default function PriceChart({ bars, type, smas }: { bars: Bar[]; type: ChartType; smas: Record<number, boolean> }) {
  const el = useRef<HTMLDivElement>(null);
  const [theme, setTheme] = useState(0);
  const [hover, setHover] = useState<Bar | null>(null);

  // Rebuild colors when the theme or color-blind setting changes.
  useEffect(() => {
    const mo = new MutationObserver(() => setTheme((n) => n + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-cb"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    if (!el.current || !bars.length) return;
    const ink = css("--ink"), muted = css("--muted"), rule = css("--rule"), paper = css("--paper");
    const up = css("--up-mark"), down = css("--down-mark"), accent = css("--accent");

    const chart: IChartApi = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: paper }, textColor: muted, fontFamily: css("--sans"), fontSize: 12, attributionLogo: false },
      grid: { vertLines: { color: rule }, horzLines: { color: rule } },
      rightPriceScale: { borderColor: rule },
      timeScale: { borderColor: rule, timeVisible: false },
      crosshair: { mode: CrosshairMode.Normal },
    });

    const times = bars.map((b) => b.date as Time);
    let main;
    if (type === "Candles") {
      main = chart.addSeries(CandlestickSeries, { upColor: up, downColor: down, wickUpColor: up, wickDownColor: down, borderVisible: false });
      main.setData(bars.map((b) => ({ time: b.date as Time, open: b.open, high: b.high, low: b.low, close: b.close })));
    } else if (type === "Area") {
      main = chart.addSeries(AreaSeries, { lineColor: accent, topColor: accent + "40", bottomColor: accent + "00", lineWidth: 2 });
      main.setData(bars.map((b) => ({ time: b.date as Time, value: b.close })));
    } else {
      main = chart.addSeries(LineSeries, { color: ink, lineWidth: 2 });
      main.setData(bars.map((b) => ({ time: b.date as Time, value: b.close })));
    }

    const vol = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "", lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("").applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    vol.setData(bars.filter((b) => b.volume != null).map((b) => ({ time: b.date as Time, value: b.volume as number, color: (b.close >= b.open ? up : down) + "66" })));

    for (const w of SMA_WINDOWS) {
      if (!smas[w]) continue;
      const key = `sma_${w}` as const;
      const s = chart.addSeries(LineSeries, { color: css(SMA_VARS[w]), lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: `SMA ${w}`, crosshairMarkerVisible: false });
      s.setData(bars.filter((b) => b[key] != null).map((b) => ({ time: b.date as Time, value: b[key] as number })));
    }

    const byDate = new Map(bars.map((b) => [b.date, b]));
    chart.subscribeCrosshairMove((p) => {
      setHover(typeof p.time === "string" ? byDate.get(p.time) ?? null : null);
    });
    chart.timeScale().fitContent();
    void times;

    return () => chart.remove();
  }, [bars, type, smas, theme]);

  const shown = hover ?? bars[bars.length - 1];
  return (
    <>
      <div className="readout" aria-live="off">
        {shown && (type === "Candles" ? (
          <>
            <span>{shown.date}</span>
            <span>Open <b>{fmtNum(shown.open)}</b></span>
            <span>High <b>{fmtNum(shown.high)}</b></span>
            <span>Low <b>{fmtNum(shown.low)}</b></span>
            <span>Close <b>{fmtNum(shown.close)}</b></span>
            <span>Volume <b>{shown.volume != null ? shown.volume.toLocaleString("en-US") : "—"}</b></span>
          </>
        ) : (
          <>
            <span>{shown.date}</span>
            <span>Close <b>{fmtNum(shown.close)}</b></span>
            <span>Volume <b>{shown.volume != null ? shown.volume.toLocaleString("en-US") : "—"}</b></span>
          </>
        ))}
      </div>
      <div ref={el} className="chartbox" role="img" aria-label={`Price chart, ${bars.length} trading days`} />
    </>
  );
}
