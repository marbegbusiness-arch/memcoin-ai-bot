"""
📡 data_fetcher.py
Сбор данных из всех источников:
- DexScreener (токены, ликвидность, объём)
- GMGN.ai (новые токены, безопасность)
- Whale wallets (кит-кошельки Solana)
- Twitter/X (Трамп, Маск, крипто-инфлюенсеры)
- Новости (CoinDesk, CryptoPanic)
"""

import aiohttp
import asyncio
import logging
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HELIUS_KEY = os.getenv("HELIUS_API_KEY", "")
TWITTER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

# ── Известные кит-кошельки Solana ──────────────────────────
WHALE_WALLETS = {
    "7WUeg8": "Whale #1 (Top Solana Trader)",
    "9xQeWv": "Whale #2 (Pump.fun Early Buyer)",
    "BQ72nS": "Whale #3 (Raydium LP Provider)",
    "DRpbCB": "Whale #4 (Known Memcoin Sniper)",
    "HVmVQu": "Whale #5 (Smart Money Tracker)",
    # Добавляй реальные адреса из Cielo/Birdeye
}

# ── Twitter аккаунты для мониторинга ───────────────────────
TWITTER_ACCOUNTS = {
    "realDonaldTrump": "🇺🇸 Трамп",
    "elonmusk":        "🚀 Илон Маск",
    "CryptoKaleo":     "📊 Kaleo",
    "AltcoinGordon":   "🔥 Gordon",
    "solana":          "◎ Solana Official",
    "pumpdotfun":      "🎰 Pump.fun",
    "Murad_mm":        "💎 Murad",
    "ansem":           "📈 Ansem",
}

# ── Крипто-ключевые слова для фильтра твитов ───────────────
MEMCOIN_KEYWORDS = [
    "solana", "sol", "memecoin", "meme coin", "pump.fun",
    "100x", "gem", "degen", "ape in", "bullish", "moon",
    "new token", "just launched", "raydium", "bonk", "dogwifhat"
]


# ═══════════════════════════════════════════════════════
#  DEXSCREENER
# ═══════════════════════════════════════════════════════

async def fetch_dexscreener_new() -> list:
    """Новые токены Solana с объёмом и ликвидностью"""
    results = []
    try:
        async with aiohttp.ClientSession() as s:
            # Новые пары на Solana
            urls = [
                "https://api.dexscreener.com/latest/dex/search?q=pump",
                "https://api.dexscreener.com/latest/dex/search?q=solana+meme",
                "https://api.dexscreener.com/token-profiles/latest/v1",
            ]
            for url in urls:
                try:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                        if r.status != 200:
                            continue
                        data = await r.json()
                        pairs = data.get("pairs", data if isinstance(data, list) else [])
                        for p in (pairs or []):
                            if isinstance(p, dict) and p.get("chainId") == "solana":
                                vol   = float(p.get("volume", {}).get("h24", 0) or 0)
                                liq   = float(p.get("liquidity", {}).get("usd", 0) or 0)
                                mc    = float(p.get("marketCap", 0) or 0)
                                age_h = _pair_age_hours(p.get("pairCreatedAt", 0))
                                if vol < 3000 or liq < 1000:
                                    continue
                                results.append({
                                    "mint":        p.get("baseToken", {}).get("address", ""),
                                    "symbol":      p.get("baseToken", {}).get("symbol", "?"),
                                    "name":        p.get("baseToken", {}).get("name", ""),
                                    "price_usd":   float(p.get("priceUsd", 0) or 0),
                                    "chg_5m":      float(p.get("priceChange", {}).get("m5",  0) or 0),
                                    "chg_1h":      float(p.get("priceChange", {}).get("h1",  0) or 0),
                                    "chg_6h":      float(p.get("priceChange", {}).get("h6",  0) or 0),
                                    "chg_24h":     float(p.get("priceChange", {}).get("h24", 0) or 0),
                                    "volume_24h":  vol,
                                    "volume_1h":   float(p.get("volume", {}).get("h1", 0) or 0),
                                    "liquidity":   liq,
                                    "market_cap":  mc,
                                    "txns_24h":    (p.get("txns", {}).get("h24", {}).get("buys", 0) +
                                                    p.get("txns", {}).get("h24", {}).get("sells", 0)),
                                    "buys_24h":    p.get("txns", {}).get("h24", {}).get("buys", 0),
                                    "sells_24h":   p.get("txns", {}).get("h24", {}).get("sells", 0),
                                    "age_hours":   age_h,
                                    "dex":         p.get("dexId", ""),
                                    "pair_url":    p.get("url", ""),
                                    "source":      "dexscreener",
                                })
                except Exception as e:
                    log.warning(f"DexScreener url error: {e}")

        # Дедупликация по mint
        seen, unique = set(), []
        for t in results:
            if t["mint"] and t["mint"] not in seen:
                seen.add(t["mint"])
                unique.append(t)

        unique.sort(key=lambda x: x["volume_24h"], reverse=True)
        log.info(f"DexScreener: {len(unique)} tokens found")
        return unique[:30]

    except Exception as e:
        log.error(f"DexScreener fetch error: {e}")
        return []


