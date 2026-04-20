/**
 * LearningPage.jsx — TickerTap Learning Center.
 *
 * An interactive educational content page about stock trading and investing.
 * Organized into three difficulty levels (Beginner, Intermediate, Advanced),
 * each containing accordion-style topic cards with rich content: intro
 * paragraphs, detailed bullets, PRO TIP and DID YOU KNOW callout boxes.
 *
 * Features:
 *   - Progress tracking via localStorage (mark topics as read)
 *   - Per-tab progress bar with completion percentage
 *   - "Try It" navigation links to relevant TickerTap pages
 *   - Themed callout boxes (amber PRO TIP, cyan DID YOU KNOW)
 *
 * No backend calls — all content is embedded as static data arrays.
 *
 * Props:
 *   @param {string}   token       - JWT access token (consistency, unused)
 *   @param {function} setPage     - optional callback(page) to navigate within app
 */

import { useState, useCallback, useEffect } from "react";

/* ═══════════════════════════════════════════════════════════════════════════
   CONSTANTS
═══════════════════════════════════════════════════════════════════════════ */

const AMBER = "#f59e0b";
const CYAN = "#06b6d4";
const GREEN = "#22c55e";
const RED = "#ef4444";
const STORAGE_KEY = "learning_progress";

/* ═══════════════════════════════════════════════════════════════════════════
   LEARNING CONTENT DATA — rich educational material per difficulty level
═══════════════════════════════════════════════════════════════════════════ */

