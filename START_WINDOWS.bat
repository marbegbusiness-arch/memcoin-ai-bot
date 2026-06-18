@echo off
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo  Solana Memcoin AI Bot — Setup
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo Устанавливаю зависимости...
pip install -r requirements.txt

if not exist .env (
    copy .env.example .env
    echo.
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    echo  ВАЖНО: Заполни файл .env
    echo  Открой .env и вставь:
    echo  - TELEGRAM_TOKEN (от @BotFather)
    echo  - TELEGRAM_USER_ID (от @userinfobot)
    echo  - ANTHROPIC_KEY (от console.anthropic.com)
    echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    notepad .env
)

echo.
echo Запускаю бота...
python main.py
pause
