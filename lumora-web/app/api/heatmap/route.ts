import { NextRequest, NextResponse } from "next/server";
import { buildMockHeatmapPayload } from "@/lib/mock-heatmap-api";

const VALID_TIMEFRAMES = new Set(["5m", "15m", "1h", "4h", "1d"]);

export async function GET(req: NextRequest): Promise<NextResponse> {
  const { searchParams } = req.nextUrl;

  const symbol   = (searchParams.get("symbol")   ?? "BTCUSDT").toUpperCase();
  const exchange = searchParams.get("exchange")  ?? "binance_spot";
  const timeframe = searchParams.get("timeframe") ?? "5m";

  if (!VALID_TIMEFRAMES.has(timeframe)) {
    return NextResponse.json(
      {
        error:   "Invalid timeframe",
        message: `'${timeframe}' is not supported. Valid values: ${Array.from(VALID_TIMEFRAMES).join(", ")}.`,
      },
      { status: 400 },
    );
  }

  const payload = buildMockHeatmapPayload(symbol, exchange, timeframe);
  return NextResponse.json(payload);
}
