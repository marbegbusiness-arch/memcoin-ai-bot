"""
🧠 ai_analyzer.py
Claude AI анализирует весь рынок:
- Токены с DexScreener
- Кит-кошельки
- Твиты Трампа/Маска
- Новости
- GMGN безопасность
Выдаёт торговые решения с объяснением
"""

import json
import logging
import os
from anthropic import Anthropic

log = logging.getLogger(__name__)
ai = Anthropic(api_key=os.getenv("ANTHROPIC_KEY", ""))

DEPOSIT = float(os.getenv("DEPOSIT_USD", "20"))


async def analyze_full_market(market_data: dict, positions: dict, daily_pnl: float) -> dict:
    """
    Главный AI-анализ. Получает все рыночные данные,
    возвращает список buy/sell/hold решений.
    """
    tokens   = market_data.get("tokens", [])[:12]
    whales   = market_data.get("whales", [])[:8]
    tweets   = market_data.get("tweets", [])[:6]
    news     = market_data.get("news",   [])[:5]
    sol_p    = market_data.get("sol_price", 150)
    balance  = DEPOSIT + daily_pnl

    # Форматируем открытые позиции
    pos_list = []
    for mint, p in positions.items():
        from src.data_fetcher import get_token_price
        cur = await get_token_price(mint)
        chg = ((cur - p["entry"]) / p["entry"] * 100) if p["entry"] > 0 else 0
        pos_list.append({
            "symbol": p["symbol"], "mint": mint,
            "entry": p["entry"], "current": cur,
            "pnl_pct": round(chg, 1), "invested_usd": p["usd"],
        })

    prompt = f"""You are an elite Solana memecoin trader with deep market knowledge.
Account: ${balance:.2f} USD | SOL price: ${sol_p:.2f}
Open positions: {len(positions)}/3 | Daily PnL: ${daily_pnl:+.2f}

━━━ OPEN POSITIONS ━━━
{json.dumps(pos_list, indent=2)}

━━━ TOP TOKENS FROM DEXSCREENER ━━━
{json.dumps([{
    "symbol": t["symbol"], "mint": t["mint"],
    "price": t["price_usd"], "chg_5m": t["chg_5m"],
    "chg_1h": t["chg_1h"], "vol_24h": t["volume_24h"],
    "liq": t["liquidity"], "mc": t["market_cap"],
    "buys": t["buys_24h"], "sells": t["sells_24h"],
    "age_h": round(t["age_hours"], 1), "dex": t["dex"],
} for t in tokens], indent=2)}

━━━ WHALE WALLET ACTIVITY ━━━
{json.dumps(whales, indent=2)}

━━━ TWITTER SIGNALS (Trump, Musk, Influencers) ━━━
{json.dumps([{"author": t["author"], "text": t["text"][:150],
              "likes": t["likes"], "important": t.get("important", False)} 
             for t in tweets], indent=2)}

━━━ CRYPTO NEWS ━━━
{json.dumps([{"title": n["title"], "source": n.get("source","")} for n in news], indent=2)}

━━━ RULES (STRICT) ━━━
- MAX $20 per trade (${balance*0.20:.1f} = 20% of balance)
- REJECT tokens: honeypot / freeze authority / top10 holders >80% / age <10min / liq <$2000
- REJECT if buys/sells ratio <0.6 (more sellers than buyers)
- BONUS if whale bought in last hour
- BONUS if Elon Musk or Trump mentioned token
- BONUS if trending news about token
- SELL if position PnL < -30% (stop loss)
- SELL if position PnL > +150% (take profit)
- SELL if token becoming rug (liq dropping fast)

Respond ONLY with JSON (no markdown, no explanation):
{{
  "decisions": [
    {{
      "action": "BUY"|"SELL"|"HOLD"|"SKIP",
      "mint": "...",
      "symbol": "...",
      "amount_usd": <number, only for BUY>,
      "confidence": <0-100>,
      "reasons": ["reason1", "reason2"],
      "red_flags": ["flag1"] or [],
      "catalysts": ["whale bought", "elon tweeted"] or [],
      "risk": "LOW"|"MEDIUM"|"HIGH"|"EXTREME"
    }}
  ],
  "market_mood": "BULLISH"|"NEUTRAL"|"BEARISH"|"EXTREME_FEAR"|"EXTREME_GREED",
  "sol_outlook": "one sentence about SOL trend",
  "top_alert": "most important signal right now or empty string",
  "skip_trading": false
}}

Only include actionable decisions. Skip tokens with EXTREME risk unless selling."""

    try:
        resp = ai.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.replace("```json","").replace("```","").strip()
        result = json.loads(raw)
        log.info(f"AI decision: {len(result.get('decisions',[]))} actions | mood: {result.get('market_mood')}")
        return result
    except Exception as e:
        log.error(f"AI analyze error: {e}")
        return {
            "decisions": [], "market_mood": "NEUTRAL",
            "sol_outlook": "AI error", "top_alert": "", "skip_trading": True
        }