/** Beginner-level topics covering foundational investing concepts. */
const BEGINNER_TOPICS = [
  {
    title: "What Are Stocks?",
    icon: "\ud83d\udcc8",
    intro:
      "A stock represents ownership in a company. When you buy a share, you become a part-owner — entitled to a portion of the company's profits and assets. Stocks are the foundation of most investment portfolios.",
    bullets: [
      "Shares are units of stock — owning 100 shares of a company with 1 million total shares means you own 0.01% of the company. This entitles you to voting rights and a share of distributed profits.",
      "Companies issue stock through IPOs (Initial Public Offerings) to raise capital for growth, R&D, or paying off debt. Early investors often get in during the IPO and benefit from long-term appreciation.",
      "Stocks are traded on exchanges like the NYSE (New York Stock Exchange) and NASDAQ. The NYSE is an auction-based exchange while NASDAQ is electronic — both facilitate billions of dollars in daily trades.",
      "Market capitalization = share price × total shares outstanding. A company trading at $50 with 1 billion shares has a $50B market cap. Large-cap (>$10B), mid-cap ($2-10B), and small-cap (<$2B) behave differently.",
      "The stock market historically returns about 10% annually on average (before inflation). However, individual years can vary dramatically — from -38% (2008) to +31% (2019).",
    ],
    proTip:
      "Start with blue-chip stocks (large, established companies like Apple or Johnson & Johnson) before exploring smaller, more volatile companies. They offer stability while you learn the ropes.",
    funFact:
      "The oldest stock exchange in the world is the Amsterdam Stock Exchange, founded in 1602 by the Dutch East India Company! It was created so investors could buy and sell shares of the VOC's spice-trading expeditions.",
  },
  {
    title: "Understanding Price Charts",
    icon: "\ud83d\udcca",
    intro:
      "Price charts are your window into market behavior. They tell the story of a stock's journey — showing where it's been, how volatile it is, and where it might be headed. Learning to read charts is like learning a new language.",
    bullets: [
      "Candlestick charts show Open, High, Low, Close (OHLC) for each time period. The 'body' is the range between open and close; 'wicks' (shadows) extend to the high and low, revealing intra-period volatility.",
      "Green/white candle = close > open (buyers won that period). Red/black candle = close < open (sellers dominated). A long body means strong conviction; a short body means indecision.",
      "Timeframes matter: 1-minute and 5-minute charts are for day traders. Daily charts suit swing traders (days to weeks). Weekly and monthly charts are for long-term investors looking at the big picture.",
      "Volume bars beneath the chart show how many shares traded. High volume on a price move means the move has conviction; low volume moves are more likely to reverse.",
      "Common patterns to watch: 'Doji' candles (open ≈ close) signal indecision, 'Hammer' candles at lows signal potential reversal, and 'Engulfing' patterns suggest trend changes.",
    ],
    proTip:
      "Always look at multiple timeframes before making a decision. A stock might look bullish on a 15-minute chart but bearish on the daily. The higher timeframe usually wins.",
    funFact:
      "Candlestick charts were invented by Munehisa Homma, a Japanese rice trader, in the 1700s! He made a fortune trading rice futures and wrote the first book on market psychology.",
    tryIt: "charts",
  },
  {
    title: "Basic Order Types",
    icon: "\ud83d\udcdd",
    intro:
      "Knowing how to place the right order is just as important as knowing what to buy. Different order types give you varying levels of control over your execution price and timing.",
    bullets: [
      "Market order: executes immediately at the best available price. Great for liquid stocks where you want in NOW, but in volatile or illiquid markets you might get a worse price than expected (slippage).",
      "Limit order: only executes at your specified price or better. Buy limits execute at or below your price; sell limits at or above. You get price control but risk the order not filling if the market moves away.",
      "Stop-loss order: triggers a market sell when price drops to your stop level, protecting against large losses. Essential risk management — always set one! A logical stop is below a support level, not an arbitrary percentage.",
      "Stop-limit order: combines a stop trigger with a limit price. More precise than a regular stop-loss, but in a fast crash the price might gap through your limit and the order won't fill at all.",
      "GTC (Good-Til-Cancelled) orders stay active until filled or cancelled. Day orders expire at market close. For swing trades, GTC is usually better so you don't have to re-enter orders every morning.",
    ],
    proTip:
      "For most beginner trades, use limit orders instead of market orders. You'll often get a better price by being patient, and you'll avoid nasty surprises from slippage during volatile moments.",
    funFact:
      "In the 1800s, orders on the NYSE were literally shouted across the trading floor! The 'open outcry' system wasn't fully replaced by electronic trading until 2006.",
    tryIt: "trading",
  },
  {
    title: "Portfolio Basics",
    icon: "\ud83d\udcbc",
    intro:
      "A portfolio is your collection of investments. Building a good portfolio isn't about picking the hottest stock — it's about creating a balanced mix that grows your wealth while managing risk.",
    bullets: [
      "Diversification means spreading investments across different assets, sectors, and geographies. If tech stocks drop 20%, your healthcare and utility holdings may cushion the blow significantly.",
      "Asset allocation is the strategic mix of stocks, bonds, cash, and alternatives. A common rule of thumb: subtract your age from 110 — that's your stock percentage (30yo → 80% stocks, 20% bonds).",
      "Rebalancing means periodically adjusting back to target allocations. If stocks surge and become 90% of a 70/30 portfolio, you'd sell some stocks and buy bonds to rebalance back to 70/30.",
      "Risk tolerance is personal: it's how much volatility you can handle both emotionally AND financially. A 30% portfolio drop that causes panic selling is worse than a conservative portfolio that lets you sleep at night.",
      "Correlation matters: owning 10 tech stocks isn't real diversification since they tend to move together. True diversification means holding assets with LOW correlation to each other.",
    ],
    proTip:
      "Start simple: a three-fund portfolio (US stocks, international stocks, bonds via low-cost index funds) beats most actively managed portfolios and requires minimal maintenance.",
    funFact:
      "Warren Buffett bet $1 million in 2007 that a simple S&P 500 index fund would beat a portfolio of hedge funds over 10 years. He won convincingly — the index returned 125% vs the hedge funds' 36%!",
    tryIt: "portfolio",
  },
  {
    title: "Dividends & Income",
    icon: "\ud83d\udcb0",
    intro:
      "Dividends are cash payments companies make to shareholders from their profits. They're one of the most reliable ways to generate passive income from investments, and historically account for about 40% of total stock market returns.",
    bullets: [
      "Dividend yield = annual dividend ÷ share price. A stock paying $2/year at $50/share has a 4% yield. High yields (>6%) can be attractive but may also signal the market expects a dividend cut.",
      "Ex-dividend date is the critical date: you must own the stock BEFORE this date to receive the upcoming dividend. On the ex-date, the stock price typically drops by roughly the dividend amount.",
      "Dividend reinvestment (DRIP) automatically uses dividends to buy more shares, creating a compounding effect. $10,000 invested in the S&P 500 in 1960 would be worth ~$70K without dividends but ~$800K with DRIP!",
      "Dividend Aristocrats are S&P 500 companies that have increased dividends for 25+ consecutive years. These include names like Coca-Cola, Procter & Gamble, and 3M — reliability you can count on.",
      "Growth companies (like many tech firms) typically reinvest profits instead of paying dividends. There's no right or wrong — dividend stocks provide income stability while growth stocks offer higher potential appreciation.",
    ],
    proTip:
      "Look at the payout ratio (dividends ÷ earnings). A ratio above 80% means the company is paying out most of its profits, which may not be sustainable. A healthy range is 30-60%.",
    funFact:
      "Coca-Cola has paid a dividend every quarter since 1920 and increased it for 61 consecutive years! Warren Buffett's Berkshire Hathaway receives over $700 million annually in Coke dividends alone.",
  },
  {
    title: "Reading Financial News",
    icon: "\ud83d\udcf0",
    intro:
      "Financial news moves markets — but not all news is created equal. Learning to filter signal from noise is a critical skill that separates successful investors from reactive ones.",
    bullets: [
      "Earnings reports are quarterly scorecards: EPS (earnings per share) and revenue vs. analyst consensus expectations. A 'beat' means results exceeded expectations; a 'miss' means they fell short.",
      "Forward guidance is often MORE important than actual results. A company can beat earnings but tank if they lower next quarter's outlook, since stocks are priced on future expectations.",
      "Economic indicators to track: CPI (inflation), jobs report (first Friday monthly), GDP (quarterly), Fed meeting statements (8x/year). These move entire markets, not just individual stocks.",
      "Be wary of clickbait and fear-mongering headlines. Financial media profits from engagement, not from making you a better investor. Cross-reference claims across Reuters, Bloomberg, and SEC filings.",
      "Pre-market (4-9:30am ET) and after-hours (4-8pm ET) moves on earnings reports often reverse by the next day's close. Don't panic-react to after-hours moves without reading the full report.",
    ],
    proTip:
      "Set up a routine: check pre-market futures, scan headlines for holdings, review the economic calendar weekly. 15 minutes of focused reading beats hours of doomscrolling financial Twitter.",
    funFact:
      "In 2013, a fake AP tweet about explosions at the White House caused a $136 billion flash crash in the S&P 500 within seconds. The market recovered within 3 minutes — algorithmic trading amplified the fake news!",
  },
  {
    title: "Risk Management Basics",
    icon: "\ud83d\udee1\ufe0f",
    intro:
      "Risk management is the single most important skill in investing. It's not about avoiding risk — it's about understanding, quantifying, and controlling it. The best traders aren't the best stock-pickers; they're the best risk managers.",
    bullets: [
      "The #1 rule: never invest money you can't afford to lose. Your emergency fund (3-6 months expenses) should be in a savings account, not the stock market. Invest only discretionary capital.",
      "Position sizing limits each trade to 1-5% of your total portfolio. If you have $10K, no single position should be more than $500-1000. This ensures no single mistake can devastate your portfolio.",
      "Stop-losses aren't optional — they're insurance. Set them at logical levels (below support lines, below moving averages) not arbitrary percentages. A 2:1 reward-to-risk ratio is a solid minimum target.",
      "Paper trading (simulated trading with virtual money) is the safest way to learn. Spend at least 1-3 months paper trading to develop your strategy before risking real capital.",
      "Emotional discipline is everything: have a written trading plan before entering any position. Define your entry, stop-loss, and target BEFORE you click buy. If the setup doesn't meet your criteria, walk away.",
    ],
    proTip:
      "Keep a trading journal — log every trade with your reasoning, entry/exit prices, and emotional state. After 50+ trades, patterns will emerge that reveal your strengths and weaknesses.",
    funFact:
      "Legendary trader Paul Tudor Jones reportedly tapes a note above his desk that reads: 'LOSERS AVERAGE LOSERS' — a reminder to never add to a losing position hoping it'll come back.",
  },
];

