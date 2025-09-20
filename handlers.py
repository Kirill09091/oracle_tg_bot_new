# handlers.py
import logging
import base64
from io import BytesIO

from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode # Импортируем ParseMode для форматирования текста

from gemini_api import get_gemini_response
from image_generation import generate_image
from telegram_utils import send_post_to_channel, send_poll_to_channel

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start."""
    user = update.effective_user
    await update.message.reply_html(
        f"Привет, {user.mention_html()}! Я Оракул-TG. Чем могу помочь?\n\n"
        "Я могу генерировать текст (просто напишите мне что-нибудь), "
        "генерировать картинки командой `/image [описание]`, "
        "публиковать посты в вашем канале командой `/post [тема]` "
        "и создавать опросы командой `/poll [вопрос];[опция1];[опция2]`."
    )
    logger.info(f"Получена команда /start от пользователя {user.id} ({user.first_name})")

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает входящие текстовые сообщения, отправляет их в Gemini
    и отправляет ответ обратно в Telegram.
    """
    user_message = update.message.text
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    logger.info(f"Получено сообщение от {user_id} ({user_name}): '{user_message}'")

    # Отправляем временное сообщение, пока Gemini думает
    await update.message.reply_text("Думаю над вашим запросом...")

    # Отправляем сообщение пользователя в Gemini через нашу функцию
    gemini_response_text = await get_gemini_response(user_message)

    if gemini_response_text:
        # Отправляем ответ от Gemini обратно в Telegram
        await update.message.reply_text(gemini_response_text)
        logger.info(f"Отправлен ответ Gemini пользователю {user_id}: '{gemini_response_text[:50]}...'")
    else:
        # Если Gemini вернул None (ошибка или пустой ответ)
        await update.message.reply_text("Извините, Оракул-TG не смог дать ответ. Пожалуйста, попробуйте перефразировать.")
        logger.warning(f"Gemini вернул пустой ответ для пользователя {user_id} или произошла ошибка.")


