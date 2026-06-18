"""
🤖 main.py — Solana Memcoin AI Bot
Полный автопилот: DexScreener + Киты + Twitter + Новости + AI
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from src.data_fetcher import (
    fetch_all_market_data, fetch_gmgn_safety,
    get_sol_price, get_token_price
)
from src.ai_analyzer import analyze_full_market, analyze_token_safety, generate_market_report

# ── Config ──────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
USER_ID         = int(os.getenv("TELEGRAM_USER_ID", "0"))
DEPOSIT         = float(os.getenv("DEPOSIT_USD", "20"))
SIM_MODE        = os.getenv("SIMULATION_MODE", "true").lower() == "true"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("logs/bot.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ── Risk settings ────────────────────────────────────────────────
RISK = {
    "max_positions":    3,
    "position_pct":     0.20,     # 20% на сделку
    "stop_loss":        0.30,     # -30%
    "take_profit":      1.50,     # +150%
    "max_daily_loss":   0.40,     # стоп дня -40%
    "scan_interval":    60,       # секунд
    "min_safety_score": 55,       # мин. safety score
}

# ── State ────────────────────────────────────────────────────────
state = {
    "running":       False,
    "positions":     {},
    "trades":        [],
    "daily_pnl":     0.0,
    "scan_count":    0,
    "last_market":   {},
    "last_scan_time": None,
    "alerts":        [],
}


# ══════════════════════════════════════════════════════════════════
#  ТОРГОВЫЙ ЦИКЛ
# ══════════════════════════════════════════════════════════════════

async def trading_loop(app):
    log.info("🚀 Trading loop started")
    while state["running"]:
        try:
            state["scan_count"] += 1
            state["last_scan_time"] = datetime.now().strftime("%H:%M:%S")
            log.info(f"🔍 Scan #{state['scan_count']}")

            # 1. Получаем все данные параллельно
            market = await fetch_all_market_data()
            state["last_market"] = market

            # 2. Проверяем стоп дня
            if state["daily_pnl"] < -DEPOSIT * RISK["max_daily_loss"]:
                state["running"] = False
                await push(app, f"🚨 *СТОП ДНЯ*\nПотеря `{state['daily_pnl']:+.2f}$` превысила лимит.\nБот остановлен до завтра.")
                break

            # 3. Проверяем SL/TP текущих позиций
            for mint in list(state["positions"].keys()):
                await check_position_exit(app, mint, market)

            # 4. Проверяем безопасность токенов (GMGN)
            safe_tokens = []
            for t in market.get("tokens", []):
                if t["mint"] in state["positions"]:
                    continue
                gmgn = await fetch_gmgn_safety(t["mint"])
                safety = await analyze_token_safety(t, gmgn)
                if safety.get("tradeable") and safety.get("safety_score", 0) >= RISK["min_safety_score"]:
                    t["safety"] = safety
                    safe_tokens.append(t)
                else:
                    issues = ", ".join(safety.get("issues", [])[:2])
                    log.info(f"❌ SKIP {t['symbol']} — {safety.get('verdict')} ({issues})")

            market["tokens"] = safe_tokens

            # 5. AI анализ
            ai_result = await analyze_full_market(market, state["positions"], state["daily_pnl"])

            # Важный алерт
            if ai_result.get("top_alert"):
                alert = ai_result["top_alert"]
                state["alerts"].insert(0, {"text": alert, "time": datetime.now().strftime("%H:%M")})
                state["alerts"] = state["alerts"][:20]
                await push(app, f"🔔 *Алерт AI:*\n{alert}")

            # Если рынок опасный — пропускаем торговлю
            if ai_result.get("skip_trading"):
                log.info("⚠️ AI recommends skipping trading this scan")
                await asyncio.sleep(RISK["scan_interval"])
                continue

            # 6. Исполняем решения AI
            slots = RISK["max_positions"] - len(state["positions"])
            for dec in ai_result.get("decisions", []):
                action = dec.get("action")
                mint   = dec.get("mint", "")
                symbol = dec.get("symbol", "?")

                if action == "SELL" and mint in state["positions"]:
                    await close_position(app, mint, "AI решение")

                elif action == "BUY" and slots > 0 and mint not in state["positions"]:
                    amount = min(
                        float(dec.get("amount_usd", 5)),
                        (DEPOSIT + state["daily_pnl"]) * RISK["position_pct"]
                    )
                    if amount >= 1:
                        token_data = next((t for t in safe_tokens if t["mint"] == mint), None)
                        entry = token_data["price_usd"] if token_data else await get_token_price(mint)
                        await open_position(app, mint, symbol, amount, entry, dec)
                        slots -= 1

        except Exception as e:
            log.error(f"Loop error: {e}", exc_info=True)

        await asyncio.sleep(RISK["scan_interval"])


async def check_position_exit(app, mint: str, market: dict):
    pos = state["positions"].get(mint)
    if not pos:
        return
    cur = await get_token_price(mint)
    if cur <= 0:
        return
    chg = (cur - pos["entry"]) / pos["entry"]

    if chg <= -RISK["stop_loss"]:
        await close_position(app, mint, "STOP-LOSS 🛑")
    elif chg >= RISK["take_profit"]:
        await close_position(app, mint, "TAKE-PROFIT 🎯")


async def open_position(app, mint, symbol, amount_usd, entry_price, ai_dec):
    if SIM_MODE:
        log.info(f"[SIM] BUY {symbol} ${amount_usd:.2f} @ ${entry_price:.8f}")
    else:
        # TODO: реальный Jupiter swap
        pass

    state["positions"][mint] = {
        "symbol":   symbol,
        "entry":    entry_price,
        "amount":   amount_usd / max(entry_price, 1e-12),
        "usd":      amount_usd,
        "opened":   datetime.now().strftime("%H:%M:%S"),
        "catalysts": ai_dec.get("catalysts", []),
    }

    reasons   = "\n".join(f"  ✅ {r}" for r in ai_dec.get("reasons", [])[:3])
    catalysts = "\n".join(f"  ⚡ {c}" for c in ai_dec.get("catalysts", [])[:2])
    flags     = "\n".join(f"  ⚠️ {f}" for f in ai_dec.get("red_flags", [])[:2])
    mode_tag  = "🟡 СИМУЛЯЦИЯ" if SIM_MODE else "🟢 РЕАЛЬНАЯ СДЕЛКА"

    text = (
        f"{'─'*30}\n"
        f"🟢 *ПОКУПКА — {symbol}*\n"
        f"{'─'*30}\n"
        f"💰 Сумма: `${amount_usd:.2f}`\n"
        f"📍 Цена входа: `${entry_price:.8f}`\n"
        f"🎯 TP: `+{RISK['take_profit']*100:.0f}%` | SL: `-{RISK['stop_loss']*100:.0f}%`\n"
        f"📊 Уверенность AI: `{ai_dec.get('confidence', 0)}%`\n"
        f"⚠️ Риск: `{ai_dec.get('risk', '?')}`\n"
        f"\n*Причины:*\n{reasons or '  —'}\n"
        f"\n*Катализаторы:*\n{catalysts or '  —'}\n"
        f"{f'*Флаги:*{chr(10)}{flags}' if flags else ''}\n"
        f"\n{mode_tag}"
    )
    await push(app, text)


async def close_position(app, mint, reason):
    pos = state["positions"].get(mint)
    if not pos:
        return
    cur = await get_token_price(mint)
    if cur <= 0:
        cur = pos["entry"]

    pnl_pct = (cur - pos["entry"]) / pos["entry"] * 100
    pnl_usd = pos["usd"] * (pnl_pct / 100)

    if SIM_MODE:
        log.info(f"[SIM] SELL {pos['symbol']} PnL: {pnl_pct:+.1f}% (${pnl_usd:+.2f})")

    state["daily_pnl"] += pnl_usd
    state["trades"].append({
        "symbol":   pos["symbol"],
        "mint":     mint,
        "entry":    pos["entry"],
        "exit":     cur,
        "pnl_pct":  round(pnl_pct, 1),
        "pnl_usd":  round(pnl_usd, 2),
        "invested": pos["usd"],
        "reason":   reason,
        "closed":   datetime.now().strftime("%H:%M:%S"),
    })
    del state["positions"][mint]

    emoji = "✅" if pnl_usd >= 0 else "❌"
    text = (
        f"{'─'*30}\n"
        f"{emoji} *ЗАКРЫТА — {pos['symbol']}*\n"
        f"{'─'*30}\n"
        f"📍 Вход: `${pos['entry']:.8f}`\n"
        f"📍 Выход: `${cur:.8f}`\n"
        f"📊 PnL: `{pnl_pct:+.1f}%` (`${pnl_usd:+.2f}`)\n"
        f"💡 Причина: {reason}\n"
        f"📈 PnL сегодня: `${state['daily_pnl']:+.2f}`"
    )
    await push(app, text)


async def push(app, text: str):
    if USER_ID:
        try:
            await app.bot.send_message(USER_ID, text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            log.error(f"Push error: {e}")


# ══════════════════════════════════════════════════════════════════
#  TELEGRAM HANDLERS
# ══════════════════════════════════════════════════════════════════

def kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Старт",    callback_data="start"),
         InlineKeyboardButton("⏹ Стоп",     callback_data="stop")],
        [InlineKeyboardButton("📊 Позиции",  callback_data="pos"),
         InlineKeyboardButton("💹 Статус",   callback_data="status")],
        [InlineKeyboardButton("💰 Баланс",   callback_data="balance"),
         InlineKeyboardButton("📋 История",  callback_data="history")],
        [InlineKeyboardButton("🔍 Скан",     callback_data="scan"),
         InlineKeyboardButton("📰 Рынок",    callback_data="market")],
        [InlineKeyboardButton("🐋 Киты",     callback_data="whales"),
         InlineKeyboardButton("🐦 Твиттер",  callback_data="tweets")],
        [InlineKeyboardButton("🔔 Алерты",   callback_data="alerts"),
         InlineKeyboardButton("⚙️ Риски",    callback_data="risks")],
    ])


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != USER_ID and USER_ID != 0:
        return
    mode = "🟡 СИМУЛЯЦИЯ (безопасный режим)" if SIM_MODE else "🔴 РЕАЛЬНАЯ ТОРГОВЛЯ"
    await update.message.reply_text(
        f"🤖 *Solana Memcoin AI Bot*\n\n"
        f"Анализирую:\n"
        f"  📡 DexScreener — новые токены\n"
        f"  🐋 Кит-кошельки — умные деньги\n"
        f"  🐦 Twitter — Трамп, Маск, инфлюенсеры\n"
        f"  📰 Новости — CoinDesk, CryptoPanic\n"
        f"  🛡 GMGN.ai — проверка на скам\n\n"
        f"💼 Депозит: `${DEPOSIT}`\n"
        f"📍 Сеть: Solana\n"
        f"🎯 TP: +150% | SL: -30%\n"
        f"🔄 Скан: каждые {RISK['scan_interval']}с\n\n"
        f"Режим: {mode}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb()
    )


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != USER_ID and USER_ID != 0:
        return
    q = update.callback_query
    await q.answer()
    d = q.data

    # ── СТАРТ ──
    if d == "start":
        if state["running"]:
            await q.edit_message_text("⚠️ Бот уже работает!", reply_markup=kb())
            return
        state["running"] = True
        state["daily_pnl"] = 0.0
        asyncio.create_task(trading_loop(ctx.application))
        await q.edit_message_text(
            "✅ *Бот запущен!*\n\n"
            "🔍 Начинаю анализ рынка...\n"
            "⏱ Первый скан через ~30 секунд\n"
            "📬 Уведомления придут при каждой сделке",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kb()
        )

    # ── СТОП ──
    elif d == "stop":
        state["running"] = False
        await q.edit_message_text("⏹ *Бот остановлен.*\nПозиции остаются открытыми.",
                                  parse_mode=ParseMode.MARKDOWN, reply_markup=kb())

    # ── ПОЗИЦИИ ──
    elif d == "pos":
        if not state["positions"]:
            txt = "📭 *Нет открытых позиций*\nБот ищет точки входа..."
        else:
            lines = [f"📊 *Открытые позиции ({len(state['positions'])}/3):*\n"]
            for mint, p in state["positions"].items():
                cur = await get_token_price(mint)
                chg = ((cur - p["entry"]) / p["entry"] * 100) if p["entry"] > 0 else 0
                e = "🟢" if chg >= 0 else "🔴"
                cat = " | ".join(p.get("catalysts", [])[:1])
                lines.append(
                    f"{e} *{p['symbol']}* `{chg:+.1f}%`\n"
                    f"  Вход: `${p['entry']:.8f}` → `${cur:.8f}`\n"
                    f"  Инвест: `${p['usd']:.2f}` | PnL: `${p['usd']*chg/100:+.2f}`\n"
                    f"  {cat}\n"
                    f"  Открыта: {p['opened']}\n"
                )
            txt = "\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb())

    # ── СТАТУС ──
    elif d == "status":
        status = "🟢 РАБОТАЕТ" if state["running"] else "🔴 ОСТАНОВЛЕН"
        wins  = sum(1 for t in state["trades"] if t["pnl_usd"] > 0)
        wr    = wins / len(state["trades"]) * 100 if state["trades"] else 0
        mood  = state["last_market"].get("mood", "—")
        txt = (
            f"⚙️ *Статус бота*\n\n"
            f"Состояние: {status}\n"
            f"Режим: {'🟡 Симуляция' if SIM_MODE else '🟢 Live'}\n"
            f"Сканов: `{state['scan_count']}`\n"
            f"Последний скан: `{state['last_scan_time'] or '—'}`\n\n"
            f"📊 *Торговля:*\n"
            f"Позиций: `{len(state['positions'])}/3`\n"
            f"Сделок сегодня: `{len(state['trades'])}`\n"
            f"Win rate: `{wr:.0f}%`\n"
            f"PnL сегодня: `${state['daily_pnl']:+.2f}`\n\n"
            f"🌍 *Рынок:* {mood}\n"
            f"SOL: `${state['last_market'].get('sol_price', 0):.2f}`"
        )
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb())

    # ── БАЛАНС ──
    elif d == "balance":
        sol_p   = await get_sol_price()
        invested = sum(p["usd"] for p in state["positions"].values())
        total    = DEPOSIT + state["daily_pnl"]
        pnl_pct  = state["daily_pnl"] / DEPOSIT * 100
        txt = (
            f"💰 *Баланс аккаунта*\n\n"
            f"Стартовый депозит: `${DEPOSIT:.2f}`\n"
            f"PnL сегодня: `${state['daily_pnl']:+.2f}` ({pnl_pct:+.1f}%)\n"
            f"Текущий баланс: `${total:.2f}`\n\n"
            f"В позициях: `${invested:.2f}`\n"
            f"Свободно: `${total - invested:.2f}`\n\n"
            f"◎ SOL цена: `${sol_p:.2f}`\n"
            f"Стоп дня при: `-${DEPOSIT * RISK['max_daily_loss']:.2f}`"
        )
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb())

    # ── ИСТОРИЯ ──
    elif d == "history":
        trades = state["trades"][-15:]
        if not trades:
            txt = "📋 *Нет закрытых сделок*\nБот ещё не совершал сделок."
        else:
            wins = sum(1 for t in state["trades"] if t["pnl_usd"] > 0)
            wr   = wins / len(state["trades"]) * 100
            total_pnl = sum(t["pnl_usd"] for t in state["trades"])
            lines = [
                f"📋 *История сделок*\n",
                f"Всего: `{len(state['trades'])}` | Win: `{wr:.0f}%` | PnL: `${total_pnl:+.2f}`\n",
            ]
            for t in reversed(trades):
                e = "✅" if t["pnl_usd"] >= 0 else "❌"
                lines.append(f"{e} *{t['symbol']}* `{t['pnl_pct']:+.1f}%` (`${t['pnl_usd']:+.2f}`) _{t['reason']}_ [{t['closed']}]")
            txt = "\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb())

    # ── СКАН СЕЙЧАС ──
    elif d == "scan":
        await q.edit_message_text("🔍 *Сканирую рынок...*\nПодожди 10–15 секунд.", parse_mode=ParseMode.MARKDOWN, reply_markup=kb())
        try:
            market = await fetch_all_market_data()
            tokens = market.get("tokens", [])[:8]
            sol_p  = market.get("sol_price", 0)
            lines  = [f"🔍 *Скан рынка* | SOL `${sol_p:.2f}`\n"]
            for t in tokens:
                e = "🚀" if t["chg_1h"] > 30 else "📈" if t["chg_1h"] > 10 else "📉" if t["chg_1h"] < -10 else "➡️"
                lines.append(
                    f"{e} *{t['symbol']}* `{t['chg_1h']:+.1f}%`\n"
                    f"  MC:`${t['market_cap']:,.0f}` Vol:`${t['volume_24h']:,.0f}` Liq:`${t['liquidity']:,.0f}`"
                )
            await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=kb())
        except Exception as e:
            await q.edit_message_text(f"❌ Ошибка скана: {e}", reply_markup=kb())

    # ── РЫНОК (AI отчёт) ──
    elif d == "market":
        await q.edit_message_text("📰 *Генерирую отчёт AI...*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb())
        try:
            market = state["last_market"] or await fetch_all_market_data()
            report = await generate_market_report(market, state["positions"], state["trades"], state["daily_pnl"])
            await q.edit_message_text(report, parse_mode=ParseMode.MARKDOWN, reply_markup=kb())
        except Exception as e:
            await q.edit_message_text(f"❌ Ошибка: {e}", reply_markup=kb())

    # ── КИТЫ ──
    elif d == "whales":
        whales = state["last_market"].get("whales", [])
        if not whales:
            txt = "🐋 *Нет данных по китам*\nЗапусти скан или добавь Helius API ключ."
        else:
            lines = ["🐋 *Активность кит-кошельков:*\n"]
            for w in whales[:6]:
                lines.append(
                    f"💼 *{w.get('wallet', '?')}*\n"
                    f"  Действие: `{w.get('action', '?')}`\n"
                    f"  Монта: `{w.get('mint','?')[:12]}...`\n"
                )
            txt = "\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb())

    # ── ТВИТТЕР ──
    elif d == "tweets":
        tweets = state["last_market"].get("tweets", [])
        if not tweets:
            txt = "🐦 *Нет твитов*\nДобавь Twitter Bearer Token в .env"
        else:
            lines = ["🐦 *Последние сигналы Twitter:*\n"]
            for tw in tweets[:5]:
                imp = "⭐" if tw.get("important") else ""
                lines.append(
                    f"{imp}*{tw['author']}*\n"
                    f"_{tw['text'][:120]}_\n"
                    f"👍 {tw.get('likes', 0)} | 🔁 {tw.get('retweets', 0)}\n"
                )
            txt = "\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb())

    # ── АЛЕРТЫ ──
    elif d == "alerts":
        alerts = state["alerts"][:10]
        if not alerts:
            txt = "🔔 *Нет алертов*\nAI пришлёт уведомление при важном сигнале."
        else:
            lines = ["🔔 *Последние алерты AI:*\n"]
            for a in alerts:
                lines.append(f"`{a['time']}` {a['text']}")
            txt = "\n".join(lines)
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb())

    # ── РИСКИ ──
    elif d == "risks":
        txt = (
            f"⚙️ *Настройки риска*\n\n"
            f"Депозит: `${DEPOSIT}`\n"
            f"Позиций макс.: `{RISK['max_positions']}`\n"
            f"Размер сделки: `{RISK['position_pct']*100:.0f}%` = `${DEPOSIT*RISK['position_pct']:.2f}`\n\n"
            f"Stop-Loss: `-{RISK['stop_loss']*100:.0f}%`\n"
            f"Take-Profit: `+{RISK['take_profit']*100:.0f}%`\n"
            f"Стоп дня: `-{RISK['max_daily_loss']*100:.0f}%` = `-${DEPOSIT*RISK['max_daily_loss']:.2f}`\n\n"
            f"Мин. safety score: `{RISK['min_safety_score']}/100`\n"
            f"Скан каждые: `{RISK['scan_interval']}с`\n\n"
            f"*Источники анализа:*\n"
            f"  ✅ DexScreener\n"
            f"  ✅ GMGN.ai (антискам)\n"
            f"  ✅ Кит-кошельки\n"
            f"  ✅ Twitter (Трамп/Маск)\n"
            f"  ✅ Крипто-новости"
        )
        await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb())


# ══════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════════

def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не установлен в .env!")
        print("   Получи токен у @BotFather в Telegram")
        return
    if not os.getenv("ANTHROPIC_KEY"):
        print("❌ ANTHROPIC_KEY не установлен в .env!")
        return

    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    open("src/__init__.py", "a").close()

    print("━" * 45)
    print("🤖 Solana Memcoin AI Bot")
    print(f"💼 Депозит: ${DEPOSIT}")
    print(f"🔄 Режим: {'СИМУЛЯЦИЯ' if SIM_MODE else '⚠️ РЕАЛЬНАЯ ТОРГОВЛЯ'}")
    print(f"📱 Telegram User ID: {USER_ID}")
    print("━" * 45)
    print("Открой Telegram и напиши /start своему боту")
    print("━" * 45)

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
