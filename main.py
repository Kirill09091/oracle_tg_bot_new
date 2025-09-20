# main.py (добавьте новый CommandHandler)
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import TELEGRAM_BOT_TOKEN
from handlers import (
    start_command,
    text_message_handler,
    generate_image_command,
    generate_and_post_to_channel,
    create_poll_command,
    voice_command # <-- ДОБАВЛЕНО
)

# Настройка логирования для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Запускает бота."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Добавляем обработчики команд и сообщений
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("image", generate_image_command))
    application.add_handler(CommandHandler("post", generate_and_post_to_channel))
    application.add_handler(CommandHandler("poll", create_poll_command))
    application.add_handler(CommandHandler("voice", voice_command)) # <-- ДОБАВЛЕНО
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

    # Запускаем бота
    logger.info("Бот Оракул-TG запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()