"""
services/gold_bot_inverse_replay_test.py
------------------------------------------
LM98C - Inverse replay test (RESEARCH-ONLY, OFFLINE).

Reads the existing LM85A replay rows and, per scope (global / timeframe / mapped
tactic) and per horizon, compares ORIGINAL directional results vs the INVERSE
(LONG<->SHORT) by negating each trade's directional points and flipping its
win/loss outcome. It answers "is the bot consistently wrong, or just using a bad
horizon?" and emits a PREVIEW-ONLY demo whitelist/blacklist.

It computes inverse only from realized directional points already in the replay
rows (`score[h].dir_return_points` + `outcome`). NO MT5, NO orders, NO demo/live,
NO network, NO sizing change. The whitelist preview is NOT used by execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.gold_bot_learning_journal import DEFAULT_REPLAY_DIR, load_replay_rows
from services.gold_bot_tactic_library import load_library, mapped_setup_tags

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TACTIC_TESTS_DIR = _REPO_ROOT / "data" / "gold_bot" / "tactic_tests"
PROMISING_EXP = 20.0
EDGE_MARGIN = 15.0
PREVIEW_NOTE = "Preview only - not used by demo execution yet."


@dataclass
class InverseConfig:
    timeframes: tuple[str, ...] = ("M1", "M5")
    horizons: tuple[int, ...] = (15, 30)
    min_samples: int = 20
    library_path: str | None = None


# ── metrics ──────────────────────────────────────────────────────────────────────
def _classify(n: int, expectancy: float, winrate: float, min_samples: int) -> str:
    if n < min_samples:
        return "insufficient"
    if expectancy >= PROMISING_EXP and winrate >= 0.50:
        return "promising"
    if expectancy < 0 and winrate < 0.45:
        return "avoid"
    return "weak"


def _flip_outcome(o: Any) -> Any:
    return {"win": "loss", "loss": "win"}.get(o, o)


def _metrics(trades: list[tuple[float, Any]], min_samples: int) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "winrate": 0.0, "expectancy_points": 0.0, "total_points": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": None,
                "max_drawdown_points": 0.0, "status": "insufficient"}
    pts = [float(dr) for dr, _ in trades]
    wins = [dr for dr, o in trades if o == "win"]
    losses = [dr for dr, o in trades if o == "loss"]
    decided = len(wins) + len(losses)
    winrate = round(len(wins) / decided, 3) if decided else 0.0
    total = sum(pts)
    expectancy = round(total / n, 1)
    gross_win = sum(p for p in pts if p > 0)
    gross_loss = -sum(p for p in pts if p < 0)
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else None
    cum = peak = dd = 0.0
    for p in pts:
        cum += p
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return {"trades": n, "winrate": winrate, "expectancy_points": expectancy,
            "total_points": round(total, 1),
            "avg_win": round(sum(wins) / len(wins), 1) if wins else 0.0,
            "avg_loss": round(sum(losses) / len(losses), 1) if losses else 0.0,
            "profit_factor": pf, "max_drawdown_points": round(dd, 1),
            "status": _classify(n, expectancy, winrate, min_samples)}


def _collect_trades(rows: list[dict], horizon: int, setup: str | None = None
                    ) -> list[tuple[float, Any]]:
    out: list[tuple[float, Any]] = []
    for r in rows:
        if setup is not None and r.get("strategy") != setup:
            continue
        if r.get("decision") not in ("LONG", "SHORT"):
            continue
        sc = (r.get("score") or {}).get(str(horizon))
        if not sc:
            continue
        dr = sc.get("dir_return_points")
        if dr is None:
            continue
        out.append((float(dr), sc.get("outcome")))
    return out


def _pair(rows: list[dict], horizon: int, min_samples: int, setup: str | None = None) -> dict:
    trades = _collect_trades(rows, horizon, setup)
    original = _metrics(trades, min_samples)
    inverse = _metrics([(-dr, _flip_outcome(o)) for dr, o in trades], min_samples)
    return {"horizon": horizon, "original": original, "inverse": inverse,
            "inverse_edge": _inverse_edge(original, inverse)}


def _inverse_edge(original: dict, inverse: dict) -> str:
    if original["status"] == "insufficient" or inverse["status"] == "insufficient":
        return "insufficient"
    oe, ie = original["expectancy_points"], inverse["expectancy_points"]
    if oe >= PROMISING_EXP and ie >= PROMISING_EXP:
        return "both_promising"
    if oe < 0 and ie < 0:
        return "both_bad"
    if ie > oe + EDGE_MARGIN:
        return "inverse_better"
    if oe > ie + EDGE_MARGIN:
        return "original_better"
    return "original_better" if oe >= ie else "inverse_better"


# ── evaluation ─────────────────────────────────────────────────────────────────────
def evaluate(rows: list[dict], cfg: InverseConfig, mapped: dict[str, str]) -> dict:
    tfs = tuple(cfg.timeframes) or None
    rows_scope = [r for r in rows if (not tfs or r.get("timeframe") in tfs)]

    global_by_h = {str(h): _pair(rows_scope, h, cfg.min_samples) for h in cfg.horizons}
    by_timeframe = {
        tf: {str(h): _pair([r for r in rows_scope if r.get("timeframe") == tf], h, cfg.min_samples)
             for h in cfg.horizons}
        for tf in cfg.timeframes
    }

    tactics: dict[str, dict] = {}
    for setup_tag, tactic_id in mapped.items():
        per_h = {str(h): _pair(rows_scope, h, cfg.min_samples, setup=setup_tag) for h in cfg.horizons}
        # best ORIGINAL horizon (max expectancy among horizons with enough trades)
        best_h = None
        best_exp = None
        for h in cfg.horizons:
            o = per_h[str(h)]["original"]
            if o["status"] != "insufficient" and (best_exp is None or o["expectancy_points"] > best_exp):
                best_exp, best_h = o["expectancy_points"], h
        tactics[tactic_id] = {"setup_tag": setup_tag, "by_horizon": per_h,
                              "best_original_horizon": best_h,
                              "recommendation": _recommend(tactic_id, setup_tag, per_h, best_h, cfg.horizons)}

    whitelist, blacklist = _whitelist_blacklist(tactics, cfg.horizons)
    suggested_horizon = _suggested_horizon(global_by_h, cfg.horizons)

    return {
        "global": global_by_h, "by_timeframe": by_timeframe, "tactics": tactics,
        "suggested_horizons": suggested_horizon,
        "demo_whitelist_preview": {"note": PREVIEW_NOTE, "whitelist": whitelist,
                                   "blacklist": blacklist, "suggested_horizons": suggested_horizon},
        "total_replay_trades": sum(global_by_h[str(h)]["original"]["trades"] for h in cfg.horizons[:1]),
    }


def _recommend(tactic_id: str, setup_tag: str, per_h: dict, best_h: int | None,
               horizons: tuple[int, ...]) -> str:
    if best_h is None:
        return "insufficient sample - no recommendation"
    pair = per_h[str(best_h)]
    o, edge = pair["original"], pair["inverse_edge"]
    if o["status"] == "promising":
        return f"whitelist ORIGINAL h{best_h} ({o['expectancy_points']:+}pt)"
    if edge == "inverse_better":
        return f"inverse looks better at h{best_h} - research inversion (engine NOT inverted)"
    if o["status"] == "avoid":
        return "blacklist until filtered"
    return f"weak - keep researching (best h{best_h} {o['expectancy_points']:+}pt)"


def _whitelist_blacklist(tactics: dict, horizons: tuple[int, ...]) -> tuple[list[dict], list[dict]]:
    whitelist: list[dict] = []
    blacklist: list[dict] = []
    for tid, t in tactics.items():
        best_h = t["best_original_horizon"]
        if best_h is None:
            blacklist.append({"tactic": tid, "reason": "insufficient sample"})
            continue
        o = t["by_horizon"][str(best_h)]["original"]
        if o["status"] == "promising":
            whitelist.append({"tactic": tid, "horizon": best_h,
                              "expectancy_points": o["expectancy_points"]})
        elif o["status"] == "avoid":
            blacklist.append({"tactic": tid, "reason": f"avoid at best h{best_h} "
                              f"({o['expectancy_points']:+}pt)"})
    return whitelist, blacklist


def _suggested_horizon(global_by_h: dict, horizons: tuple[int, ...]) -> list[int]:
    ranked = sorted(horizons, key=lambda h: global_by_h[str(h)]["original"]["expectancy_points"],
                    reverse=True)
    return list(ranked)


# ── report ──────────────────────────────────────────────────────────────────────
def _fmt_pair(label: str, pair: dict) -> str:
    o, i = pair["original"], pair["inverse"]
    return (f"{label}: original {o['expectancy_points']:+}pt/{o['status']} "
            f"(n{o['trades']}, wr {round(o['winrate']*100)}%) | "
            f"inverse {i['expectancy_points']:+}pt/{i['status']} -> edge {pair['inverse_edge']}")


def build_markdown(result: dict, cfg: InverseConfig, meta: dict, warnings: list[str]) -> str:
    L = ["# Gold Bot Tactic / Inverse Replay Test", "",
         f"_Replay-only research. No demo outcomes used here. {PREVIEW_NOTE}_", "",
         f"- timeframes: {', '.join(cfg.timeframes)}  horizons: {', '.join(map(str, cfg.horizons))}  "
         f"min-samples: {cfg.min_samples}",
         f"- tactic library: {meta.get('path')}", ""]
    for w in warnings:
        L.append(f"- warning: {w}")
    L += ["", "## Global (original vs inverse) by horizon", ""]
    for h in cfg.horizons:
        L.append(f"- {_fmt_pair(f'h{h}', result['global'][str(h)])}")
    L += ["", "## Per timeframe", ""]
    for tf, hs in result["by_timeframe"].items():
        L.append(f"### {tf}")
        for h in cfg.horizons:
            L.append(f"- {_fmt_pair(f'h{h}', hs[str(h)])}")
    L += ["", "## Mapped tactics", ""]
    for tid, t in result["tactics"].items():
        L.append(f"### {tid}  (setup {t['setup_tag']})")
        for h in cfg.horizons:
            L.append(f"- {_fmt_pair(f'h{h}', t['by_horizon'][str(h)])}")
        L.append(f"- recommendation: {t['recommendation']}")
    wl = result["demo_whitelist_preview"]
    L += ["", "## Demo whitelist preview (NOT active)", "",
          f"_{PREVIEW_NOTE}_", "",
          f"- suggested horizons (best first): {', '.join(map(str, wl['suggested_horizons']))}",
          "- whitelist:"]
    L += [f"  - {w['tactic']} h{w['horizon']} ({w['expectancy_points']:+}pt)" for w in wl["whitelist"]] or ["  - (none)"]
    L += ["- blacklist:"]
    L += [f"  - {b['tactic']} - {b['reason']}" for b in wl["blacklist"]] or ["  - (none)"]
    L += ["", "Replay-only research. No MT5 orders, no demo execution, live locked."]
    return "\n".join(L)


# ── run + persist ─────────────────────────────────────────────────────────────────
def run_inverse_test(cfg: InverseConfig, *, replay_dir: Path = DEFAULT_REPLAY_DIR,
                     out_dir: Path = DEFAULT_TACTIC_TESTS_DIR,
                     now_fn=lambda: datetime.now(timezone.utc)) -> dict:
    tactics, meta, lib_warn = load_library(cfg.library_path)
    mapped = mapped_setup_tags(tactics)
    rows, files, warnings = load_replay_rows(replay_dir)
    warnings = lib_warn + warnings

    if not rows:
        return {"ok": False, "error": "no replay data - run scripts/run_gold_bot_replay.py first",
                "warnings": warnings, "meta": meta}

    result = evaluate(rows, cfg, mapped)
    # detect missing-field case: rows exist but no directional points anywhere
    if sum(result["global"][str(h)]["original"]["trades"] for h in cfg.horizons) == 0:
        warnings.append("replay rows lack directional trade data (no LONG/SHORT dir_return_points) "
                        "- cannot compute inverse edge")

    result.update({"ok": True, "generated_at": now_fn().isoformat(), "replay_files": len(files),
                   "timeframes": list(cfg.timeframes), "horizons": list(cfg.horizons),
                   "min_samples": cfg.min_samples, "mapped_tactics": mapped, "warnings": warnings})
    markdown = build_markdown(result, cfg, meta, warnings)
    result["paths"] = _write(result, markdown, out_dir, now_fn())
    return result


def _write(result: dict, markdown: str, out_dir: Path, now: datetime) -> dict[str, str]:
    try:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%d_%H%M%S")
        paths = {
            "json": d / f"inverse_{stamp}.json", "latest_json": d / "inverse_latest.json",
            "md": d / f"inverse_{stamp}.md", "latest_md": d / "inverse_latest.md",
            "whitelist_preview": d / "demo_whitelist.preview.json",
        }
        payload = json.dumps(result, indent=2, default=str)
        paths["json"].write_text(payload, encoding="utf-8")
        paths["latest_json"].write_text(payload, encoding="utf-8")
        paths["md"].write_text(markdown + "\n", encoding="utf-8")
        paths["latest_md"].write_text(markdown + "\n", encoding="utf-8")
        wl = dict(result["demo_whitelist_preview"])
        wl["generated_at"] = result.get("generated_at")
        paths["whitelist_preview"].write_text(json.dumps(wl, indent=2, default=str), encoding="utf-8")
        return {k: str(v) for k, v in paths.items()}
    except OSError:
        return {}