/** Intermediate-level topics for traders with some experience. */
const INTERMEDIATE_TOPICS = [
  {
    title: "Technical Indicators",
    icon: "\ud83d\udd2c",
    intro:
      "Technical indicators are mathematical calculations based on price, volume, or open interest. They help traders identify trends, measure momentum, and find potential entry/exit points — think of them as your trading dashboard instruments.",
    bullets: [
      "Moving Averages (SMA/EMA): SMA gives equal weight to all periods; EMA weights recent prices more. The 50-day and 200-day are institutional benchmarks. A 'Golden Cross' (50 crosses above 200) is a powerful bullish signal.",
      "RSI (Relative Strength Index): oscillates 0-100 measuring speed of price changes. Above 70 = overbought, below 30 = oversold. But in strong trends, RSI can stay overbought/oversold for weeks — don't fade strong momentum blindly.",
      "MACD (Moving Average Convergence Divergence): shows the relationship between two EMAs (12 and 26). Signal line crossovers, histogram direction changes, and divergences from price all provide trading signals.",
      "Bollinger Bands: 20-period SMA with bands at ±2 standard deviations. Bands widen in volatility, narrow in calm ('squeeze'). A squeeze often precedes a big move — combine with other indicators to determine direction.",
      "Volume analysis: the backbone of confirmation. Rising price + rising volume = strong trend. Rising price + falling volume = weak trend likely to reverse. Volume spikes often mark capitulation bottoms or euphoric tops.",
      "Don't overload your chart with indicators! 2-3 complementary indicators (trend + momentum + volume) beat 10 redundant ones that just create analysis paralysis.",
    ],
    proTip:
      "Use indicators as confirmation, not primary decision-makers. Price action (the raw chart) should always come first. If price says one thing and an indicator says another, trust price.",
    funFact:
      "John Bollinger, creator of Bollinger Bands, earned a CFA charter AND a CMT (Chartered Market Technician) — he's one of the few people to hold both technical and fundamental analysis credentials!",
    tryIt: "charts",
  },
  {
    title: "Chart Patterns",
    icon: "\ud83d\udcd0",
    intro:
      "Chart patterns are visual formations that appear repeatedly across all markets and timeframes. They represent the battle between buyers and sellers, and recognizing them early gives you a trading edge.",
    bullets: [
      "Support & Resistance are price levels where buying/selling pressure concentrates. Support is a 'floor' where buyers step in; resistance is a 'ceiling' where sellers appear. Old resistance often becomes new support after a breakout.",
      "Head & Shoulders: three peaks where the middle (head) is highest. The neckline connects the two troughs. A break below the neckline targets a move equal to the distance from head to neckline. Inverse H&S is bullish.",
      "Double Top/Bottom: two peaks at similar levels (double top = bearish) or two troughs (double bottom = bullish). Confirmation requires a break of the neckline between them with above-average volume.",
      "Triangles: ascending (flat top, rising bottom = bullish), descending (flat bottom, falling top = bearish), and symmetrical (converging lines = continuation). They represent decreasing volatility before a breakout.",
      "Cup & Handle: a U-shaped recovery followed by a small pullback (handle), then a breakout. A favorite pattern of growth stock traders — William O'Neil's CANSLIM strategy relies heavily on this pattern.",
      "Flags and Pennants: brief consolidation (1-3 weeks) after a sharp move. Flags are parallel channels; pennants are small triangles. They're continuation patterns — the original trend usually resumes.",
    ],
    proTip:
      "Volume is the key to pattern validity. Breakouts on heavy volume are much more reliable than those on light volume. If a pattern breaks out on decreasing volume, be skeptical.",
    funFact:
      "Chartist Thomas Bulkowski analyzed over 53,000 chart patterns and published his findings in the 'Encyclopedia of Chart Patterns.' He found that head & shoulders patterns have a failure rate of only 14% — among the most reliable!",
  },
  {
    title: "Fundamental Analysis",
    icon: "\ud83d\udcb1",
    intro:
      "Fundamental analysis examines a company's financials to determine its intrinsic value. If a stock trades below its intrinsic value, it's potentially undervalued — the core philosophy of value investing pioneered by Benjamin Graham and Warren Buffett.",
    bullets: [
      "P/E Ratio = Price ÷ Earnings Per Share. A P/E of 20 means you're paying $20 for every $1 of earnings. The S&P 500 average is ~20. Below 15 may be 'cheap,' above 25 may be 'expensive' — but context matters immensely.",
      "PEG Ratio = P/E ÷ Annual Earnings Growth Rate. A PEG of 1 means you're paying fair value for growth. Under 1 = potentially undervalued growth. Over 2 = potentially overpriced. This is Peter Lynch's favorite metric.",
      "Price-to-Book (P/B) compares market value to book value (net assets). P/B < 1 means the market values the company below its liquidation value — could be a bargain or a value trap. Banks and insurers commonly use P/B.",
      "Debt-to-Equity measures financial leverage. D/E of 0.5 means $0.50 of debt for every $1 of equity. High D/E (>2) can be dangerous in downturns as interest payments consume cash flow. Tech firms often have low D/E.",
      "Free Cash Flow (FCF) = Operating Cash Flow - Capital Expenditures. This is the 'real' money a company generates after maintaining its business. Positive and growing FCF is one of the best signs of financial health.",
      "Always compare metrics within the same sector. A P/E of 30 is expensive for a utility company but cheap for a high-growth SaaS company. Industry context is everything.",
    ],
    proTip:
      "Don't rely on a single metric. A stock with low P/E might have high debt and declining revenue. Build a 'scorecard' of 5-6 metrics and evaluate the full picture before investing.",
    funFact:
      "Benjamin Graham, the 'father of value investing,' bought shares of GEICO in 1948 for roughly $712,000. By the time of his death in 1976, that investment was worth $400 million — a 56,000% return!",
  },
  {
    title: "Sector Analysis",
    icon: "\ud83c\udfed",
    intro:
      "The stock market isn't monolithic — it's composed of 11 distinct sectors that behave differently depending on economic conditions. Understanding sector rotation gives you a macro edge that pure stock pickers often miss.",
    bullets: [
      "The 11 GICS sectors: Information Technology (XLK), Health Care (XLV), Financials (XLF), Consumer Discretionary (XLY), Communication Services (XLC), Industrials (XLI), Consumer Staples (XLP), Energy (XLE), Utilities (XLU), Real Estate (XLRE), Materials (XLB).",
      "Sector rotation follows the economic cycle: early recovery favors Financials and Consumer Discretionary; mid-cycle favors Tech and Industrials; late-cycle favors Energy and Materials; recession favors Utilities and Staples.",
      "Defensive sectors (Utilities, Consumer Staples, Health Care) sell essentials people need regardless of the economy. They outperform in recessions but lag in bull markets. Think: electricity bills, toothpaste, medicine.",
      "Cyclical sectors (Tech, Consumer Discretionary, Industrials) amplify economic growth but also amplify downturns. They're exciting in bull markets but can fall 40-60% in bear markets.",
      "Sector ETFs allow you to express a view on an entire sector with one trade. XLK for tech, XLF for banks, XLE for oil — these are often more liquid and less risky than picking individual stocks within a sector.",
      "Monitor sector relative strength by comparing sector ETF performance. Money flows from weak sectors to strong ones. When leadership changes (e.g., from Tech to Energy), it often signals a broader market shift.",
    ],
    proTip:
      "Use TickerTap's Research page sector heatmap to quickly spot which sectors are hot and which are cold. One glance saves you 30 minutes of research across multiple sources.",
    funFact:
      "During the 2020 COVID crash, the Energy sector (XLE) fell 60% while Technology (XLK) ended the year UP 44%. That's a 104 percentage point spread between sectors in the same year!",
    tryIt: "research",
  },
  {
    title: "Options Basics",
    icon: "\u2696\ufe0f",
    intro:
      "Options are contracts that give you the RIGHT (but not obligation) to buy or sell a stock at a specific price before a specific date. They're powerful tools for leverage, hedging, and generating income — but they require proper education.",
    bullets: [
      "Call option = right to BUY at the strike price. You profit when the stock rises above strike + premium paid. Calls are like a deposit on a house — you lock in the price without committing full capital upfront.",
      "Put option = right to SELL at the strike price. You profit when the stock falls below strike - premium paid. Puts act as portfolio insurance — owning puts on your stocks limits your downside risk.",
      "Premium is the price of the option contract, determined by intrinsic value (how far in/out of the money) + time value (time until expiration). Options are priced per share but sold in lots of 100.",
      "Time decay (Theta) erodes option value every day, accelerating as expiration appREDACTEDes. This is why 80% of options expire worthless — time is always working against option buyers and for option sellers.",
      "The Greeks: Delta (price sensitivity), Gamma (delta's rate of change), Theta (time decay), Vega (volatility sensitivity). Understanding these is like having a dashboard — you know exactly how your position will behave.",
      "Covered calls: if you own 100 shares, sell a call against them to collect premium income. You cap your upside but generate consistent income. This is one of the safest and most popular options strategies for beginners.",
    ],
    proTip:
      "Never risk money you can't afford to lose on options. Start with paper trading, learn the Greeks, and begin with simple strategies (covered calls, cash-secured puts) before attempting complex trades.",
    funFact:
      "Options have existed since ancient Greece! Philosopher Thales reportedly purchased options on olive presses before a predicted bumper harvest. When the harvest came, he rented the presses at a premium — the first known options trade!",
  },
  {
    title: "Fair Value Gap (FVG) Trading",
    icon: "\ud83e\uddf2",
    intro:
      "Fair Value Gaps are areas on a chart where price moved so quickly that it left an 'imbalanced' zone — a gap between candles where no two-sided trading occurred. These gaps act as magnets, with price often returning to fill them.",
    bullets: [
      "An FVG forms with three consecutive candles: the gap exists between candle 1's high/low and candle 3's low/high, where candle 2's body 'jumps' through without overlap. It's a zone of inefficiency the market wants to correct.",
      "Bullish FVG: gap between candle 1's high and candle 3's low during an upward move. This gap becomes a support zone where buyers are expected to step in when price returns to fill it.",
      "Bearish FVG: gap between candle 1's low and candle 3's high during a downward move. This gap becomes a resistance zone where sellers are expected to defend when price rallies back into it.",
      "The best FVG trades combine with the higher-timeframe trend. A bullish FVG on the 1-hour chart in an uptrending daily chart is a high-probability setup. Against the trend, FVGs are less reliable.",
      "Not all FVGs get filled — some never return to the gap zone, especially in strong trending markets. Use FVGs as confluence with other analysis (support/resistance, Fibonacci, order blocks) rather than as standalone signals.",
      "FVG trading is central to ICT (Inner Circle Trader) methodology and smart money concepts. It's based on the idea that institutional traders leave 'footprints' that can be tracked and exploited.",
    ],
    proTip:
      "Mark FVGs on higher timeframes (4H, Daily) for the most reliable setups. Lower timeframe FVGs (5m, 15m) are more frequent but less significant. Quality over quantity applies here.",
    funFact:
      "The concept of Fair Value Gaps gained massive popularity on YouTube and TikTok around 2021-2022, leading to what some traders call the 'ICT revolution' — millions of retail traders now use these institutional concepts!",
  },
  {
    title: "Backtesting Strategies",
    icon: "\u23ea",
    intro:
      "Backtesting means running your trading strategy against historical data to see how it would have performed. It's the single best way to validate (or invalidate) a strategy before risking real money. Think of it as a flight simulator for traders.",
    bullets: [
      "Key metrics to track: Total Return, Sharpe Ratio (risk-adjusted return; >1 is good, >2 is excellent), Maximum Drawdown (worst peak-to-trough decline), Win Rate (% of profitable trades), and Profit Factor (gross profit ÷ gross loss).",
      "Walk-forward analysis splits data into in-sample (optimize) and out-of-sample (validate) periods. If your strategy only works on in-sample data, it's overfit — it memorized the past rather than learning a pattern.",
      "Always account for realistic trading costs: commissions, slippage (difference between expected and actual fill price), and bid-ask spread. A strategy profitable on paper may lose money after costs.",
      "Survivorship bias: most historical databases only include stocks that still exist today, excluding companies that went bankrupt or were delisted. This makes backtest results look better than reality.",
      "Overfitting is the #1 backtesting trap: if you keep tweaking parameters until the backtest looks perfect, you've fit noise, not signal. A robust strategy works across multiple markets, timeframes, and time periods.",
      "Past performance doesn't guarantee future results — this isn't just a legal disclaimer, it's a fundamental truth. Use backtests as ONE input alongside forward testing, paper trading, and logical analysis.",
    ],
    proTip:
      "Use TickerTap's AI strategy tools to backtest ideas quickly. Always test on at least 3-5 years of data and across different market conditions (bull, bear, sideways) before considering live trading.",
    funFact:
      "Renaissance Technologies' Medallion Fund, the most successful quant fund in history, reportedly backtests strategies on data going back to the 1700s for some instruments. They've averaged 66% annual returns before fees since 1988!",
  },
];

