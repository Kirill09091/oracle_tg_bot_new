# telegram_utils.py
import logging
from telegram import Bot, InputMediaPhoto, Poll
from telegram.constants import ParseMode
from config import TELEGRAM_CHANNEL_ID, TELEGRAM_BOT_TOKEN # Импортируем ID канала и токен

logger = logging.getLogger(__name__)

# Инициализируем объект бота, используя токен
# Это позволит нам отправлять сообщения напрямую, а не только в ответ на действия пользователя
bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def send_post_to_channel(text: str, image_bytes: bytes = None, parse_mode: str = ParseMode.HTML) -> bool:
    """
    Отправляет текстовый пост или пост с изображением в указанный Telegram-канал.
    """
    if not TELEGRAM_CHANNEL_ID:
        logger.error("TELEGRAM_CHANNEL_ID не установлен в config.py. Пост не будет отправлен.")
        return False

    try:
        if image_bytes:
            # Если есть изображение, отправляем его с подписью
            await bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=image_bytes,
                caption=text,
                parse_mode=parse_mode
            )
            logger.info(f"Фото с подписью отправлено в канал {TELEGRAM_CHANNEL_ID}. Подпись: {text[:50]}...")
        else:
            # Если изображения нет, отправляем только текст
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=text,
                parse_mode=parse_mode
            )
            logger.info(f"Текстовый пост отправлен в канал {TELEGRAM_CHANNEL_ID}. Текст: {text[:50]}...")
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке поста в канал {TELEGRAM_CHANNEL_ID}: {e}", exc_info=True)
        return False

async def send_poll_to_channel(question: str, options: list[str]) -> bool:
    """
    Отправляет опрос в указанный Telegram-канал.
    """
    if not TELEGRAM_CHANNEL_ID:
        logger.error("TELEGRAM_CHANNEL_ID не установлен в config.py. Опрос не будет отправлен.")
        return False

    if not question or not options or len(options) < 2:
        logger.warning("Некорректные данные для опроса: вопрос или опции отсутствуют/недостаточны.")
        return False

    try:
        await bot.send_poll(
            chat_id=TELEGRAM_CHANNEL_ID,
            question=question,
            options=options,
            is_anonymous=False, # Опросы в каналах обычно не анонимные для статистики
            type=Poll.REGULAR # Обычный опрос, не викторина
        )
        logger.info(f"Опрос отправлен в канал {TELEGRAM_CHANNEL_ID}. Вопрос: '{question}'")
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке опроса в канал {TELEGRAM_CHANNEL_ID}: {e}", exc_info=True)
        return False