async def generate_image_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /image [промпт] для генерации изображения.
    """
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    prompt = " ".join(context.args) # Получаем весь текст после команды /image

    if not prompt:
        await update.message.reply_text("Пожалуйста, укажите описание для изображения после команды /image. Например: `/image кошка в шляпе`")
        logger.info(f"Пользователь {user_id} ({user_name}) вызвал /image без промпта.")
        return

    await update.message.reply_text("Пожалуйста, подождите, Оракул-TG генерирует изображение...")
    logger.info(f"Пользователь {user_id} ({user_name}) запросил генерацию изображения с промптом: '{prompt}'")

    image_base64 = await generate_image(prompt)

    if image_base64:
        try:
            # Декодируем base64 в байты
            image_bytes = base64.b64decode(image_base64)
            # Отправляем изображение как фото
            await update.message.reply_photo(
                photo=InputFile(BytesIO(image_bytes)),
                caption=f"Ваше изображение по запросу: *{prompt}*",
                parse_mode=ParseMode.MARKDOWN # Используем Markdown для форматирования подписи
            )
            logger.info(f"Изображение успешно отправлено пользователю {user_id}.")
        except Exception as e:
            logger.error(f"Ошибка при отправке изображения в Telegram: {e}", exc_info=True)
            await update.message.reply_text("Извините, не удалось отправить изображение в Telegram.")
    else:
        await update.message.reply_text("Извините, не удалось сгенерировать изображение. Возможно, промпт слишком сложный, превышен лимит API или возникла внутренняя проблема.")
        logger.warning(f"Не удалось сгенерировать изображение для пользователя {user_id} с промптом: '{prompt}'")


async def generate_and_post_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /post [тема]. Генерирует пост с помощью Gemini
    и отправляет его в канал. Поддерживает выбор языка и размера.
    Пример: /post тема:новости, язык:русский, размер:средний, картинка:описание картинки
    """
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    args_str = " ".join(context.args).lower() # Приводим к нижнему регистру для удобства парсинга

    # Парсим аргументы
    prompt_parts = []
    lang = "русский" # Язык по умолчанию
    size = "обычный" # Размер по умолчанию
    image_prompt = None # Промпт для изображения, если запрошено

    # Простой парсер для аргументов (можно улучшить, но для начала достаточно)
    if "тема:" in args_str:
        prompt_parts.append(f"Тема: {args_str.split('тема:')[1].split(',')[0].strip()}")
    if "язык:" in args_str:
        lang = args_str.split('язык:')[1].split(',')[0].strip()
    if "размер:" in args_str:
        size = args_str.split('размер:')[1].split(',')[0].strip()
    if "картинка:" in args_str:
        image_prompt = args_str.split('картинка:')[1].split(',')[0].strip()

    if not prompt_parts:
        await update.message.reply_text(
            "Пожалуйста, укажите **тему** для поста. Например: \n"
            "`/post тема:интересные факты`\n"
            "Вы также можете добавить `язык: [русский/украинский]`, `размер: [короткий/средний/длинный]` "
            "и `картинка: [описание картинки]` для генерации изображения к посту."
        )
        logger.info(f"Пользователь {user_id} ({user_name}) вызвал /post без темы.")
        return

    full_gemini_prompt = (
        f"Сгенерируй пост для Telegram-канала на {lang} языке. "
        f"Размер поста: {size}. {', '.join(prompt_parts)}. "
        "Убедись, что пост разнообразный, интересный и подходит для публикации в Telegram. "
        "Форматируй текст для Telegram, используй жирный шрифт для заголовков, абзацы."
    )

    await update.message.reply_text(f"Оракул-TG генерирует пост по теме '{prompt_parts[0]}' на {lang} языке...")
    logger.info(f"Пользователь {user_id} ({user_name}) запросил генерацию поста с промптом: '{full_gemini_prompt}'")

    generated_text = await get_gemini_response(full_gemini_prompt)
    generated_image_b64 = None
    image_bytes = None

    if image_prompt:
        await update.message.reply_text("Генерирую изображение для поста...")
        generated_image_b64 = await generate_image(image_prompt)
        if generated_image_b64:
            image_bytes = base64.b64decode(generated_image_b64)
            logger.info(f"Изображение для поста сгенерировано.")
        else:
            await update.message.reply_text("Не удалось сгенерировать изображение к посту. Опубликую только текст.")
            logger.warning(f"Не удалось сгенерировать изображение для поста с промптом: '{image_prompt}'")


    if generated_text:
        await update.message.reply_text("Пост сгенерирован. Отправляю в канал...")
        # Предполагаем, что Gemini может вернуть текст с разметкой Markdown или HTML,
        # поэтому отправляем как HTML для лучшей совместимости
        success = await send_post_to_channel(generated_text, image_bytes, parse_mode=ParseMode.HTML)
        if success:
            await update.message.reply_text("Пост успешно опубликован в канале!")
            logger.info(f"Пост успешно опубликован в канале пользователем {user_id}.")
        else:
            await update.message.reply_text("Не удалось опубликовать пост в канале. Проверьте ID канала и права бота.")
            logger.warning(f"Не удалось опубликовать пост в канале для пользователя {user_id}.")
    else:
        await update.message.reply_text("Не удалось сгенерировать пост. Пожалуйста, попробуйте еще раз.")
        logger.warning(f"Не удалось сгенерировать пост для пользователя {user_id}.")


