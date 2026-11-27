import React from 'react';
import { Composition } from 'remotion';
import { TradingViewReel, ReelProps } from './TradingViewReel';

const defaultProps: ReelProps = {
  session: 'NEW YORK SESSION',
  hookTitle: 'GOLD LIQUIDITY MAP',
  durationSec: 30,
  stageTimes: new Array(6, 13, 20, 25),
  smc: {
    live_price: 2745.5,
    bias_label: 'BEARISH BIAS',
    supply_low: 2750,
    supply_high: 2756,
    demand_low: 2728,
    demand_high: 2734,
    watch_low: 2750,
    watch_high: 2756,
    equilibrium: 2742,
    trade_setup: { direction: 'SHORT', entry: 2753, sl: 2759, tp: 2734, rr: 3.1 },
  },
  candles15m: new Array(),
  candles5m: new Array(),
  captions: new Array(),
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="TradingViewReel"
      component={TradingViewReel}
      durationInFrames={1800}
      fps={60}
      width={1080}
      height={1920}
      defaultProps={defaultProps}
      calculateMetadata={({ props }) => {
        return {
          durationInFrames: Math.max(Math.ceil((props.durationSec || 30) * 60), 300),
          fps: 60,
          width: 1080,
          height: 1920,
        };
      }}
    />
  );
};
