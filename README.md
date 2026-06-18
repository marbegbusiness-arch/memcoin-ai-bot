# 🤖 Solana Memcoin AI Bot

Полный автопилот. Анализирует:
- 📡 DexScreener (токены, объём, ликвидность)
- 🛡 GMGN.ai (защита от скама/rug pull)
- 🐋 Кит-кошельки (умные деньги Solana)
- 🐦 Twitter: Трамп, Илон Маск, топ-инфлюенсеры
- 📰 Новости: CoinDesk, CryptoPanic

---

## 🚀 УСТАНОВКА ЗА 5 МИНУТ

### Шаг 1 — Создай Telegram бота (БЕСПЛАТНО)
1. Открой Telegram → найди **@BotFather**
2. Напиши `/newbot`
3. Придумай имя: `Мой Мемкоин Бот`
4. Придумай username: `my_memcoin_bot`
5. Скопируй **TOKEN** (выглядит как `123456:ABC-DEF...`)

### Шаг 2 — Узнай свой Telegram ID
1. Открой @userinfobot
2. Напиши `/start`
3. Скопируй **Id** (число)

### Шаг 3 — Получи Claude API ключ (БЕСПЛАТНЫЙ TRIAL)
1. Зайди на https://console.anthropic.com
2. Создай аккаунт → API Keys → Create Key
3. Скопируй ключ

### Шаг 4 — Установи Python и запусти

**Windows:**
```
1. Скачай Python 3.11 с python.org
2. Открой папку с ботом
3. Двойной клик на START_WINDOWS.bat
```

**Mac/Linux:**
```bash
pip3 install -r requirements.txt
cp .env.example .env
# Отредактируй .env (вставь свои ключи)
python3 main.py
```

### Шаг 5 — Заполни .env файл
```
TELEGRAM_TOKEN=  ← токен от @BotFather
TELEGRAM_USER_ID= ← твой ID от @userinfobot  
ANTHROPIC_KEY=   ← ключ от console.anthropic.com
DEPOSIT_USD=20
SIMULATION_MODE=true  ← начни с симуляции!
```

### Шаг 6 — Открой своего бота
1. Найди своего бота в Telegram по username
2. Напиши `/start`
3. Нажми **▶️ Старт**

---

## 📱 КАК ВЫГЛЯДИТ БОТ В TELEGRAM

```
🤖 Solana Memcoin AI Bot

[▶️ Старт]  [⏹ Стоп]
[📊 Позиции] [💹 Статус]
[💰 Баланс]  [📋 История]
[🔍 Скан]    [📰 Рынок]
[🐋 Киты]    [🐦 Твиттер]
[🔔 Алерты]  [⚙️ Риски]
```

Уведомления приходят автоматически:
```
🟢 ПОКУПКА — BONK
💰 Сумма: $4.00
📍 Цена: $0.00002341
🎯 TP: +150% | SL: -30%
📊 Уверенность AI: 78%
⚡ Кит купил 30 мин назад
⚡ Упоминание в твиттере
```

---

## 🔑 ДОПОЛНИТЕЛЬНЫЕ API (ОПЦИОНАЛЬНО)

### Twitter API ($0 — базовый доступ)
- developer.twitter.com → Create App → Free tier
- Даёт доступ к твитам Трампа, Маска

### Helius (БЕСПЛАТНО — 100k запросов/мес)
- helius.dev → создай аккаунт → Get API Key
- Нужен для отслеживания кит-кошельков

---

## ⚙️ УПРАВЛЕНИЕ РИСКАМИ

| Параметр | Значение |
|---|---|
| Макс. позиций | 3 |
| Размер сделки | 20% депозита |
| Stop-Loss | -30% |
| Take-Profit | +150% |
| Стоп дня | -40% депозита |
| Мин. safety score | 55/100 |

---

## 🌐 ДЛЯ РАБОТЫ 7/24

Бот работает пока открыт терминал.
Для постоянной работы используй VPS:

**Бесплатные варианты:**
- Railway.app — задеплой за 5 минут
- Render.com — бесплатный tier
- Oracle Cloud — навсегда бесплатно (ARM VM)

**Дешёвые VPS ($3-5/мес):**
- Hetzner.com (лучшее соотношение цена/качество)
- DigitalOcean
- Contabo

На VPS запусти:
```bash
pip install pm2
pm2 start "python3 main.py" --name membot
pm2 save
```

---

## ⚠️ ДИСКЛЕЙМЕР

Торговля мемкоинами = высокий риск потери средств.
Начинай ВСЕГДА с SIMULATION_MODE=true.
Не торгуй деньгами которые не можешь потерять.