async def create_poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /poll [вопрос];[опция1];[опция2];...
    Создает и отправляет опрос в канал.
    """
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    args_str = " ".join(context.args)

    parts = args_str.split(';')

    if len(parts) < 3: # Минимум: вопрос, опция1, опция2
        await update.message.reply_text(
            "Неверный формат. Используйте: `/poll [вопрос];[опция1];[опция2];[опция3]`"
        )
        logger.info(f"Пользователь {user_id} ({user_name}) вызвал /poll с неверным форматом.")
        return

    question = parts[0].strip()
    options = [opt.strip() for opt in parts[1:] if opt.strip()] # Убираем пустые опции

    if not question or len(options) < 2:
        await update.message.reply_text(
            "Не удалось создать опрос. Убедитесь, что есть вопрос и минимум две опции."
        )
        logger.warning(f"Пользователь {user_id} ({user_name}) вызвал /poll с некорректными данными: '{args_str}'")
        return

    # Ограничения Telegram на опросы
    if len(question) > 300:
        await update.message.reply_text("Вопрос для опроса слишком длинный (максимум 300 символов).")
        logger.warning(f"Вопрос для опроса слишком длинный от пользователя {user_id}.")
        return
    if not (2 <= len(options) <= 10):
        await update.message.reply_text("Опрос должен иметь от 2 до 10 вариантов ответа.")
        logger.warning(f"Неправильное количество опций для опроса от пользователя {user_id}.")
        return
    for opt in options:
        if len(opt) > 100:
            await update.message.reply_text(f"Опция '{opt[:20]}...' слишком длинная (максимум 100 символов).")
            logger.warning(f"Опция для опроса слишком длинная от пользователя {user_id}.")
            return

    await update.message.reply_text("Создаю и отправляю опрос в канал...")
    logger.info(f"Пользователь {user_id} ({user_name}) запросил опрос: '{question}' с опциями: {options}")

    success = await send_poll_to_channel(question, options)

    if success:
        await update.message.reply_text("Опрос успешно опубликован в канале!")
        logger.info(f"Опрос успешно опубликован в канале пользователем {user_id}.")
    else:
        await update.message.reply_text("Не удалось опубликовать опрос в канале. Проверьте ID канала и права бота.")
        logger.warning(f"Не удалось опубликовать опрос в канале для пользователя {user_id}.")

        # handlers.py (добавьте эту функцию в конец файла)
# ... (весь предыдущий код, включая импорты) ...

from voice_utils import listen_and_recognize, speak_text # Импортируем новые функции

async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /voice: запускает голосовое взаимодействие.
    Бот слушает, распознает, отправляет в Gemini и отвечает голосом.
    """
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    await update.message.reply_text("Режим голосового общения активирован. Скажите что-нибудь...")
    logger.info(f"Пользователь {user_id} ({user_name}) активировал голосовой режим.")

    # Можно добавить возможность выбрать язык голоса для Оракула-TG
    # Например, из аргументов команды: /voice ru или /voice uk
    # Для простоты пока используем язык по умолчанию из speak_text

    try:
        while True: # Будем слушать в цикле, пока пользователь не скажет "стоп" или "хватит"
            recognized_text = await listen_and_recognize()

            if recognized_text:
                logger.info(f"Распознанный голос от {user_id}: '{recognized_text}'")

                # Проверяем команды для выхода из голосового режима
                if recognized_text.lower() in ["стоп", "хватит", "закончить", "stop", "enough", "выйти"]:
                    await speak_text("Режим голосового общения деактивирован. До свидания!")
                    await update.message.reply_text("Режим голосового общения деактивирован.")
                    logger.info(f"Голосовой режим деактивирован пользователем {user_id}.")
                    break # Выходим из цикла

                # Отправляем распознанный текст в Gemini
                gemini_response_text = await get_gemini_response(recognized_text)

                if gemini_response_text:
                    # Отвечаем голосом (на русском или украинском, как настроено по умолчанию в speak_text)
                    await speak_text(gemini_response_text, lang='ru') # Или 'uk'
                    # Также отправляем ответ текстом в Telegram
                    await update.message.reply_text(f"Оракул-TG (голосом): _{gemini_response_text}_", parse_mode=ParseMode.MARKDOWN)
                    logger.info(f"Голосовой ответ Оракула-TG пользователю {user_id}: '{gemini_response_text[:50]}...'")
                else:
                    await speak_text("Извините, я не могу сейчас ответить. Пожалуйста, попробуйте еще раз.")
                    await update.message.reply_text("Извините, Оракул-TG не смог дать голосовой ответ.")
                    logger.warning(f"Gemini вернул пустой ответ для голосового запроса от {user_id}.")
            else:
                await speak_text("Я вас не расслышал. Повторите, пожалуйста, или скажите 'стоп' чтобы завершить.")
                await update.message.reply_text("Я вас не расслышал. Повторите, пожалуйста, или скажите 'стоп' чтобы завершить.")

    except Exception as e:
        logger.error(f"Общая ошибка в голосовом режиме для пользователя {user_id}: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка в голосовом режиме. Пожалуйста, попробуйте позже.")