/** Advanced-level topics for experienced traders and analysts. */
const ADVANCED_TOPICS = [
  {
    title: "Advanced Technical Analysis",
    icon: "\ud83c\udfaf",
    intro:
      "Beyond basic indicators lies a deeper layer of technical analysis used by professional traders. These advanced tools reveal hidden structure, project price targets, and identify high-probability setups invisible to novices.",
    bullets: [
      "Fibonacci retracements (23.6%, 38.2%, 50%, 61.8%, 78.6%) project levels where pullbacks in a trend are likely to find support/resistance. The 61.8% 'golden ratio' is statistically the most respected level across all markets.",
      "Ichimoku Cloud: an all-in-one indicator showing support, resistance, trend direction, momentum, and signal crossovers simultaneously. The cloud (Kumo) itself acts as dynamic support/resistance — price above the cloud is bullish, below is bearish.",
      "Elliott Wave Theory proposes that markets move in predictable 5-wave impulse patterns (trending) followed by 3-wave corrections (counter-trend). Wave 3 is typically the longest and strongest — the sweet spot for traders.",
      "Volume Profile shows trading activity distributed across price levels rather than time. The Point of Control (POC) is the price with the most volume — it acts as a powerful magnet. Value Area (70% of volume) defines fair value.",
      "Market structure analysis: Higher Highs + Higher Lows = uptrend. Lower Highs + Lower Lows = downtrend. A 'break of structure' (BOS) where this pattern is violated often signals a trend change.",
      "Multi-timeframe confluence: find your bias on the weekly/daily, your setup on the 4H, and your entry on the 1H/15m. When all timeframes align, the probability of a successful trade increases dramatically.",
    ],
    proTip:
      "Master ONE advanced technique at a time. Spend 2-3 months trading with Fibonacci before adding Ichimoku. Stacking techniques before understanding each one deeply leads to conflicting signals and confusion.",
    funFact:
      "The Fibonacci sequence appears everywhere in nature — flower petals, hurricane spirals, galaxy arms, and DNA molecules. That the same mathematical ratios appear in financial markets suggests a deep connection to natural growth patterns.",
    tryIt: "charts",
  },
  {
    title: "Algorithmic Trading Concepts",
    icon: "\ud83e\udd16",
    intro:
      "Algorithmic trading uses computer programs to execute trades based on predefined rules. It removes emotion from the equation and can process information faster than any human. Today, algos account for roughly 70% of all US equity trading volume.",
    bullets: [
      "Signal generation converts indicator conditions into actionable buy/sell signals. Example: 'BUY when RSI crosses above 30 AND price is above 200-day SMA AND MACD histogram turns positive.' The more conditions, the fewer but higher-quality signals.",
      "Strategy composition combines multiple uncorrelated signals for higher confidence. A mean-reversion signal + a momentum signal can complement each other, catching different market conditions and smoothing equity curves.",
      "Risk-reward ratio ensures potential profit exceeds potential loss. A minimum 2:1 ratio means your target is 2x your stop-loss. Even with a 40% win rate, a 2:1 R:R makes you profitable: (0.4 × $2) - (0.6 × $1) = +$0.20 per dollar risked.",
      "Position sizing algorithms: Fixed Fractional (risk 1% of capital per trade), Kelly Criterion (mathematically optimal but aggressive), ATR-based (adjust size to volatility). Proper sizing is the difference between surviving and blowing up.",
      "Execution strategies: Market orders for urgency, Limit orders for price; TWAP (Time-Weighted Average Price) spreads large orders across time; VWAP (Volume-Weighted) blends with market volume to minimize market impact.",
      "Monitoring and safety: real-time P&L tracking, maximum daily drawdown limits (auto-flatten at -2%), kill switches for runaway algorithms, and latency monitoring. A bug in production can lose money faster than any human can react.",
    ],
    proTip:
      "Start with simple rule-based strategies before attempting machine learning. A moving average crossover system with proper risk management will teach you more about algo trading than a neural network you don't understand.",
    funFact:
      "In 2010, the 'Flash Crash' saw the Dow Jones drop 1,000 points in 5 minutes due to algorithmic trading feedback loops. $1 trillion in market value vanished and returned within 36 minutes. It led to the creation of circuit breakers.",
  },
  {
    title: "Portfolio Optimization",
    icon: "\ud83e\uddee",
    intro:
      "Portfolio optimization goes beyond simple diversification — it uses mathematical frameworks to find the ideal combination of assets that maximizes expected return for a given level of risk. This is where investing meets quantitative science.",
    bullets: [
      "Modern Portfolio Theory (MPT), developed by Harry Markowitz in 1952, shows that a portfolio's risk isn't just the sum of individual risks — correlations between assets matter more. Two volatile assets can create a low-volatility portfolio if they're negatively correlated.",
      "The Efficient Frontier is a curve plotting the best possible portfolios: each point offers the maximum return for its level of risk. Any portfolio below the frontier is suboptimal — you could get more return for the same risk.",
      "Correlation is the linchpin: assets with correlation near -1 provide the best diversification. Gold and stocks historically have low/negative correlation. Combining them reduces portfolio volatility more than either alone.",
      "Beta measures a stock's volatility relative to the market. Beta=1 means market-like movement; Beta>1 is more volatile; Beta<1 is less. A portfolio beta of 0.7 means you expect 70% of the market's moves (up AND down).",
      "Alpha is the holy grail: excess return above what your risk level (beta) would predict. Positive alpha means you're generating genuine skill-based returns. Most active managers fail to produce consistent alpha after fees.",
      "Sharpe Ratio = (Portfolio Return - Risk-Free Rate) ÷ Standard Deviation. It measures risk-adjusted return. Sharpe >1 is good, >2 is excellent, >3 is rare and exceptional. It lets you compare strategies on equal footing.",
    ],
    proTip:
      "Use TickerTap's portfolio scoring feature to evaluate your portfolio's diversification and risk metrics. It'll highlight concentration risks and suggest improvements based on MPT principles.",
    funFact:
      "Harry Markowitz won the Nobel Prize in Economics in 1990 for MPT. Ironically, when asked how he personally invested, he admitted to a simple 50/50 split between stocks and bonds — not the complex optimization his own theory would suggest!",
    tryIt: "trading",
  },
  {
    title: "Market Microstructure",
    icon: "\ud83d\udd2e",
    intro:
      "Market microstructure is the study of HOW markets actually work at the mechanical level — the order book, matching engines, and the hidden dynamics of price discovery. Understanding this reveals why prices move the way they do.",
    bullets: [
      "The order book is a real-time ledger of all pending buy (bid) and sell (ask) orders. Level 1 shows best bid/ask; Level 2 shows depth (multiple price levels). Large orders visible on L2 can signal institutional intent — or be decoys.",
      "Bid-ask spread is the cost of immediacy: Market buy fills at the ask (higher); market sell fills at the bid (lower). Tight spreads (1 cent on AAPL) = very liquid. Wide spreads ($0.50 on small caps) = illiquid, higher transaction costs.",
      "Market makers are firms that continuously quote buy and sell prices, providing liquidity. They profit from the spread and manage risk through hedging. Citadel Securities and Virtu Financial are the largest in US equity markets.",
      "Dark pools are private venues where large institutional orders execute without showing up on public exchanges. They prevent 'information leakage' — if a fund needs to sell 10 million shares, showing that on a public exchange would crash the price.",
      "High-frequency trading (HFT) firms use co-located servers (physically next to exchange computers) and sub-microsecond execution. They provide liquidity and reduce spreads, but critics argue they exploit speed advantages over regular investors.",
      "Price discovery is the continuous process of determining fair value. Every trade, order, and cancellation contributes to the market's collective intelligence about what a stock is 'worth' at any given moment.",
    ],
    proTip:
      "For retail traders, the key takeaway is: always use limit orders for illiquid stocks, trade during regular market hours for tighter spreads, and be aware that your orders interact with an ecosystem of HFTs and market makers.",
    funFact:
      "The time it takes for light to travel between the NYSE in New York and the CME in Chicago (about 5 milliseconds) is considered TOO SLOW for some HFT firms. They've invested millions in microwave towers and laser networks to shave off microseconds!",
  },
  {
    title: "Macroeconomic Factors",
    icon: "\ud83c\udf0d",
    intro:
      "Macroeconomic forces are the tides that lift or sink all boats. Interest rates, inflation, GDP growth, and geopolitics create the backdrop against which all companies operate. Ignoring macro is like sailing without checking the weather.",
    bullets: [
      "Federal Reserve interest rate policy is the single most powerful market force. Low rates boost stocks (cheap borrowing, low discount rate for valuations). High rates hurt stocks (expensive debt, bonds become competitive). 'Don't fight the Fed.'",
      "The yield curve plots interest rates across bond maturities. Normal: longer maturities have higher yields (upward slope). Inverted: short-term yields exceed long-term — this has predicted every US recession since 1955 with a 12-18 month lead.",
      "Inflation (measured by CPI and PCE) has a Goldilocks zone: 2% is 'just right' per the Fed. Above 4% erodes purchasing power and forces rate hikes. Deflation (falling prices) is actually worse — it discourages spending and investment.",
      "Currency strength: a strong dollar hurts US multinationals (foreign revenue converts to fewer dollars) but helps importers. A weak dollar has the opposite effect. About 40% of S&P 500 revenue comes from international markets.",
      "Geopolitical events (wars, trade disputes, sanctions, elections) inject uncertainty. Markets hate uncertainty more than bad news — a definitive bad outcome is often better for stocks than prolonged ambiguity.",
      "Intermarket analysis: bonds, currencies, commodities, and stocks are interconnected. Rising oil -> inflation fears -> bond yields rise -> growth stocks fall. Understanding these linkages gives you a framework for macro positioning.",
    ],
    proTip:
      "Track the FRED (Federal Reserve Economic Data) calendar for key releases. The most market-moving events are: Fed rate decisions, Non-Farm Payrolls, CPI, and GDP. Position around these events or step aside entirely.",
    funFact:
      "The inverted yield curve predicted COVID's recession in 2019 — before anyone knew a pandemic was coming! The curve inverted in August 2019, and the recession began in February 2020. Whether it 'predicted' the pandemic or would have caused a recession anyway remains debated.",
  },
  {
    title: "Psychology & Behavioral Finance",
    icon: "\ud83e\udde0",
    intro:
      "The biggest threat to your portfolio isn't a market crash — it's the three-pound organ between your ears. Behavioral finance studies how psychological biases cause investors to make irrational decisions, and understanding them is your best defense.",
    bullets: [
      "Confirmation bias: you unconsciously seek information that supports your existing beliefs and ignore contradictory evidence. If you're bullish on a stock, you'll notice every positive headline and dismiss every warning sign.",
      "Loss aversion: losing $100 feels about 2.5× worse than gaining $100 feels good (Kahneman & Tversky, 1979). This causes people to hold losers too long (avoiding the pain of realizing a loss) and sell winners too early (locking in the pleasure of a gain).",
      "Anchoring: fixating on irrelevant reference points. 'I won't sell below my purchase price' — the market doesn't know or care what you paid. Your entry price is irrelevant to the stock's current prospects.",
      "Herd mentality: buying because everyone else is buying (FOMO) or selling because everyone is panicking (capitulation). The crowd is usually right during trends but catastrophically wrong at inflection points.",
      "Overconfidence: studies show ~80% of investors believe they're above-average traders (statistically impossible). This leads to overtrading, insufficient diversification, and ignoring risk management rules.",
      "Recency bias: overweighting recent events. After a bull market, people expect it to continue forever. After a crash, they expect another crash. Reality: markets are mean-reverting and full of surprises in both directions.",
    ],
    proTip:
      "Maintain a trading journal where you record your emotional state alongside each trade: 'Felt FOMO,' 'Panicked,' 'Overconfident.' After 50+ entries, you'll clearly see which emotions hurt your returns and can build rules to counteract them.",
    funFact:
      "Daniel Kahneman, who won the Nobel Prize in Economics for his work on behavioral biases, admitted he's personally terrible at investing. He said: 'My intuitions about the market are the same as everyone else's — and they're wrong just as often!'",
  },
];

