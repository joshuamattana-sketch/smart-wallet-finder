import { NextRequest, NextResponse } from "next/server";
import { buildMockHeatmapPayload } from "@/lib/mock-heatmap-api";
import type { HeatmapTimeframe, HeatmapApiError } from "@/lib/heatmap-types";
import { isKnownSymbol, getMarketSymbols } from "@/lib/market-sources";
import { loadHeatmapFixture } from "@/lib/heatmap-fixture-loader";

const VALID_TIMEFRAMES: HeatmapTimeframe[] = ["5m", "15m", "1h", "4h", "1d"];

export async function GET(req: NextRequest): Promise<NextResponse> {
  const { searchParams } = req.nextUrl;

  const symbol    = (searchParams.get("symbol")    ?? "BTCUSDT").toUpperCase();
  const exchange  =  searchParams.get("exchange")  ?? "binance_spot";
  const timeframe =  searchParams.get("timeframe") ?? "5m";
  const source    =  searchParams.get("source");   // "fixture" opts into local fixtures

  if (!isKnownSymbol(symbol)) {
    const body: HeatmapApiError = {
      error:   "Unsupported symbol",
      message: `'${symbol}' is not a known market. Supported symbols: ${getMarketSymbols().join(", ")}.`,
    };
    return NextResponse.json(body, { status: 400 });
  }

  if (!(VALID_TIMEFRAMES as string[]).includes(timeframe)) {
    const body: HeatmapApiError = {
      error:   "Invalid timeframe",
      message: `'${timeframe}' is not supported. Valid values: ${VALID_TIMEFRAMES.join(", ")}.`,
    };
    return NextResponse.json(body, { status: 400 });
  }

  // Opt-in: serve a locally exported fixture payload when source=fixture and a
  // matching file exists. Falls back to the mock when no fixture is present.
  if (source === "fixture") {
    const fixture = loadHeatmapFixture(symbol, timeframe);
    if (fixture) {
      // Preserve any producer tag from the exported file under dataSource,
      // and flag the request origin as "fixture".
      const producer = fixture.meta?.source;
      fixture.meta = {
        ...fixture.meta,
        source: "fixture",
        dataSource: fixture.meta?.dataSource ?? producer ?? "fixture",
      };
      return NextResponse.json(fixture);
    }
    // No fixture on disk → fall back to the synthetic mock.
    const fallback = buildMockHeatmapPayload(symbol, exchange, timeframe as HeatmapTimeframe);
    fallback.meta.source = "mock";
    return NextResponse.json(fallback);
  }

  const payload = buildMockHeatmapPayload(symbol, exchange, timeframe as HeatmapTimeframe);
  return NextResponse.json(payload);
}
