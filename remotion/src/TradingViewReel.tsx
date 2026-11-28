import React, { useEffect, useRef, useState } from 'react';
import {
  AbsoluteFill,
  Audio,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from 'remotion';
import { createChart, ColorType, CrosshairMode, IChartApi, ISeriesApi } from 'lightweight-charts';

export interface CandleItem {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface CaptionItem {
  word: string;
  start: number;
  end: number;
}

export interface ReelProps {
  session: string;
  hookTitle: string;
  durationSec: number;
  stageTimes: number[];
  smc: any;
  chartFocus?: {
    highlight_asia?: boolean;
    highlight_fvg?: boolean;
    show_rr_box?: boolean;
    callout_label?: string;
  };
  candles15m: CandleItem[];
  candles5m: CandleItem[];
  captions: CaptionItem[];
}

export const TradingViewReel: React.FC<ReelProps> = ({
  session,
  hookTitle,
  durationSec,
  stageTimes,
  smc,
  chartFocus,
  candles15m,
  candles5m,
  captions,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const [zoneCoords, setZoneCoords] = useState<Record<string, number | null>>({});

  const [t2 = 6, t3 = 13, t4 = 20, t5 = 25] = stageTimes;
  const stage = t >= t5 ? 5 : t >= t4 ? 4 : t >= t3 ? 3 : t >= t2 ? 2 : 1;

  const tickPulse = Math.sin(frame * 0.22) * 0.32;
  const activeCandles = stage >= 5 && candles5m.length > 0 ? candles5m : candles15m;
  useEffect(() => {
    if (!chartContainerRef.current) return;
    chartContainerRef.current.innerHTML = '';

    const chart = createChart(chartContainerRef.current, {
      width: 1064,
      height: 1000,
      layout: {
        background: { type: ColorType.Solid, color: '#131722' },
        textColor: '#cbd5e1',
        fontSize: 21,
      },
      grid: {
        vertLines: { color: '#1e222d' },
        horzLines: { color: '#1e222d' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: '#2a2e39',
        scaleMargins: { top: 0.14, bottom: 0.14 },
      },
      timeScale: {
        borderColor: '#2a2e39',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12,
        barSpacing: 22,
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: '#089981',
      downColor: '#f23645',
      borderVisible: false,
      wickUpColor: '#089981',
      wickDownColor: '#f23645',
    });

    chartRef.current = chart;
    seriesRef.current = series;

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [stage >= 5]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series || activeCandles.length === 0) return;

    const visibleCount =
      stage === 1
        ? Math.max(activeCandles.length - 6 + Math.min(6, Math.floor((t / Math.max(t2, 1)) * 7)), 14)
        : activeCandles.length;

    const sliced = activeCandles.slice(0, visibleCount).map((c, idx, arr) => {
      if (idx === arr.length - 1) {
        const pulsedClose = Number((c.close + tickPulse).toFixed(2));
        return {
          ...c,
          close: pulsedClose,
          high: Math.max(c.high, pulsedClose),
          low: Math.min(c.low, pulsedClose),
        };
      }
      return c;
    });

    series.setData(sliced as any);

    const toY = (price: any) => (price != null ? series.priceToCoordinate(Number(price)) : null);
    setZoneCoords({
      asiaHigh: toY(smc.asia_high),
      asiaLow: toY(smc.asia_low),
      supHigh: toY(smc.supply_high),
      supLow: toY(smc.supply_low),
      demHigh: toY(smc.demand_high),
      demLow: toY(smc.demand_low),
      watchHigh: toY(smc.watch_high),
      watchLow: toY(smc.watch_low),
      entry: toY(smc.trade_setup?.entry),
      sl: toY(smc.trade_setup?.sl),
      tp: toY(smc.trade_setup?.tp),
    });
  }, [stage, Math.floor(frame / 2)]);
  const stageStartFrame =
    stage === 5 ? t5 * fps : stage === 4 ? t4 * fps : stage === 3 ? t3 * fps : stage === 2 ? t2 * fps : 0;
  const wipeProgress = spring({ frame: frame - stageStartFrame, fps, config: { damping: 16, stiffness: 110 } });

  const cursorX = interpolate(wipeProgress, [0, 1], [180, 760]);
  const cursorY =
    stage >= 5 && zoneCoords.entry != null
      ? zoneCoords.entry
      : stage >= 4 && zoneCoords.watchHigh != null
      ? zoneCoords.watchHigh
      : stage === 3 && zoneCoords.demLow != null
      ? zoneCoords.demLow
      : zoneCoords.supHigh ?? 360;

  const sortedCaptions = [...captions].sort((a, b) => a.start - b.start);
  const foundIdx = sortedCaptions.findIndex((c) => t >= c.start && t <= c.end + 0.12);
  const activeChunkIdx = foundIdx >= 0 ? Math.floor(foundIdx / 3) : -1;
  const currentChunk = activeChunkIdx >= 0 ? sortedCaptions.slice(activeChunkIdx * 3, activeChunkIdx * 3 + 3) : [];
  const lastCandle = activeCandles[activeCandles.length - 1];
  const calloutBadge = chartFocus?.callout_label || 'LIQUIDITY MAP';

  return (
    <AbsoluteFill style={{ backgroundColor: '#0b0e14', fontFamily: 'sans-serif' }}>
      <Audio src={staticFile('voiceover.mp3')} />

      <div style={{ position: 'absolute', top: 136, left: 16, right: 16, display: 'flex', justifyContent: 'center', zIndex: 10 }}>
        <div
          style={{
            backgroundColor: '#181c27',
            border: '3px solid #facc15',
            borderRadius: 18,
            padding: '12px 34px',
            color: '#facc15',
            fontSize: 42,
            fontWeight: 900,
            letterSpacing: 0.8,
            textAlign: 'center',
          }}
        >
          {hookTitle}
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          top: 228,
          left: 16,
          right: 16,
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 24,
          fontWeight: 800,
        }}
      >
        <span style={{ color: '#94a3b8' }}>{session} • {smc.bias_label}</span>
        <span style={{ color: '#38bdf8' }}>XAUUSD ${(Number(smc.live_price) + tickPulse).toFixed(2)}</span>
      </div>

      <div
        style={{
          position: 'absolute',
          top: 268,
          left: 8,
          width: 1064,
          height: 1054,
          borderRadius: 16,
          border: '2px solid #2a2e39',
          backgroundColor: '#131722',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: 52,
            padding: '0 18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #2a2e39',
            fontSize: 21,
            fontWeight: 800,
          }}
        >
          <span style={{ color: '#d1d4dc' }}>🟡 XAUUSD · {stage >= 5 ? '5m' : '15m'} · EXNESS</span>
          {lastCandle && (
            <span style={{ color: lastCandle.close >= lastCandle.open ? '#089981' : '#f23645' }}>
              O{lastCandle.open.toFixed(1)} H{lastCandle.high.toFixed(1)} L{lastCandle.low.toFixed(1)} C{(lastCandle.close + tickPulse).toFixed(1)}
            </span>
          )}
        </div>

        <div style={{ position: 'relative', width: 1064, height: 1000 }}>
          <div ref={chartContainerRef} />

          <svg
            width={960}
            height={1000}
            style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none', zIndex: 6 }}
          >
            {zoneCoords.asiaHigh != null && zoneCoords.asiaLow != null && (
              <g>
                <rect
                  x={40}
                  y={Math.min(zoneCoords.asiaHigh, zoneCoords.asiaLow)}
                  width={380}
                  height={Math.max(Math.abs(zoneCoords.asiaLow - zoneCoords.asiaHigh), 18)}
                  fill="rgba(99, 102, 241, 0.14)"
                  stroke="#818cf8"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                />
                <text x={50} y={Math.min(zoneCoords.asiaHigh, zoneCoords.asiaLow) - 8} fill="#818cf8" fontSize={18} fontWeight="bold">
                  ASIA RANGE (${smc.asia_low}–${smc.asia_high})
                </text>
              </g>
            )}

            {stage >= 2 && zoneCoords.supHigh != null && zoneCoords.supLow != null && (
              <g>
                <rect
                  x={0}
                  y={Math.min(zoneCoords.supHigh, zoneCoords.supLow)}
                  width={950 * wipeProgress}
                  height={Math.max(Math.abs(zoneCoords.supLow - zoneCoords.supHigh), 24)}
                  fill="rgba(242, 54, 69, 0.22)"
                  stroke="#f23645"
                  strokeWidth={2}
                />
                <text x={20} y={Math.min(zoneCoords.supHigh, zoneCoords.supLow) - 8} fill="#f87171" fontSize={19} fontWeight="bold">
                  SUPPLY / BSL (${smc.supply_low}–${smc.supply_high})
                </text>
              </g>
            )}

            {stage >= 3 && zoneCoords.demHigh != null && zoneCoords.demLow != null && (
              <g>
                <rect
                  x={0}
                  y={Math.min(zoneCoords.demHigh, zoneCoords.demLow)}
                  width={950 * wipeProgress}
                  height={Math.max(Math.abs(zoneCoords.demLow - zoneCoords.demHigh), 24)}
                  fill="rgba(8, 153, 129, 0.22)"
                  stroke="#089981"
                  strokeWidth={2}
                />
                <text x={20} y={Math.max(zoneCoords.demHigh, zoneCoords.demLow) + 22} fill="#34d399" fontSize={19} fontWeight="bold">
                  DEMAND / SSL (${smc.demand_low}–${smc.demand_high})
                </text>
              </g>
            )}

            {stage >= 4 && zoneCoords.watchHigh != null && zoneCoords.watchLow != null && (
              <g>
                <rect
                  x={440}
                  y={Math.min(zoneCoords.watchHigh, zoneCoords.watchLow)}
                  width={510 * wipeProgress}
                  height={Math.max(Math.abs(zoneCoords.watchLow - zoneCoords.watchHigh), 28)}
                  fill="rgba(250, 204, 21, 0.24)"
                  stroke="#facc15"
                  strokeWidth={2.5}
                />
                <text x={455} y={Math.min(zoneCoords.watchHigh, zoneCoords.watchLow) - 8} fill="#facc15" fontSize={20} fontWeight="bold">
                  🎯 {calloutBadge} (${smc.watch_low}–${smc.watch_high})
                </text>
              </g>
            )}

            {stage >= 5 && zoneCoords.entry != null && zoneCoords.sl != null && zoneCoords.tp != null && (
              <g>
                <rect
                  x={690}
                  y={Math.min(zoneCoords.entry, zoneCoords.tp)}
                  width={230 * wipeProgress}
                  height={Math.max(Math.abs(zoneCoords.tp - zoneCoords.entry), 24)}
                  fill="rgba(8, 153, 129, 0.30)"
                  stroke="#089981"
                  strokeWidth={2}
                />
                <rect
                  x={690}
                  y={Math.min(zoneCoords.entry, zoneCoords.sl)}
                  width={230 * wipeProgress}
                  height={Math.max(Math.abs(zoneCoords.sl - zoneCoords.entry), 18)}
                  fill="rgba(242, 54, 69, 0.30)"
                  stroke="#f23645"
                  strokeWidth={2}
                />
                <rect x={695} y={zoneCoords.entry - 18} width={220} height={36} rx={8} fill="#1e293b" stroke="#38bdf8" strokeWidth={2} />
                <text x={805} y={zoneCoords.entry + 6} textAnchor="middle" fill="#ffffff" fontSize={18} fontWeight="bold">
                  {smc.trade_setup?.direction} • 1:{smc.trade_setup?.rr} R:R
                </text>
              </g>
            )}

            <line x1={0} y1={cursorY} x2={960} y2={cursorY} stroke="rgba(255,255,255,0.22)" strokeDasharray="4 4" />
            <line x1={cursorX} y1={0} x2={cursorX} y2={1000} stroke="rgba(255,255,255,0.22)" strokeDasharray="4 4" />
            <polygon
              points={`${cursorX},${cursorY} ${cursorX},${cursorY + 26} ${cursorX + 8},${cursorY + 20} ${cursorX + 18},${cursorY + 18}`}
              fill="#ffffff"
              stroke="#0b0e14"
              strokeWidth={2}
            />
          </svg>
        </div>
      </div>

      <div style={{ position: 'absolute', top: 1332, left: 8, width: 1064, height: 8, backgroundColor: '#1e222d', borderRadius: 4 }}>
        <div style={{ width: `${Math.min(100, (t / durationSec) * 100)}%`, height: '100%', backgroundColor: '#facc15', borderRadius: 4 }} />
      </div>

      {currentChunk.length > 0 && (
        <div style={{ position: 'absolute', top: 1354, left: 20, right: 20, display: 'flex', justifyContent: 'center', zIndex: 15 }}>
          <div
            style={{
              backgroundColor: 'rgba(10, 14, 23, 0.96)',
              border: '3px solid #facc15',
              borderRadius: 18,
              padding: '14px 30px',
              display: 'flex',
              gap: 16,
              flexWrap: 'wrap',
              justifyContent: 'center',
            }}
          >
            {currentChunk.map((w, idx) => {
              const active = t >= w.start && t <= w.end + 0.1;
              const pop = spring({ frame: frame - w.start * fps, fps, config: { damping: 14 } });
              return (
                <span
                  key={idx}
                  style={{
                    fontSize: 46,
                    fontWeight: 900,
                    color: active ? '#facc15' : '#ffffff',
                    transform: active ? `scale(${1 + pop * 0.06})` : 'scale(1)',
                  }}
                >
                  {w.word.toUpperCase()}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};