/* ── Tab configuration — maps tab IDs to display info and content ──────── */
const TABS = [
  { id: "beginner", label: "BEGINNER", color: GREEN, topics: BEGINNER_TOPICS },
  { id: "intermediate", label: "INTERMEDIATE", color: AMBER, topics: INTERMEDIATE_TOPICS },
  { id: "advanced", label: "ADVANCED", color: RED, topics: ADVANCED_TOPICS },
];

/* ═══════════════════════════════════════════════════════════════════════════
   STYLES — inline style objects matching the Bloomberg-terminal aesthetic
═══════════════════════════════════════════════════════════════════════════ */

/** Card container styles — dark glass panel with subtle border. */
const cardStyle = {
  background: "rgba(255,255,255,0.03)",
  border: "1px solid rgba(255,255,255,0.06)",
  borderRadius: 8,
  marginBottom: 10,
  overflow: "hidden",
  transition: "border-color 0.2s",
};

/** Card header — clickable row with title and expand chevron. */
const cardHeaderStyle = {
  padding: "16px 20px",
  fontWeight: 600,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  fontFamily: "var(--font-mono)",
  fontSize: 13,
  letterSpacing: "0.4px",
  color: "var(--bright)",
  transition: "background 0.15s",
};

/** Card body — the expanded content area. */
const cardBodyStyle = {
  padding: "0 20px 20px 20px",
  color: "#94a3b8",
};

