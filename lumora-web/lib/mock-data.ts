export const mockKpis = [
  { label: "BTC Price", value: "$67,420", change: "+2.14%", positive: true },
  { label: "ETH Price", value: "$3,512", change: "+1.83%", positive: true },
  { label: "Market Bias", value: "BULLISH", change: "Confidence 78%", positive: true },
  { label: "Whale Alerts", value: "14", change: "Last 1h", positive: null },
  { label: "Top Liquidity Wall", value: "$68,000", change: "BTC Ask Wall", positive: null },
  { label: "Fear & Greed", value: "72 — Greed", change: "↑ from 65", positive: true },
];

export const mockSetups = [
  { symbol: "BTCUSDT", bias: "LONG", confidence: 84, entry: "67,100", target: "69,500", stop: "66,200", reason: "Strong bid wall at 67k, low OI flush" },
  { symbol: "ETHUSDT", bias: "LONG", confidence: 71, entry: "3,480", target: "3,650", stop: "3,400", reason: "Absorption visible in tape, CVD divergence" },
  { symbol: "SOLUSDT", bias: "SHORT", confidence: 63, entry: "158.50", target: "152.00", stop: "162.00", reason: "Rejection at ask wall, whale distribution" },
  { symbol: "BNBUSDT", bias: "NEUTRAL", confidence: 55, entry: "—", target: "—", stop: "—", reason: "Compressed range, wait for breakout" },
];

export const mockWhaleAlerts = [
  { id: 1, time: "14:32", symbol: "BTC", side: "BUY", size: "$4.2M", exchange: "Binance", type: "Spot Accumulation", risk: "HIGH" },
  { id: 2, time: "14:28", symbol: "ETH", side: "SELL", size: "$1.8M", exchange: "Bybit", type: "Perp Short Open", risk: "MEDIUM" },
  { id: 3, time: "14:21", symbol: "SOL", side: "BUY", size: "$880K", exchange: "Coinbase", type: "Spot Buy", risk: "LOW" },
  { id: 4, time: "14:15", symbol: "BTC", side: "BUY", size: "$6.1M", exchange: "OKX", type: "Futures Long", risk: "HIGH" },
  { id: 5, time: "14:08", symbol: "DOGE", side: "SELL", size: "$420K", exchange: "Binance", type: "Spot Dump", risk: "LOW" },
  { id: 6, time: "14:02", symbol: "ETH", side: "BUY", size: "$2.2M", exchange: "Binance", type: "Spot Accumulation", risk: "MEDIUM" },
];

export const mockOrderbook = {
  symbol: "BTCUSDT",
  midPrice: 67420,
  asks: [
    { price: 67480, size: 1.24, total: 1.24, usd: 83475 },
    { price: 67470, size: 0.88, total: 2.12, usd: 59374 },
    { price: 67460, size: 2.41, total: 4.53, usd: 162578 },
    { price: 67450, size: 0.55, total: 5.08, usd: 37098 },
    { price: 67440, size: 3.20, total: 8.28, usd: 215808 },
    { price: 67430, size: 1.10, total: 9.38, usd: 74173 },
    { price: 67425, size: 0.74, total: 10.12, usd: 49895 },
    { price: 67422, size: 0.31, total: 10.43, usd: 20901 },
  ],
  bids: [
    { price: 67418, size: 0.42, total: 0.42, usd: 28316 },
    { price: 67415, size: 1.85, total: 2.27, usd: 124718 },
    { price: 67410, size: 0.63, total: 2.90, usd: 42468 },
    { price: 67400, size: 4.10, total: 7.00, usd: 276340 },
    { price: 67390, size: 1.22, total: 8.22, usd: 82216 },
    { price: 67380, size: 0.77, total: 8.99, usd: 51883 },
    { price: 67370, size: 2.60, total: 11.59, usd: 175162 },
    { price: 67350, size: 0.95, total: 12.54, usd: 63983 },
  ],
};

export const mockLiquidityZones = [
  { price: 68000, intensity: 95, side: "ASK", label: "Major Wall" },
  { price: 67500, intensity: 72, side: "ASK", label: "Resistance" },
  { price: 67000, intensity: 88, side: "BID", label: "Support Floor" },
  { price: 66500, intensity: 61, side: "BID", label: "Demand Zone" },
  { price: 65800, intensity: 79, side: "BID", label: "Strong Bid" },
];

export const mockPaperTrades = [
  { id: 1, symbol: "BTCUSDT", side: "LONG", entry: 66800, current: 67420, size: 0.5, pnl: 310, pnlPct: 0.93, status: "OPEN" },
  { id: 2, symbol: "ETHUSDT", side: "LONG", entry: 3450, current: 3512, size: 2.0, pnl: 124, pnlPct: 1.80, status: "OPEN" },
  { id: 3, symbol: "SOLUSDT", side: "SHORT", entry: 162, current: 158.5, size: 10, pnl: 35, pnlPct: 2.16, status: "OPEN" },
];

export const mockJournal = [
  { date: "2026-05-31", symbol: "BTC", side: "LONG", pnl: 420, note: "Clean breakout above 67k resistance. CVD confirmation." },
  { date: "2026-05-30", symbol: "ETH", side: "SHORT", pnl: -85, note: "Stop hit at 3520. Underestimated bid absorption." },
  { date: "2026-05-29", symbol: "SOL", side: "LONG", pnl: 210, note: "Liquidity sweep at 150, perfect reversal." },
];

export const roadmapItems = [
  { phase: "Q2 2026", title: "Private Beta Launch", status: "active", items: ["Live Orderbook Terminal", "Whale Alert Engine", "Basic Liquidity Maps"] },
  { phase: "Q3 2026", title: "Pro Features", status: "upcoming", items: ["AI Market Bias Engine", "Multi-Exchange Aggregation", "Paper Trading with P&L"] },
  { phase: "Q4 2026", title: "Premium Tier", status: "planned", items: ["Custom Alerts & Webhooks", "Historical Replay Mode", "Strategy Backtester"] },
  { phase: "2027", title: "Ecosystem", status: "planned", items: ["API Access", "Discord Bot", "Mobile App"] },
];