def _pair_age_hours(created_at_ms) -> float:
    if not created_at_ms:
        return 999
    try:
        created = datetime.fromtimestamp(int(created_at_ms) / 1000)
        return (datetime.now() - created).total_seconds() / 3600
    except:
        return 999


# ═══════════════════════════════════════════════════════
#  GMGN.AI — безопасность токена
# ═══════════════════════════════════════════════════════

async def fetch_gmgn_safety(mint: str) -> dict:
    """Проверка токена на rug pull через GMGN"""
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://gmgn.ai/api/v1/token_info/sol/{mint}"
            headers = {"User-Agent": "Mozilla/5.0"}
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status == 200:
                    d = await r.json()
                    info = d.get("data", {})
                    return {
                        "is_honeypot":      info.get("is_honeypot", False),
                        "top10_holders_pct": info.get("top10_holder_rate", 100),
                        "creator_pct":      info.get("creator_token_status", 0),
                        "freeze_authority": info.get("freeze_authority", True),
                        "mint_authority":   info.get("mint_authority", True),
                        "rug_score":        info.get("rug_ratio", 100),
                        "holders":          info.get("holder_count", 0),
                        "source":           "gmgn",
                    }
    except Exception as e:
        log.warning(f"GMGN error for {mint}: {e}")
    return {"is_honeypot": None, "rug_score": 50, "holders": 0, "source": "gmgn_failed"}


# ═══════════════════════════════════════════════════════
#  WHALE WALLETS — кит-активность
# ═══════════════════════════════════════════════════════

async def fetch_whale_activity() -> list:
    """Последние транзакции кит-кошельков через Helius"""
    activity = []
    if not HELIUS_KEY:
        return _mock_whale_activity()

    try:
        async with aiohttp.ClientSession() as s:
            for addr, label in list(WHALE_WALLETS.items())[:5]:
                url = f"https://api.helius.xyz/v0/addresses/{addr}/transactions?api-key={HELIUS_KEY}&limit=10"
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                    if r.status != 200:
                        continue
                    txns = await r.json()
                    for tx in (txns or []):
                        # Ищем swap-транзакции
                        if tx.get("type") in ("SWAP", "TOKEN_MINT"):
                            mint = _extract_mint_from_tx(tx)
                            if mint:
                                activity.append({
                                    "wallet":    label,
                                    "wallet_addr": addr,
                                    "action":    tx.get("type", "SWAP"),
                                    "mint":      mint,
                                    "amount_sol": tx.get("fee", 0) / 1e9,
                                    "time":      tx.get("timestamp", 0),
                                    "source":    "helius",
                                })
        log.info(f"Whale activity: {len(activity)} txns")
    except Exception as e:
        log.error(f"Whale fetch error: {e}")

    return activity


def _extract_mint_from_tx(tx: dict) -> str:
    try:
        for ins in tx.get("tokenTransfers", []):
            if ins.get("mint"):
                return ins["mint"]
    except:
        pass
    return ""


def _mock_whale_activity() -> list:
    """Заглушка если нет Helius ключа"""
    return [{
        "wallet": "Whale #1 (Demo)",
        "action": "SWAP",
        "mint": "demo_mint",
        "amount_sol": 5.0,
        "time": int(datetime.now().timestamp()),
        "source": "mock",
    }]


# ═══════════════════════════════════════════════════════
#  TWITTER / X — Трамп, Маск, инфлюенсеры
# ═══════════════════════════════════════════════════════

async def fetch_twitter_signals() -> list:
    """Твиты от ключевых аккаунтов через Twitter API v2"""
    signals = []

    if not TWITTER_TOKEN:
        log.warning("Twitter token not set — using RSS fallback")
        return await _fetch_twitter_rss_fallback()

    try:
        import tweepy
        client = tweepy.AsyncClient(bearer_token=TWITTER_TOKEN)

        for username, label in TWITTER_ACCOUNTS.items():
            try:
                user = await client.get_user(username=username)
                if not user.data:
                    continue
                tweets = await client.get_users_tweets(
                    user.data.id,
                    max_results=5,
                    tweet_fields=["created_at", "text", "public_metrics"],
                    start_time=datetime.utcnow() - timedelta(hours=6),
                )
                for tw in (tweets.data or []):
                    text = tw.text.lower()
                    if any(kw in text for kw in MEMCOIN_KEYWORDS):
                        signals.append({
                            "author":    label,
                            "username":  username,
                            "text":      tw.text[:280],
                            "likes":     tw.public_metrics.get("like_count", 0),
                            "retweets":  tw.public_metrics.get("retweet_count", 0),
                            "time":      str(tw.created_at),
                            "source":    "twitter",
                            "important": username in ("realDonaldTrump", "elonmusk"),
                        })
            except Exception as e:
                log.warning(f"Twitter error for {username}: {e}")

        signals.sort(key=lambda x: x["likes"], reverse=True)
        log.info(f"Twitter: {len(signals)} relevant tweets")

    except ImportError:
        return await _fetch_twitter_rss_fallback()
    except Exception as e:
        log.error(f"Twitter fetch error: {e}")

    return signals[:10]


