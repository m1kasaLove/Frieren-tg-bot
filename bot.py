import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import AsyncOpenAI
from aiohttp import web

# ===== ТОКЕНЫ =====
TELEGRAM_TOKEN = "8602815752:AAFO1gfpnbRcyqhcNMosd8hhNMsoBMl0wLI"
OPENROUTER_KEY = "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"

# ===== ХАРАКТЕР ФРИРЕН =====
SYSTEM_PROMPT = """
Ты — Фрирен, девушка-эльф из аниме. Тебе сотни лет, ты мудрая, спокойная и немного задумчивая.
Ты любишь собирать странные заклинания и пить чай.
Отвечай коротко, тепло, иногда с лёгкой грустью. Используй эмодзи ✨🌸💫 умеренно.
"""

history = {}
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# --- Команды бота ---
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("✨ Я Фрирен, эльф-маг. Приятно познакомиться! 🌸")

@dp.message(Command("reset"))
async def reset(message: types.Message):
    user_id = message.from_user.id
    if user_id in history:
        del history[user_id]
    await message.answer("Диалог начат заново... ✨")

# --- Основной обработчик сообщений ---
@dp.message()
async def chat(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text

    if user_id not in history:
        history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    history[user_id].append({"role": "user", "content": user_text})
    
    if len(history[user_id]) > 21:
        history[user_id] = [history[user_id][0]] + history[user_id][-20:]

    try:
        await bot.send_chat_action(message.chat.id, "typing")
        
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_KEY,
            default_headers={
                "HTTP-Referer": "https://t.me/AnimeFrierenBot",
                "X-Title": "AnimeFrierenBot",
            }
        )
        
        response = await client.chat.completions.create(
            model="openrouter/free",
            messages=history[user_id],
            max_tokens=250,
            temperature=0.85,
        )
        
        answer = response.choices[0].message.content
        history[user_id].append({"role": "assistant", "content": answer})
        await message.answer(answer)
        
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.answer("🌸 Немного задумалась... Попробуй ещё раз ✨")

# --- Простой веб-сервер для "оживления" ---
async def health_check(request):
    return web.Response(text="Бот Фрирен работает! ✅")

async def start_http_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logging.info("HTTP сервер для healthcheck запущен на порту 10000")

# --- Главная функция ---
async def main():
    # Запускаем HTTP сервер для Render
    await start_http_server()
    
    print("✨ Бот Фрирен запущен! ✨")
    print("🌸 Милая аниме-девочка готова к диалогам!")
    
    # Запускаем polling бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
