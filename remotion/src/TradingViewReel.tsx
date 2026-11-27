import React, { useEffect, useRef } from 'react';
import {
  AbsoluteFill,
  Audio,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  spring,
} from 'remotion';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';

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
  candles15m,
  candles5m,
  captions,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const chartContainerRef = useRef<HTMLDivElement>(null);

  const [t2 = 6, t3 = 13, t4 = 20, t5 = 25] = stageTimes;
  const stage = t >= t5 ? 5 : t >= t4 ? 4 : t >= t3 ? 3 : t >= t2 ? 2 : 1;

  const tickPulse = Math.sin(frame * 0.25) * 0.35;
  const activeCandles = stage >= 5 && candles5m.length > 0 ? candles5m : candles15m;

  useEffect(() => {
    if (!chartContainerRef.current || activeCandles.length === 0) return;
    chartContainerRef.current.innerHTML = '';

    const chart = createChart(chartContainerRef.current, {
      width: 1064,
      height: 1000,
      layout: {
        background: { type: ColorType.Solid, color: '#131722' },
        textColor: '#cbd5e1',
        fontSize: 22,
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
        rightOffset: 10,
        barSpacing: 20,
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: '#089981',
      downColor: '#f23645',
      borderVisible: false,
      wickUpColor: '#089981',
      wickDownColor: '#f23645',
    });

    const visibleCount =
      stage === 1
        ? Math.max(activeCandles.length - 6 + Math.min(6, Math.floor((t / Math.max(t2, 1)) * 7)), 12)
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

    if (stage >= 2) {
      series.createPriceLine({
        price: Number(smc.supply_high),
        color: '#f23645',
        lineWidth: 3,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'SUPPLY',
      });
    }
    if (stage >= 3) {
      series.createPriceLine({
        price: Number(smc.demand_low),
        color: '#089981',
        lineWidth: 3,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'DEMAND',
      });
    }
    if (stage >= 4) {
      series.createPriceLine({
        price: Number(smc.watch_high),
        color: '#facc15',
        lineWidth: 3,
        lineStyle: 0,
        axisLabelVisible: true,
        title: 'WATCH ZONE',
      });
    }
    if (stage >= 5 && smc.trade_setup) {
      series.createPriceLine({
        price: Number(smc.trade_setup.entry),
        color: '#38bdf8',
        lineWidth: 3,
        lineStyle: 0,
        axisLabelVisible: true,
        title: `${smc.trade_setup.direction}`,
      });
      series.createPriceLine({
        price: Number(smc.trade_setup.sl),
        color: '#f23645',
        lineWidth: 3,
        lineStyle: 1,
        axisLabelVisible: true,
        title: 'SL',
      });
      series.createPriceLine({
        price: Number(smc.trade_setup.tp),
        color: '#089981',
        lineWidth: 3,
        lineStyle: 1,
        axisLabelVisible: true,
        title: `TP 1:${smc.trade_setup.rr}`,
      });
    }

    return () => chart.remove();
  }, [stage, Math.floor(frame / 4)]);
  const sortedCaptions = [...captions].sort((a, b) => a.start - b.start);
  const foundIdx = sortedCaptions.findIndex((c) => t >= c.start && t <= c.end + 0.12);
  const activeChunkIdx = foundIdx >= 0 ? Math.floor(foundIdx / 3) : -1;
  const currentChunk = activeChunkIdx >= 0 ? sortedCaptions.slice(activeChunkIdx * 3, activeChunkIdx * 3 + 3) : [];
  const lastCandle = activeCandles[activeCandles.length - 1];

  return (
    <AbsoluteFill style={{ backgroundColor: '#0b0e14', fontFamily: 'sans-serif' }}>
      <Audio src={staticFile('voiceover.mp3')} />

      {/* Top Hook Pill */}
      <div style={{ position: 'absolute', top: 136, left: 16, right: 16, display: 'flex', justifyContent: 'center', zIndex: 10 }}>
        <div
          style={{
            backgroundColor: '#181c27',
            border: '3px solid #facc15',
            borderRadius: 18,
            padding: '12px 34px',
            color: '#facc15',
            fontSize: 44,
            fontWeight: 900,
            letterSpacing: 0.8,
            textAlign: 'center',
          }}
        >
          {hookTitle}
        </div>
      </div>

      {/* Session & Live Spot Strip */}
      <div
        style={{
          position: 'absolute',
          top: 228,
          left: 16,
          right: 16,
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 25,
          fontWeight: 800,
        }}
      >
        <span style={{ color: '#94a3b8' }}>{session} • {smc.bias_label}</span>
        <span style={{ color: '#38bdf8' }}>XAUUSD ${(Number(smc.live_price) + tickPulse).toFixed(2)}</span>
      </div>

      {/* Full-Bleed Mobile TradingView Chart Card */}
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
            fontSize: 22,
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
        <div ref={chartContainerRef} />
      </div>

      {/* Progress Bar */}
      <div style={{ position: 'absolute', top: 1332, left: 8, width: 1064, height: 8, backgroundColor: '#1e222d', borderRadius: 4 }}>
        <div style={{ width: `${Math.min(100, (t / durationSec) * 100)}%`, height: '100%', backgroundColor: '#facc15', borderRadius: 4 }} />
      </div>

      {/* Karaoke Captions (Safely above Shorts/Reels UI) */}
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
                    fontSize: 48,
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