async def _fetch_twitter_rss_fallback() -> list:
    """RSS-фид как fallback для Twitter (nitter)"""
    signals = []
    nitter_accounts = ["elonmusk", "realDonaldTrump", "pumpdotfun"]
    try:
        async with aiohttp.ClientSession() as s:
            for acc in nitter_accounts:
                url = f"https://nitter.privacydev.net/{acc}/rss"
                try:
                    async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                        if r.status != 200:
                            continue
                        html = await r.text()
                        soup = BeautifulSoup(html, "lxml-xml")
                        for item in soup.find_all("item")[:3]:
                            text = item.find("title").text if item.find("title") else ""
                            if any(kw in text.lower() for kw in MEMCOIN_KEYWORDS):
                                signals.append({
                                    "author":    acc,
                                    "username":  acc,
                                    "text":      text[:280],
                                    "likes":     0,
                                    "source":    "nitter_rss",
                                    "important": acc in ("realDonaldTrump", "elonmusk"),
                                })
                except:
                    pass
    except Exception as e:
        log.error(f"RSS fallback error: {e}")
    return signals


# ═══════════════════════════════════════════════════════
#  НОВОСТИ — CryptoPanic, CoinDesk
# ═══════════════════════════════════════════════════════

async def fetch_crypto_news() -> list:
    """Последние крипто-новости"""
    news = []
    try:
        async with aiohttp.ClientSession() as s:
            # CryptoPanic (бесплатный API)
            url = "https://cryptopanic.com/api/free/v1/posts/?auth_token=free&filter=hot&currencies=SOL&public=true"
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status == 200:
                    d = await r.json()
                    for item in (d.get("results", []))[:8]:
                        news.append({
                            "title":    item.get("title", ""),
                            "url":      item.get("url", ""),
                            "source":   item.get("source", {}).get("title", ""),
                            "votes_pos": item.get("votes", {}).get("positive", 0),
                            "votes_neg": item.get("votes", {}).get("negative", 0),
                            "time":     item.get("published_at", ""),
                            "type":     "news",
                        })

        # RSS CoinDesk Solana tag
        async with aiohttp.ClientSession() as s:
            rss_url = "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"
            async with s.get(rss_url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    html = await r.text()
                    soup = BeautifulSoup(html, "lxml-xml")
                    for item in soup.find_all("item")[:5]:
                        title = item.find("title").text if item.find("title") else ""
                        if "solana" in title.lower() or "meme" in title.lower():
                            news.append({
                                "title":  title,
                                "url":    item.find("link").text if item.find("link") else "",
                                "source": "CoinDesk",
                                "type":   "news",
                            })

        log.info(f"News: {len(news)} articles")
    except Exception as e:
        log.error(f"News fetch error: {e}")

    return news[:10]


# ═══════════════════════════════════════════════════════
#  SOLANA PRICE
# ═══════════════════════════════════════════════════════

async def get_sol_price() -> float:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                d = await r.json()
                return float(d["solana"]["usd"])
    except:
        return 150.0


async def get_token_price(mint: str) -> float:
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    d = await r.json()
                    pairs = d.get("pairs", [])
                    if pairs:
                        return float(pairs[0].get("priceUsd", 0) or 0)
    except:
        pass
    return 0.0


# ═══════════════════════════════════════════════════════
#  ПОЛНЫЙ СРЕЗ РЫНКА (один вызов = все данные)
# ═══════════════════════════════════════════════════════

async def fetch_all_market_data() -> dict:
    """Параллельный сбор всех данных"""
    log.info("📡 Fetching all market data...")
    tokens, whales, tweets, news, sol_price = await asyncio.gather(
        fetch_dexscreener_new(),
        fetch_whale_activity(),
        fetch_twitter_signals(),
        fetch_crypto_news(),
        get_sol_price(),
        return_exceptions=True
    )

    return {
        "tokens":    tokens    if isinstance(tokens, list)    else [],
        "whales":    whales    if isinstance(whales, list)    else [],
        "tweets":    tweets    if isinstance(tweets, list)    else [],
        "news":      news      if isinstance(news, list)      else [],
        "sol_price": sol_price if isinstance(sol_price, float) else 150.0,
        "fetched_at": datetime.now().isoformat(),
    }