/** Individual bullet point inside an expanded card. */
const bulletStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  lineHeight: 1.8,
  paddingLeft: 16,
  position: "relative",
  marginBottom: 6,
};

/** Amber dot marker for bullet points. */
const bulletDotStyle = {
  position: "absolute",
  left: 0,
  color: AMBER,
  fontWeight: "bold",
};

/** PRO TIP callout box style — amber accent. */
const proTipStyle = {
  background: "rgba(245, 158, 11, 0.06)",
  borderLeft: `3px solid ${AMBER}`,
  borderRadius: "0 6px 6px 0",
  padding: "12px 16px",
  marginTop: 14,
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  lineHeight: 1.7,
  color: "#d4d4d8",
};

/** DID YOU KNOW callout box style — cyan accent. */
const funFactStyle = {
  background: "rgba(6, 182, 212, 0.06)",
  borderLeft: `3px solid ${CYAN}`,
  borderRadius: "0 6px 6px 0",
  padding: "12px 16px",
  marginTop: 10,
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  lineHeight: 1.7,
  color: "#d4d4d8",
};

/** Try-it navigation link style. */
const tryItStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  marginTop: 14,
  fontFamily: "var(--font-mono)",
  fontSize: 10,
  letterSpacing: "0.5px",
  color: AMBER,
  cursor: "pointer",
  opacity: 0.8,
  transition: "opacity 0.15s",
};

