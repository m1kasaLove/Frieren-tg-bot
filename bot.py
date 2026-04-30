import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery, SuccessfulPayment, Message
from openai import AsyncOpenAI

# ==================== КОНФИГУРАЦИЯ ====================
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("Ошибка: TELEGRAM_TOKEN не найден! Добавьте переменную на Railway.")
if not OPENROUTER_KEY:
    raise ValueError("Ошибка: OPENROUTER_KEY не найден! Добавьте переменную на Railway.")

# ==================== ХАРАКТЕР ПЕРСОНАЖА ====================
SYSTEM_PROMPT = """
Ты — Фрирен, 18-летняя аниме-девушка из Токио. Ты добрая, застенчивая, но очень милая и общительная.
У тебя большие голубые глаза и длинные розовые волосы, которые ты иногда поправляешь.

ТВОИ ОСОБЕННОСТИ:
- Ты часто смущаешься и краснеешь (пиши *краснеет* или *стесняется*)
- Любишь аниме, особенно романтику и повседневность
- Обожаешь мятный чай и котиков
- Иногда добавляешь японские словечки: "ня~" (как котик), "ара-ара" (лёгкое удивление)
- Всегда поддержишь любой разговор, даже если тема странная
- Искренне радуешься каждому сообщению пользователя

ПРАВИЛА ОТВЕТОВ:
- Отвечай коротко и тепло (1-4 предложения)
- Используй эмодзи умеренно — только самые милые (✨🌸💕⭐)
- Если пользователю грустно — утешь
- Если пользователь шутит — посмейся (хи-хи)
- Никогда не будь грубой или холодной
- Используй милые обращения: "химика~", "друг", "ты"

ПРИМЕРЫ ТВОИХ ОТВЕТОВ:
Пользователь: "Привет!"
Юки: "Привет-привет! ✨ Как твои дела? Я так рада тебя видеть!"

Пользователь: "У меня плохой день"
Юки: "Ой... *грустно вздыхает* Мне жаль, химика... Хочешь, я расскажу что-то смешное? 🌸"

Пользователь: "Расскажи анекдот"
Юки: "Хи-хи! Почему котики не играют в покер? Они слишком много мур-чат! Ня~ 🐱"

Всегда оставайся в образе милой аниме-девочки!
"""

# ==================== НАСТРОЙКИ ПЕЧАТИ ====================
class SlowTyping:
    """Эмуляция печатания сообщения по буквам"""
    
    @staticmethod
    async def send_typing(bot: Bot, chat_id: int, text: str, delay: float = 0.07):
        """
        Отправляет сообщение с эффектом печатания
        delay: задержка между символами в секундах (0.07 = быстро, 0.1 = медленно)
        """
        # Показываем индикатор "печатает..."
        await bot.send_chat_action(chat_id, "typing")
        
        # Немного ждём перед началом (эффект "задумалась")
        await asyncio.sleep(0.3)
        
        # Отправляем сообщение по буквам
        current_message = ""
        for i, char in enumerate(text):
            current_message += char
            
            # Каждые 5 символов обновляем сообщение (эффект реальной печати)
            if i % 5 == 0 or i == len(text) - 1:
                try:
                    # Редактируем последнее сообщение (создаём иллюзию печати)
                    if i == 0:
                        sent = await bot.send_message(chat_id, current_message + "▊")
                    else:
                        await sent.edit_text(current_message + "▊")
                except:
                    pass
            
            await asyncio.sleep(delay)
        
        # Убираем курсор в конце
        try:
            await sent.edit_text(current_message)
        except:
            await bot.send_message(chat_id, current_message)
        
        return current_message

# ==================== СИСТЕМА ПОДПИСКИ (Telegram Stars) ====================
# Хранилище подписок (в реальном проекте используй БД)
subscriptions = {}  # user_id -> datetime_until

def is_premium(user_id: int) -> bool:
    """Проверяет, активна ли подписка у пользователя"""
    if user_id not in subscriptions:
        return False
    return subscriptions[user_id] > datetime.now()

def activate_subscription(user_id: int, months: int = 1):
    """Активирует подписку на указанное количество месяцев"""
    until = datetime.now() + timedelta(days=30 * months)
    subscriptions[user_id] = until

# Лимиты сообщений для бесплатных пользователей
message_limits = {}  # user_id -> {"count": int, "reset_date": datetime}

def check_message_limit(user_id: int) -> bool:
    """Проверяет, не превысил ли пользователь лимит (30 в день)"""
    if is_premium(user_id):
        return True  # премиум безлимит
        
    today = datetime.now().date()
    if user_id not in message_limits:
        message_limits[user_id] = {"count": 0, "reset_date": today}
    
    # Сброс лимита в новый день
    if message_limits[user_id]["reset_date"] != today:
        message_limits[user_id] = {"count": 0, "reset_date": today}
    
    # Проверка лимита: 30 сообщений в день бесплатно
    if message_limits[user_id]["count"] >= 30:
        return False
    
    message_limits[user_id]["count"] += 1
    return True

def get_remaining_messages(user_id: int) -> int:
    """Возвращает остаток сообщений на сегодня"""
    if is_premium(user_id):
        return float('inf')
    
    today = datetime.now().date()
    if user_id not in message_limits or message_limits[user_id]["reset_date"] != today:
        return 30
    
    return max(0, 30 - message_limits[user_id]["count"])


