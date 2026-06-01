import { NextRequest, NextResponse } from "next/server";
import { buildMockHeatmapPayload } from "@/lib/mock-heatmap-api";
import type { HeatmapTimeframe, HeatmapApiError } from "@/lib/heatmap-types";

const VALID_TIMEFRAMES: HeatmapTimeframe[] = ["5m", "15m", "1h", "4h", "1d"];

export async function GET(req: NextRequest): Promise<NextResponse> {
  const { searchParams } = req.nextUrl;

  const symbol    = (searchParams.get("symbol")    ?? "BTCUSDT").toUpperCase();
  const exchange  =  searchParams.get("exchange")  ?? "binance_spot";
  const timeframe =  searchParams.get("timeframe") ?? "5m";

  if (!(VALID_TIMEFRAMES as string[]).includes(timeframe)) {
    const body: HeatmapApiError = {
      error:   "Invalid timeframe",
      message: `'${timeframe}' is not supported. Valid values: ${VALID_TIMEFRAMES.join(", ")}.`,
    };
    return NextResponse.json(body, { status: 400 });
  }

  const payload = buildMockHeatmapPayload(symbol, exchange, timeframe as HeatmapTimeframe);
  return NextResponse.json(payload);
}
