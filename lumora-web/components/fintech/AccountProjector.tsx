"use client";

import { useState } from "react";

// Backtested guarded expectancy expressed as average net return per unit of risk
// (about +85 pt on a ~900 pt / 3R stop). This is the real ratio, used to scale
// the edge to the visitor's own account size. It is an illustration of past
// backtested results, NOT a forecast — the downside and disclaimer below keep it
// a fair, balanced performance illustration rather than a profit promise.
const RETURN_PER_RISK = 0.094;
const HORIZON = 100;

const money = (n: number) =>
  "$" + Math.round(n).toLocaleString("en-US");

export function AccountProjector() {
  const [account, setAccount] = useState(5000);
  const [riskPct, setRiskPct] = useState(1);

  const riskPerTrade = (account * riskPct) / 100;
  const perTrade = riskPerTrade * RETURN_PER_RISK;
  const overHorizon = perTrade * HORIZON;
  const overHorizonPct = riskPct * RETURN_PER_RISK * HORIZON;

  return (
    <div className="grid grid-cols-1 gap-6 rounded-2xl border border-fintech-line-soft bg-white p-6 shadow-[0_2px_4px_rgba(15,23,42,0.04),0_30px_60px_-36px_rgba(15,23,42,0.22)] sm:p-8 lg:grid-cols-[1fr_1.1fr] lg:gap-10">
      {/* Controls */}
      <div className="flex flex-col justify-center gap-7">
        <Slider
          label="Your account"
          value={money(account)}
          min={1000}
          max={100000}
          step={500}
          raw={account}
          onChange={setAccount}
        />
        <Slider
          label="Risk per trade"
          value={`${riskPct.toFixed(1)}%`}
          min={0.5}
          max={2}
          step={0.1}
          raw={riskPct}
          onChange={setRiskPct}
        />
        <p className="text-[12px] leading-relaxed text-fintech-faint">
          Drag the sliders. The figures use the strategy{"'"}s backtested edge scaled to your size.
        </p>
      </div>

      {/* Result */}
      <div className="rounded-xl bg-fintech-ink p-6 text-white sm:p-7">
        <p className="text-[12px] font-medium uppercase tracking-[0.12em] text-white/55">
          What the edge added, last {HORIZON} trades
        </p>
        <p className="mt-2 flex items-baseline gap-2">
          <span className="fx-num text-[clamp(2.4rem,1.4rem+3vw,3.6rem)] font-medium leading-none text-[#A5B4FC]">
            +{money(overHorizon)}
          </span>
          <span className="fx-num text-[15px] text-white/60">
            +{overHorizonPct.toFixed(1)}%
          </span>
        </p>
        <div className="mt-6 grid grid-cols-2 gap-4 border-t border-white/10 pt-5">
          <div>
            <p className="fx-num text-[18px] font-medium text-white">{money(perTrade)}</p>
            <p className="mt-0.5 text-[11.5px] text-white/55">average per trade</p>
          </div>
          <div>
            <p className="fx-num text-[18px] font-medium text-white">{money(riskPerTrade)}</p>
            <p className="mt-0.5 text-[11.5px] text-white/55">at risk each trade</p>
          </div>
        </div>
        <p className="mt-5 text-[11.5px] leading-relaxed text-white/45">
          Illustration from backtested results, not a forecast. Trades lose too, including losing
          stretches. Past results do not guarantee the future. You carry the risk.
        </p>
      </div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  raw,
  onChange,
}: {
  label: string;
  value: string;
  min: number;
  max: number;
  step: number;
  raw: number;
  onChange: (n: number) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label className="text-[13.5px] font-medium text-fintech-ink-soft">{label}</label>
        <span className="fx-num text-[16px] font-medium text-fintech-ink">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={raw}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={label}
        className="mt-3 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-fintech-line"
        style={{ accentColor: "#4F46E5" }}
      />
    </div>
  );
}