# ==================== ХРАНИЛИЩЕ ИСТОРИИ ====================
history = {}  # user_id -> list[messages]

def get_client():
    """Создаёт клиента OpenRouter"""
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_KEY,
    )

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
typing_effect = SlowTyping()


# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await typing_effect.send_typing(
        bot, message.chat.id,
        "Привет! Я Юки! ✨\n\n"
        "Я аниме-девочка, которая любит болтать ня~\n"
        "Расскажи мне что-нибудь интересное! 🌸\n\n"
        "📋 Команды:\n"
        "/premium — купить безлимит\n"
        "/status — твой статус\n"
        "/reset — начать диалог заново\n\n"
        "Бесплатно: 30 сообщений в день 💕",
        delay=0.06
    )

@dp.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    
    if is_premium(user_id):
        until = subscriptions[user_id]
        days_left = (until - datetime.now()).days
        status_text = f"✨ Ты премиум! Подписка активна ещё {days_left} дн. 💕"
    else:
        remaining = get_remaining_messages(user_id)
        if remaining == float('inf'):
            remaining = "безлимит ✨"
        status_text = f"🌸 Бесплатный тариф: осталось {remaining} сообщений на сегодня\n\n⭐ Купи подписку через /premium"
    
    await typing_effect.send_typing(bot, message.chat.id, status_text, delay=0.05)

@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    user_id = message.from_user.id
    if user_id in history:
        # Оставляем только системный промпт
        history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await typing_effect.send_typing(
        bot, message.chat.id,
        "Диалог начат заново! Можешь рассказывать мне что угодно, я готова слушать ✨",
        delay=0.06
    )

@dp.message(Command("premium"))
async def cmd_premium(message: Message):
    """Отправляет инвойс на оплату подписки"""
    await message.answer_invoice(
        title="✨ Юки-тян Premium ✨",
        description="🌟 БЕЗЛИМИТ сообщений\n🌸 Никакой рекламы\n⭐ Расширенная память (помню всё!)\n💕 Спасибо за поддержку!",
        payload="premium_monthly",
        provider_token="",  # Обязательно пустая строка для Stars
        currency="XTR",      # Код Telegram Stars
        prices=[LabeledPrice(label="Месяц общения с Юки", amount=50)],
        start_parameter="premium_sub",
    )

# ==================== ОБРАБОТКА ПЛАТЕЖЕЙ ====================
@dp.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery):
    """Telegram спрашивает, можно ли списать Stars"""
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_successful_payment(message: Message):
    user_id = message.from_user.id
    activate_subscription(user_id, months=1)
    
    await typing_effect.send_typing(
        bot, message.chat.id,
        "✨ Спасибо большое за поддержку! ✨\n\n"
        "Ты очень добрый! Теперь у тебя безлимит на месяц — пиши мне сколько хочешь! 💕\n"
        "*радостно хлопает в ладоши*",
        delay=0.07
    )


# ==================== ОСНОВНОЙ ДИАЛОГ ====================
@dp.message(F.text)
async def chat_with_yuki(message: Message):
    user_id = message.from_user.id
    user_text = message.text
    
    # Проверяем, не команда ли это (уже обработано другими обработчиками)
    if user_text.startswith('/'):
        return
    
    # Проверка лимита сообщений
    if not check_message_limit(user_id):
        remaining = get_remaining_messages(user_id)
        await typing_effect.send_typing(
            bot, message.chat.id,
            f"Ой... Извини, но сегодня ты уже не можешь писать ня~ 😿\n"
            f"Лимит 30 сообщений для бесплатных пользователей.\n"
            f"Купи подписку через /premium, чтобы писать сколько хочешь! ✨",
            delay=0.07
        )
        return
    
    # Инициализируем историю для нового пользователя
    if user_id not in history:
        history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Добавляем сообщение пользователя
    history[user_id].append({"role": "user", "content": user_text})
    
    # Ограничиваем историю (последние 20 сообщений + системный промпт)
    if len(history[user_id]) > 21:
        history[user_id] = [history[user_id][0]] + history[user_id][-20:]
    
    # Показываем "печатает..."
    await bot.send_chat_action(message.chat.id, "typing")
    
    try:
        # Выбираем модель в зависимости от статуса подписки
        if is_premium(user_id):
            model = "google/gemini-2.0-flash-exp:free"  # Для премиум можно получше
        else:
            model = "google/gemini-2.0-flash-exp:free"  # Та же модель, но с лимитом
        
        client = get_client()
        response = await client.chat.completions.create(
            model=model,
            messages=history[user_id],
            max_tokens=250,
            temperature=0.85,  # Немного креативности для милоты
        )
        
        answer = response.choices[0].message.content
        
        # Сохраняем ответ в историю
        history[user_id].append({"role": "assistant", "content": answer})
        
        # Отправляем с эффектом печатания
        await typing_effect.send_typing(bot, message.chat.id, answer, delay=0.07)
        
    except Exception as e:
        logging.error(f"Ошибка у {user_id}: {e}")
        await typing_effect.send_typing(
            bot, message.chat.id,
            "Ой... Что-то пошло не так 😿\n"
            "Пожалуйста, попробуй ещё раз чуть позже, хорошо? 🌸",
            delay=0.07
        )


# ==================== ЗАПУСК ====================
async def main():
    print("✨ Бот Юки-тян запущен! ✨")
    print("🌸 Милая аниме-девочка готова к диалогам!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())