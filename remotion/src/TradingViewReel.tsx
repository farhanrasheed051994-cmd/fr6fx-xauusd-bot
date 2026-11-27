import React, { useEffect, useRef } from 'react';
import {
  AbsoluteFill,
  Audio,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
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

  // Smooth human-edited camera zoom & pan on each stage change
  const zoomScale = interpolate(
    t,
    [0, t2, t2 + 0.4, t4, t4 + 0.4, t5, t5 + 0.5, durationSec],
    [1.0, 1.03, 1.01, 1.04, 1.02, 1.06, 1.04, 1.08],
    { extrapolateRight: 'clamp' }
  );

  // Live price pulse simulation on final candle
  const tickPulse = Math.sin(frame * 0.25) * 0.35;
  const activeCandles = stage >= 5 && candles5m.length > 0 ? candles5m : candles15m;

  useEffect(() => {
    if (!chartContainerRef.current || activeCandles.length === 0) return;
    chartContainerRef.current.innerHTML = '';

    const chart = createChart(chartContainerRef.current, {
      width: 1036,
      height: 1090,
      layout: {
        background: { type: ColorType.Solid, color: '#131722' },
        textColor: '#787b86',
        fontSize: 16,
      },
      grid: {
        vertLines: { color: '#1e222d' },
        horzLines: { color: '#1e222d' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#2a2e39' },
      timeScale: { borderColor: '#2a2e39', timeVisible: true, secondsVisible: false },
    });

    const series = chart.addCandlestickSeries({
      upColor: '#089981',
      downColor: '#f23645',
      borderVisible: false,
      wickUpColor: '#089981',
      wickDownColor: '#f23645',
    });

    // Progressive replay: reveal last 6 candles live during Stage 1, full chart by Stage 2+
    const visibleCount =
      stage === 1
        ? Math.max(activeCandles.length - 6 + Math.min(6, Math.floor((t / Math.max(t2, 1)) * 7)), 10)
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

    // TradingView Price Lines for SMC Zones & Risk/Reward Setup
    if (stage >= 2) {
      series.createPriceLine({
        price: Number(smc.supply_high),
        color: '#f23645',
        lineWidth: 2,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'SUPPLY / BSL',
      });
    }
    if (stage >= 3) {
      series.createPriceLine({
        price: Number(smc.demand_low),
        color: '#089981',
        lineWidth: 2,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'DEMAND / SSL',
      });
    }
    if (stage >= 4) {
      series.createPriceLine({
        price: Number(smc.watch_high),
        color: '#facc15',
        lineWidth: 2,
        lineStyle: 0,
        axisLabelVisible: true,
        title: 'WATCH ZONE',
      });
    }
    if (stage >= 5 && smc.trade_setup) {
      series.createPriceLine({
        price: Number(smc.trade_setup.entry),
        color: '#38bdf8',
        lineWidth: 2,
        lineStyle: 0,
        axisLabelVisible: true,
        title: `${smc.trade_setup.direction} ENTRY`,
      });
      series.createPriceLine({
        price: Number(smc.trade_setup.sl),
        color: '#f23645',
        lineWidth: 2,
        lineStyle: 1,
        axisLabelVisible: true,
        title: 'STOP LOSS',
      });
      series.createPriceLine({
        price: Number(smc.trade_setup.tp),
        color: '#089981',
        lineWidth: 2,
        lineStyle: 1,
        axisLabelVisible: true,
        title: `TARGET (1:${smc.trade_setup.rr} R:R)`,
      });
    }

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [stage, Math.floor(frame / 4)]);

  const activeChunkIdx = Math.floor(
    Math.max(0, captions.findIndex((c) => t >= c.start && t <= c.end)) / 3
  );
  const currentChunk = captions.slice(activeChunkIdx * 3, activeChunkIdx * 3 + 3);
  const lastCandle = activeCandles[activeCandles.length - 1];

  return (
    <AbsoluteFill style={{ backgroundColor: '#0b0e14', fontFamily: 'sans-serif' }}>
      <Audio src={staticFile('voiceover.mp3')} />

      {/* Top Hook Pill */}
      <div style={{ position: 'absolute', top: 170, width: '100%', display: 'flex', justifyContent: 'center', zIndex: 10 }}>
        <div
          style={{
            backgroundColor: '#181c27',
            border: '3px solid #facc15',
            borderRadius: 20,
            padding: '14px 36px',
            color: '#facc15',
            fontSize: 42,
            fontWeight: 900,
            letterSpacing: 1,
          }}
        >
          {hookTitle}
        </div>
      </div>

      {/* Session & Live Spot Strip */}
      <div
        style={{
          position: 'absolute',
          top: 268,
          left: 26,
          right: 115,
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 24,
          fontWeight: 800,
        }}
      >
        <span style={{ color: '#94a3b8' }}>{session} • {smc.bias_label}</span>
        <span style={{ color: '#38bdf8' }}>XAUUSD ${(Number(smc.live_price) + tickPulse).toFixed(2)}</span>
      </div>

      {/* TradingView Lightweight Charts Container */}
      <div
        style={{
          position: 'absolute',
          top: 306,
          left: 20,
          width: 1040,
          height: 1142,
          borderRadius: 20,
          border: '2px solid #2a2e39',
          backgroundColor: '#131722',
          overflow: 'hidden',
          transform: `scale(${zoomScale})`,
        }}
      >
        {/* TradingView OHLC Header */}
        <div
          style={{
            height: 50,
            padding: '0 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #2a2e39',
            fontSize: 20,
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
      <div style={{ position: 'absolute', top: 1456, left: 20, width: 1040, height: 8, backgroundColor: '#1e222d' }}>
        <div style={{ width: `${Math.min(100, (t / durationSec) * 100)}%`, height: '100%', backgroundColor: '#facc15' }} />
      </div>

      {/* Karaoke Captions */}
      {currentChunk.length > 0 && (
        <div style={{ position: 'absolute', top: 1482, left: 40, right: 100, display: 'flex', justifyContent: 'center' }}>
          <div
            style={{
              backgroundColor: 'rgba(10, 14, 23, 0.94)',
              border: '3px solid #facc15',
              borderRadius: 20,
              padding: '14px 30px',
              display: 'flex',
              gap: 16,
            }}
          >
            {currentChunk.map((w, idx) => {
              const active = t >= w.start && t <= w.end;
              const pop = spring({ frame: frame - w.start * fps, fps, config: { damping: 14 } });
              return (
                <span
                  key={idx}
                  style={{
                    fontSize: 46,
                    fontWeight: 900,
                    color: active ? '#facc15' : '#ffffff',
                    transform: active ? `scale(${1 + pop * 0.08})` : 'scale(1)',
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