/** Intro paragraph style. */
const introStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: 11.5,
  lineHeight: 1.8,
  color: "#b0b8c8",
  marginBottom: 14,
  paddingBottom: 12,
  borderBottom: "1px solid rgba(255,255,255,0.04)",
};

/* ═══════════════════════════════════════════════════════════════════════════
   HELPERS
═══════════════════════════════════════════════════════════════════════════ */

/**
 * loadProgress — read learning progress from localStorage.
 * @returns {Object} mapping of "tabId-topicIdx" → true for completed topics
 */
function loadProgress() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

/**
 * saveProgress — persist learning progress to localStorage.
 * @param {Object} progress - mapping of "tabId-topicIdx" → true
 */
function saveProgress(progress) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch {
    /* localStorage full or blocked — silently ignore */
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   COMPONENT
═══════════════════════════════════════════════════════════════════════════ */

export default function LearningPage({ token, setPage }) {
  /* Active difficulty tab */
  const [activeTab, setActiveTab] = useState("beginner");

  /* Index of the currently expanded accordion card (-1 = all collapsed) */
  const [openIdx, setOpenIdx] = useState(0);

  /* Progress tracking: keys are "tabId-topicIdx", values are true */
  const [progress, setProgress] = useState(() => loadProgress());

  /* Persist progress whenever it changes */
  useEffect(() => {
    saveProgress(progress);
  }, [progress]);

  /**
   * toggleCard — expand or collapse an accordion topic card.
   * @param {number} idx - index of the card to toggle
   */
  const toggleCard = useCallback((idx) => {
    setOpenIdx((prev) => (prev === idx ? -1 : idx));
  }, []);

  /**
   * handleTabChange — switch difficulty level and reset accordion.
   * @param {string} tabId - one of "beginner", "intermediate", "advanced"
   */
  const handleTabChange = useCallback((tabId) => {
    setActiveTab(tabId);
    setOpenIdx(0);
  }, []);

  /**
   * toggleComplete — mark/unmark a topic as read.
   * @param {string} key - "tabId-topicIdx" identifier
   */
  const toggleComplete = useCallback((key) => {
    setProgress((prev) => {
      const next = { ...prev };
      if (next[key]) {
        delete next[key];
      } else {
        next[key] = true;
      }
      return next;
    });
  }, []);

  /**
   * handleTryIt — navigate to a related page within TickerTap.
   * @param {string} page - page identifier (charts, trading, portfolio, etc.)
   */
  const handleTryIt = useCallback(
    (page) => {
      if (setPage) setPage(page);
    },
    [setPage],
  );

  /* Resolve the current tab's config and topic list */
  const currentTab = TABS.find((t) => t.id === activeTab);
  const topics = currentTab?.topics || [];

  /* Calculate progress for each tab */
  const getTabProgress = (tabId, topicCount) => {
    let done = 0;
    for (let i = 0; i < topicCount; i++) {
      if (progress[`${tabId}-${i}`]) done++;
    }
    return done;
  };

  const currentDone = getTabProgress(activeTab, topics.length);

  return (
    <div className="page-scroll">
      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="page-header">
        <div>
          <div className="page-title">LEARNING CENTER</div>
          <div className="page-sub">
            EDUCATIONAL RESOURCES FOR TRADERS & INVESTORS
          </div>
        </div>
      </div>

      <div className="page-inner">
        {/* ── Difficulty level tab bar ────────────────────────────────────── */}
        <div className="filter-bar" style={{ marginBottom: 12 }}>
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            const tabDone = getTabProgress(tab.id, tab.topics.length);
            const tabTotal = tab.topics.length;
            return (
              <button
                key={tab.id}
                className={`filter-btn${isActive ? " active" : ""}`}
                onClick={() => handleTabChange(tab.id)}
                style={isActive ? {
                  background: tab.color,
                  color: tab.id === "intermediate" ? "#000" : "#fff",
                  borderColor: tab.color,
                } : {}}
              >
                {/* Level indicator dot */}
                <span
                  style={{
                    display: "inline-block",
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: tab.color,
                    marginRight: 8,
                    flexShrink: 0,
                  }}
                />
                {tab.label}
                {/* Completion badge */}
                {tabDone > 0 && (
                  <span
                    style={{
                      marginLeft: 8,
                      fontFamily: "var(--font-mono)",
                      fontSize: 9,
                      background: isActive ? "rgba(0,0,0,0.2)" : "rgba(255,255,255,0.06)",
                      padding: "2px 6px",
                      borderRadius: 4,
                      color: isActive ? (tab.id === "intermediate" ? "#000" : "#fff") : tab.color,
                    }}
                  >
                    {tabDone}/{tabTotal}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* ── Progress bar ────────────────────────────────────────────────── */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginBottom: 16,
          }}
        >
          <div
            style={{
              flex: 1,
              height: 4,
              background: "rgba(255,255,255,0.06)",
              borderRadius: 2,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${topics.length > 0 ? (currentDone / topics.length) * 100 : 0}%`,
                height: "100%",
                background: currentTab?.color || AMBER,
                borderRadius: 2,
                transition: "width 0.3s ease",
              }}
            />
          </div>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 10,
              color: "var(--muted)",
              letterSpacing: "0.5px",
              whiteSpace: "nowrap",
            }}
          >
            {currentDone}/{topics.length} COMPLETED · {currentTab?.label} LEVEL
          </span>
        </div>

        {/* ── Accordion topic cards ──────────────────────────────────────── */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          {topics.map((topic, idx) => {
            const isOpen = openIdx === idx;
            const progressKey = `${activeTab}-${idx}`;
            const isDone = !!progress[progressKey];
            return (
              <div
                key={`${activeTab}-${idx}`}
                style={{
                  ...cardStyle,
                  borderColor: isOpen
                    ? `${currentTab.color}33`
                    : "rgba(255,255,255,0.06)",
                }}
              >
                {/* Card header — click to expand/collapse */}
                <div
                  onClick={() => toggleCard(idx)}
                  style={{
                    ...cardHeaderStyle,
                    background: isOpen
                      ? "rgba(255,255,255,0.02)"
                      : "transparent",
                  }}
                  onMouseOver={(e) => {
                    if (!isOpen) e.currentTarget.style.background = "rgba(255,255,255,0.015)";
                  }}
                  onMouseOut={(e) => {
                    if (!isOpen) e.currentTarget.style.background = "transparent";
                  }}
                >
                  {/* Topic icon + number + title */}
                  <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    {/* Emoji icon */}
                    <span style={{ fontSize: 16, lineHeight: 1 }}>{topic.icon}</span>
                    {/* Topic number */}
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 10,
                        color: currentTab.color,
                        fontWeight: 700,
                        minWidth: 20,
                      }}
                    >
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    {topic.title}
                    {/* Completion checkmark */}
                    {isDone && (
                      <span style={{ color: GREEN, fontSize: 12, marginLeft: 4 }}>
                        &#x2713;
                      </span>
                    )}
                  </span>

                  {/* Expand/collapse chevron */}
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      color: "var(--muted)",
                      transition: "transform 0.25s ease",
                      transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
                      flexShrink: 0,
                    }}
                  >
                    &#x25BC;
                  </span>
                </div>

                {/* Card body — animated expand/collapse via max-height */}
                <div
                  style={{
                    maxHeight: isOpen ? 1200 : 0,
                    overflow: "hidden",
                    transition: "max-height 0.3s ease",
                  }}
                >
                  <div style={cardBodyStyle}>
                    {/* Intro paragraph */}
                    {topic.intro && <div style={introStyle}>{topic.intro}</div>}

                    {/* Bullet points */}
                    {topic.bullets.map((bullet, bi) => (
                      <div key={bi} style={bulletStyle}>
                        <span style={bulletDotStyle}>&#x2022;</span>
                        {bullet}
                      </div>
                    ))}

                    {/* PRO TIP callout */}
                    {topic.proTip && (
                      <div style={proTipStyle}>
                        <div
                          style={{
                            fontWeight: 700,
                            fontSize: 10,
                            letterSpacing: "0.8px",
                            color: AMBER,
                            marginBottom: 6,
                          }}
                        >
                          &#x26A0; PRO TIP
                        </div>
                        {topic.proTip}
                      </div>
                    )}

                    {/* DID YOU KNOW callout */}
                    {topic.funFact && (
                      <div style={funFactStyle}>
                        <div
                          style={{
                            fontWeight: 700,
                            fontSize: 10,
                            letterSpacing: "0.8px",
                            color: CYAN,
                            marginBottom: 6,
                          }}
                        >
                          &#x2728; DID YOU KNOW?
                        </div>
                        {topic.funFact}
                      </div>
                    )}

                    {/* Try it in TickerTap link */}
                    {topic.tryIt && (
                      <div
                        style={tryItStyle}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleTryIt(topic.tryIt);
                        }}
                        onMouseOver={(e) => { e.currentTarget.style.opacity = 1; }}
                        onMouseOut={(e) => { e.currentTarget.style.opacity = 0.8; }}
                      >
                        TRY IT IN TICKERTAP &#x2192;
                      </div>
                    )}

                    {/* Mark as read button */}
                    <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleComplete(progressKey);
                        }}
                        style={{
                          background: isDone ? "rgba(34,197,94,0.1)" : "rgba(255,255,255,0.04)",
                          border: `1px solid ${isDone ? "rgba(34,197,94,0.3)" : "rgba(255,255,255,0.08)"}`,
                          borderRadius: 4,
                          padding: "6px 14px",
                          fontFamily: "var(--font-mono)",
                          fontSize: 10,
                          letterSpacing: "0.5px",
                          color: isDone ? GREEN : "var(--muted)",
                          cursor: "pointer",
                          transition: "all 0.15s",
                        }}
                        onMouseOver={(e) => {
                          e.currentTarget.style.background = isDone
                            ? "rgba(34,197,94,0.15)"
                            : "rgba(255,255,255,0.06)";
                        }}
                        onMouseOut={(e) => {
                          e.currentTarget.style.background = isDone
                            ? "rgba(34,197,94,0.1)"
                            : "rgba(255,255,255,0.04)";
                        }}
                      >
                        {isDone ? "\u2713 COMPLETED" : "MARK AS READ"}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