async def analyze_token_safety(token: dict, gmgn_data: dict) -> dict:
    """
    Проверка токена на мусор/скам.
    Возвращает safety score 0-100 и список проблем.
    """
    prompt = f"""You are a crypto security expert. Analyze this Solana token for safety.

Token: {token.get('symbol')} | {token.get('name')}
Mint: {token.get('mint')}
Age: {token.get('age_hours', 0):.1f} hours
Market cap: ${token.get('market_cap', 0):,.0f}
Liquidity: ${token.get('liquidity', 0):,.0f}
Volume 24h: ${token.get('volume_24h', 0):,.0f}
Buys/Sells 24h: {token.get('buys_24h',0)}/{token.get('sells_24h',0)}
Price change 1h: {token.get('chg_1h',0):+.1f}%

GMGN Safety Data:
- Honeypot: {gmgn_data.get('is_honeypot', 'unknown')}
- Top 10 holders %: {gmgn_data.get('top10_holders_pct', 'unknown')}
- Freeze authority: {gmgn_data.get('freeze_authority', 'unknown')}
- Mint authority: {gmgn_data.get('mint_authority', 'unknown')}
- Rug score: {gmgn_data.get('rug_score', 'unknown')}
- Holders: {gmgn_data.get('holders', 'unknown')}

Respond ONLY with JSON:
{{
  "safety_score": <0-100, 100=safest>,
  "verdict": "SAFE"|"CAUTION"|"DANGER"|"SCAM",
  "issues": ["issue1", "issue2"],
  "positives": ["positive1"],
  "tradeable": true|false
}}"""

    try:
        r = ai.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(r.content[0].text.replace("```json","").replace("```","").strip())
    except:
        return {"safety_score": 0, "verdict": "DANGER", "issues": ["AI error"], "tradeable": False}


async def generate_market_report(market_data: dict, positions: dict, trades: list, daily_pnl: float) -> str:
    """Генерирует текстовый отчёт о рынке для Telegram"""
    tokens = market_data.get("tokens", [])[:5]
    tweets = market_data.get("tweets", [])[:3]
    mood   = market_data.get("mood", "NEUTRAL")

    prompt = f"""Generate a short Telegram market report in Russian for a memecoin trader.

Data:
- SOL price: ${market_data.get('sol_price', 150):.2f}
- Market mood: {mood}
- Top tokens: {json.dumps([{"s":t["symbol"],"chg":t["chg_1h"],"vol":t["volume_24h"]} for t in tokens])}
- Key tweets: {json.dumps([{"a":t["author"],"t":t["text"][:80]} for t in tweets])}
- Open positions: {len(positions)}
- Daily PnL: ${daily_pnl:+.2f}
- Trades today: {len(trades)}

Write 6-8 lines max. Use emojis. Format for Telegram Markdown.
Include: SOL price, market mood, top movers, important social signals, account status.
Language: Russian."""

    try:
        r = ai.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        return r.content[0].text
    except:
        return f"📊 *Отчёт рынка*\n💰 SOL: ${market_data.get('sol_price',150):.2f}\n📈 PnL: ${daily_pnl:+.2f}"
