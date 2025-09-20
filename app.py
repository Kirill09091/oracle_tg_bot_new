import customtkinter
import os
import asyncio
import threading
import logging
import pyperclip

# Реальные импорты для работы с API и голосом
import google.generativeai as genai
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from gtts import gTTS
from pydub import AudioSegment
from pydub.playback import play
import speech_recognition as sr

# ИМПОРТИРУЕМ НАШИ НАСТРОЙКИ ИЗ config.py
import config

# Импортируем функции из других файлов
from handlers import ( # Все обработчики команд Telegram
    start_command,
    text_message_handler,
    generate_image_command,
    generate_and_post_to_channel,
    create_poll_command,
    voice_command
)
# Функции из telegram_utils и voice_utils теперь вызываются напрямую или через app.py
# telegram_utils.py и voice_utils.py должны быть в той же папке для импорта

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

customtkinter.set_appearance_mode("Dark")
customtkinter.set_default_color_theme("blue")

# --- Инициализация Gemini API ---
gemini_model = None
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
    try:
        gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        logger.info("Gemini API успешно настроен.")
    except Exception as e:
        logger.error(f"Ошибка при настройке Gemini API: {e}. Проверьте ваш API ключ.")
else:
    logger.error("Gemini API Key не найден в config.py. Пожалуйста, добавьте его.")

# --- Инициализация Telegram Bot API ---
# Объект бота инициализируется здесь, чтобы быть доступным для функций publish_*
telegram_bot_instance = None # Переименовал, чтобы не конфликтовать с telegram.Bot
if config.TELEGRAM_BOT_TOKEN:
    try:
        telegram_bot_instance = Bot(token=config.TELEGRAM_BOT_TOKEN)
        logger.info("Telegram Bot API успешно настроен.")
    except Exception as e:
        logger.error(f"Ошибка при настройке Telegram API: {e}. Проверьте ваш токен.")
else:
    logger.warning("Telegram Bot Token не найден в config.py. Функции Telegram будут недоступны.")

# --- РЕАЛЬНЫЕ ФУНКЦИИ ---
async def get_gemini_response(prompt: str) -> str:
    """Получение ответа от Gemini."""
    if not gemini_model:
        return "Ошибка: Gemini API не настроен."
    logger.info(f"Запрос к Gemini: '{prompt[:50]}...'")
    try:
        response = gemini_model.generate_content(prompt)
        text_response = response.text
        logger.info(f"Получен ответ от Gemini: '{text_response[:50]}...'")
        return text_response
    except Exception as e:
        logger.error(f"Ошибка при обращении к Gemini API: {e}")
        return "Произошла ошибка при получении ответа от Оракула."

async def generate_post_text(topic: str, style: str) -> str:
    """Генерация поста с помощью Gemini."""
    if not gemini_model:
        return "Ошибка: Gemini API не настроен."
    prompt = f"Сгенерируй пост на тему '{topic}' в стиле '{style}'. Текст должен быть интересным и полезным для читателей, содержать эмодзи и хештеги."
    logger.info(f"Начинаю генерацию поста на тему '{topic}' в стиле '{style}'...")
    try:
        response = gemini_model.generate_content(prompt)
        text = response.text
        logger.info("Пост успешно сгенерирован.")
        return text
    except Exception as e:
        logger.error(f"Ошибка при генерации поста: {e}")
        return f"Произошла ошибка при генерации поста: {e}"

async def suggest_topic() -> str:
    """Предлагает тему для поста с помощью Gemini."""
    if not gemini_model:
        return "Ошибка: Gemini API не настроен."
    prompt = "Предложите короткую, интересную тему для поста в социальной сети, связанную с технологиями, творчеством или саморазвитием. Ответьте только темой, без дополнительных слов."
    logger.info("Запрашиваю у Gemini интересную тему для поста...")
    try:
        response = gemini_model.generate_content(prompt)
        topic = response.text.strip().replace('"', '')
        logger.info(f"Сгенерирована тема: '{topic}'")
        return topic
    except Exception as e:
        logger.error(f"Ошибка при генерации темы: {e}")
        return "Произошла ошибка при генерации темы."

async def generate_poll() -> tuple[str, list[str]]:
    """Генерирует вопрос и варианты ответов для опроса с помощью Gemini."""
    if not gemini_model:
        return "Ошибка: Gemini API не настроен.", [""]

    prompt = "Предложите интересный вопрос для опроса в социальной сети и четыре варианта ответа. Верните ответ в формате JSON: {'question': 'Ваш вопрос', 'options': ['Вариант 1', 'Вариант 2', 'Вариант 3', 'Вариант 4']}"
    logger.info("Запрашиваю у Gemini вопрос и варианты для опроса...")
    try:
        response = gemini_model.generate_content(prompt)
        import json
        poll_data = json.loads(response.text)
        question = poll_data.get('question', 'Вопрос без текста.')
        options = poll_data.get('options', ['Нет вариантов.'])
        logger.info(f"Сгенерирован опрос: '{question}'")
        return question, options
    except Exception as e:
        logger.error(f"Ошибка при генерации опроса: {e}")
        return "Произошла ошибка при генерации опроса.", [""]

async def publish_text_message(chat_id: str, text: str) -> bool:
    """Публикация текстового сообщения в Telegram."""
    if not telegram_bot_instance:
        logger.error("Telegram Bot API не настроен. Не могу опубликовать пост.")
        return False
    logger.info(f"Попытка публикации текста в канал {chat_id}...")
    try:
        await telegram_bot_instance.send_message(chat_id=chat_id, text=text)
        logger.info("Пост успешно опубликован!")
        return True
    except Exception as e:
        logger.error(f"Ошибка публикации поста: {e}")
        return False

async def publish_poll(chat_id: str, question: str, options: list[str]) -> bool:
    """Публикует опрос в Telegram."""
    if not telegram_bot_instance:
        logger.error("Telegram Bot API не настроен. Не могу опубликовать опрос.")
        return False
    logger.info(f"Попытка опубликовать опрос в канал {chat_id}...")
    try:
        await telegram_bot_instance.send_poll(
            chat_id=chat_id,
            question=question,
            options=options,
            is_anonymous=True
        )
        logger.info("Опрос успешно опубликован!")
        return True
    except Exception as e:
        logger.error(f"Ошибка публикации опроса: {e}")
        return False

async def speak_text(text: str, lang: str = 'ru') -> bool:
    """Воспроизведение текста голосом."""
    logger.info(f"Воспроизвожу голос: '{text[:50]}...'")
    try:
        tts = gTTS(text=text, lang=lang)
        tts.save("temp_audio.mp3")
        song = AudioSegment.from_mp3("temp_audio.mp3")
        play(song)
        os.remove("temp_audio.mp3")
        logger.info("Воспроизведение завершено.")
        return True
    except Exception as e:
        logger.error(f"Ошибка воспроизведения голоса: {e}")
        return False

async def listen_and_recognize() -> str | None:
    """Распознавание речи."""
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    
    logger.info("Слушаю ваш голос... Скажите что-нибудь.")
    await speak_text("Я вас слушаю.")
    
    try:
        with mic as source:
            recognizer.adjust_for_ambient_noise(source)
            audio = recognizer.listen(source, timeout=5)
        
        logger.info("Обрабатываю аудио...")
        text = recognizer.recognize_google(audio, language="ru-RU")
        logger.info(f"Голос распознан: '{text}'")
        return text
    except sr.UnknownValueError:
        logger.warning("Голос не распознан.")
        return None
    except sr.RequestError as e:
        logger.error(f"Ошибка сервиса распознавания речи: {e}")
        return None
    except Exception as e:
        logger.error(f"Ошибка распознавания речи: {e}")
        return None

# --- КОНЕЦ РЕАЛЬНЫХ ФУНКЦИЙ ---


class TextboxHandler(logging.Handler):
    """Кастомный обработчик логов для вывода в CTkTextbox."""
    def __init__(self, textbox):
        super().__init__()
        self.textbox = textbox
        self.textbox.tag_config("info", foreground="#A0A0A0")
        self.textbox.tag_config("warning", foreground="#FFA500")
        self.textbox.tag_config("error", foreground="#FF4500")
        self.textbox.tag_config("critical", foreground="#FF0000")
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        msg = self.format(record)
        self.textbox.configure(state="normal")
        if record.levelno == logging.INFO:
            self.textbox.insert("end", msg + "\n", "info")
        elif record.levelno == logging.WARNING:
            self.textbox.insert("end", msg + "\n", "warning")
        elif record.levelno >= logging.ERROR:
            self.textbox.insert("end", msg + "\n", "error")
        else:
            self.textbox.insert("end", msg + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()

        self.title("Оракул-Мастер Постов")
        self.geometry("1200x900")
        self.resizable(True, True)

        self.chat_history = []
        self.current_async_task = None
        self.telegram_app = None # Для хранения экземпляра Telegram Application

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self.api_settings_frame = customtkinter.CTkFrame(self)
        self.api_settings_frame.grid(row=0, column=0, padx=10, pady=(10,5), sticky="ew")
        self.api_settings_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        customtkinter.CTkLabel(self.api_settings_frame, text="Gemini API Key:").grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")
        self.gemini_api_entry = customtkinter.CTkEntry(self.api_settings_frame, placeholder_text="Из config.py")
        self.gemini_api_entry.grid(row=0, column=1, padx=(0, 5), pady=5, sticky="ew")
        self.gemini_api_entry.insert(0, config.GEMINI_API_KEY)
        self.gemini_api_entry.configure(state="disabled")

        customtkinter.CTkLabel(self.api_settings_frame, text="Bot Token:").grid(row=0, column=3, padx=(10, 5), pady=5, sticky="w")
        self.bot_token_entry = customtkinter.CTkEntry(self.api_settings_frame, placeholder_text="Из config.py")
        self.bot_token_entry.grid(row=0, column=4, padx=(0, 5), pady=5, sticky="ew")
        self.bot_token_entry.insert(0, config.TELEGRAM_BOT_TOKEN)
        self.bot_token_entry.configure(state="disabled")

        customtkinter.CTkLabel(self.api_settings_frame, text="Channel ID:").grid(row=1, column=0, padx=(10, 5), pady=5, sticky="w")
        self.channel_id_entry = customtkinter.CTkEntry(self.api_settings_frame, placeholder_text="Из config.py")
        self.channel_id_entry.grid(row=1, column=1, padx=(0, 5), pady=5, sticky="ew")
        self.channel_id_entry.insert(0, config.TELEGRAM_CHANNEL_ID)
        self.channel_id_entry.configure(state="disabled")

        customtkinter.CTkLabel(self.api_settings_frame, text="Stability AI Key:").grid(row=1, column=3, padx=(10, 5), pady=5, sticky="w")
        self.stability_api_entry = customtkinter.CTkEntry(self.api_settings_frame, placeholder_text="Из config.py")
        self.stability_api_entry.grid(row=1, column=4, padx=(0, 5), pady=5, sticky="ew")
        self.stability_api_entry.insert(0, config.STABILITY_API_KEY)
        self.stability_api_entry.configure(state="disabled")

        self.main_work_area = customtkinter.CTkFrame(self)
        self.main_work_area.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.main_work_area.grid_columnconfigure((0, 1), weight=1)
        self.main_work_area.grid_rowconfigure(0, weight=1)

        self.chat_frame = customtkinter.CTkFrame(self.main_work_area)
        self.chat_frame.grid_rowconfigure(1, weight=1)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        customtkinter.CTkLabel(self.chat_frame, text="ЧАТ С ОРАКУЛОМ (F1)", font=customtkinter.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=(5,0))

        self.chat_display = customtkinter.CTkTextbox(self.chat_frame, wrap="word", state="disabled", height=300)
        self.chat_display.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        self.chat_input = customtkinter.CTkEntry(self.chat_frame, placeholder_text="Введите сообщение...")
        self.chat_input.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        self.chat_input.bind("<Return>", self.send_chat_message)
        self.chat_input.bind("<Control-Return>", self.send_chat_message)

        self.chat_buttons_frame = customtkinter.CTkFrame(self.chat_frame, fg_color="transparent")
        self.chat_buttons_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.chat_buttons_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.send_button = customtkinter.CTkButton(self.chat_buttons_frame, text="Отправить (Enter/Ctrl+Enter)", command=self.send_chat_message)
        self.send_button.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="ew")

        self.voice_input_button = customtkinter.CTkButton(self.chat_buttons_frame, text="Начать голос (Ctrl+G)", command=self.start_voice_chat)
        self.voice_input_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.voice_stop_button = customtkinter.CTkButton(self.chat_buttons_frame, text="Стоп голос (Ctrl+S)", command=self.stop_voice_chat)
        self.voice_stop_button.grid(row=0, column=2, padx=(5, 0), pady=5, sticky="ew")


        self.generate_publish_frame = customtkinter.CTkFrame(self.main_work_area)
        self.generate_publish_frame.grid_columnconfigure(0, weight=1)
        self.generate_publish_frame.grid_rowconfigure(7, weight=1)

        customtkinter.CTkLabel(self.generate_publish_frame, text="ГЕНЕРАЦИЯ ПОСТОВ (F2)", font=customtkinter.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=(5,0))

        customtkinter.CTkLabel(self.generate_publish_frame, text="Тема для поста:").grid(row=1, column=0, padx=10, pady=(10,0), sticky="w")
        self.post_topic_entry = customtkinter.CTkEntry(self.generate_publish_frame, placeholder_text="Например: 'Преимущества ИИ в обучении'")
        self.post_topic_entry.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="ew")

        self.suggest_topic_button = customtkinter.CTkButton(self.generate_publish_frame, text="Сгенерировать тему", command=self.generate_topic)
        self.suggest_topic_button.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")

        customtkinter.CTkLabel(self.generate_publish_frame, text="Стиль поста:").grid(row=4, column=0, padx=10, pady=(10,0), sticky="w")
        self.post_style_combobox = customtkinter.CTkComboBox(self.generate_publish_frame,
                                                              values=["Обычный", "Формальный", "Креативный", "Юмористический", "Научный"])
        self.post_style_combobox.grid(row=5, column=0, padx=10, pady=(0, 5), sticky="ew")
        self.post_style_combobox.set("Обычный")

        self.generate_post_button = customtkinter.CTkButton(self.generate_publish_frame, text="Сгенерировать пост (Ctrl+Q)", command=self.generate_post)
        self.generate_post_button.grid(row=6, column=0, padx=10, pady=(5, 5), sticky="ew")

        self.clear_post_button = customtkinter.CTkButton(self.generate_publish_frame, text="Очистить пост", command=self.clear_generated_post)
        self.clear_post_button.grid(row=7, column=0, padx=10, pady=(0, 10), sticky="ew")

        self.generated_post_display = customtkinter.CTkTextbox(self.generate_publish_frame, wrap="word", state="disabled", height=200)
        self.generated_post_display.grid(row=8, column=0, padx=10, pady=5, sticky="nsew")

        self.copy_post_button = customtkinter.CTkButton(self.generate_publish_frame, text="Копировать пост (Ctrl+C)", command=self.copy_post_to_clipboard)
        self.copy_post_button.grid(row=9, column=0, padx=10, pady=(5, 5), sticky="ew")

        self.publish_post_button = customtkinter.CTkButton(self.generate_publish_frame, text="Опубликовать пост (Ctrl+P)", command=self.publish_post_ui)
        self.publish_post_button.grid(row=10, column=0, padx=10, pady=(0, 10), sticky="ew")


        self.poll_frame = customtkinter.CTkFrame(self.main_work_area)
        self.poll_frame.grid_columnconfigure(0, weight=1)
        self.poll_frame.grid_rowconfigure(4, weight=1)
        
        customtkinter.CTkLabel(self.poll_frame, text="СОЗДАНИЕ ОПРОСА (F3)", font=customtkinter.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=(5,0))

        customtkinter.CTkLabel(self.poll_frame, text="Вопрос для опроса:").grid(row=1, column=0, padx=10, pady=(10,0), sticky="w")
        self.poll_question_entry = customtkinter.CTkEntry(self.poll_frame, placeholder_text="Например: 'Какой ваш любимый цвет?'")
        self.poll_question_entry.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="ew")

        customtkinter.CTkLabel(self.poll_frame, text="Варианты ответов (каждый с новой строки):").grid(row=3, column=0, padx=10, pady=(10,0), sticky="w")
        self.poll_options_textbox = customtkinter.CTkTextbox(self.poll_frame, wrap="word", height=100)
        self.poll_options_textbox.grid(row=4, column=0, padx=10, pady=(0, 5), sticky="nsew")

        self.generate_poll_button = customtkinter.CTkButton(self.poll_frame, text="Сгенерировать Опрос", command=self.generate_poll_ui)
        self.generate_poll_button.grid(row=5, column=0, padx=10, pady=(5, 5), sticky="ew")

        self.publish_poll_button = customtkinter.CTkButton(self.poll_frame, text="Опубликовать Опрос (Ctrl+O)", command=self.publish_poll_ui)
        self.publish_poll_button.grid(row=6, column=0, padx=10, pady=(0, 10), sticky="ew")


        self.logs_frame = customtkinter.CTkFrame(self)
        self.logs_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.logs_frame.grid_columnconfigure(0, weight=1)
        self.logs_frame.grid_rowconfigure(1, weight=1) # Сделать текстовое поле логов растягиваемым

        customtkinter.CTkLabel(self.logs_frame, text="ЛОГИ ПРИЛОЖЕНИЯ (F4)", font=customtkinter.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=(5,0))
        self.logs_display = customtkinter.CTkTextbox(self.logs_frame, wrap="word", state="disabled", height=120)
        self.logs_display.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="nsew") # Уменьшим pady снизу для кнопки

        # Кнопка для копирования логов
        self.copy_logs_button = customtkinter.CTkButton(self.logs_frame, text="Копировать логи", command=self.copy_logs_to_clipboard)
        self.copy_logs_button.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="ew")


        self.log_handler = TextboxHandler(self.logs_display)
        logger.addHandler(self.log_handler)
        self.log_message("Приложение запущено. Используйте F1, F2, F3 для переключения режимов. F4 для фокуса на логах.", level="info")

        self.bind("<F1>", lambda e: self.show_frame(self.chat_frame, self.chat_input, "left"))
        self.bind("<F2>", lambda e: self.show_frame(self.generate_publish_frame, self.post_topic_entry, "right"))
        self.bind("<F3>", lambda e: self.show_frame(self.poll_frame, self.poll_question_entry, "right"))
        self.bind("<F4>", lambda e: self.logs_display.focus_set())

        self.bind("<Control-g>", self.start_voice_chat)
        self.bind("<Control-s>", self.stop_voice_chat)
        self.bind("<Control-q>", self.generate_post)
        self.bind("<Control-c>", self.copy_post_to_clipboard)
        self.bind("<Control-p>", self.publish_post_ui)
        self.bind("<Control-o>", self.publish_poll_ui)

        self.active_frame = None
        self.show_frame(self.chat_frame, self.chat_input, "left")

        # Запускаем Telegram бота в отдельном потоке
        self.telegram_bot_thread = threading.Thread(target=self.start_telegram_bot_thread, daemon=True)
        self.telegram_bot_thread.start()
        self.log_message("Поток Telegram бота запущен.", level="info")

        # Обработчик закрытия окна CustomTkinter
        self.protocol("WM_DELETE_WINDOW", self.on_closing)


    def on_closing(self):
        """Обрабатывает закрытие окна приложения."""
        self.log_message("Приложение закрывается. Останавливаю Telegram бота...", level="info")
        if self.telegram_app:
            # Остановка polling
            # run_until_complete(stop()) не нужна, т.к. stop() уже асинхронная и будет вызвана
            # в контексте loop.call_soon_threadsafe
            self.telegram_app.stop() 
            self.telegram_app.shutdown() # Добавлено для более чистого завершения
            self.log_message("Telegram бот остановлен.", level="info")
        self.destroy() # Закрываем окно CustomTkinter

    def start_telegram_bot_thread(self):
        """Функция для запуска Telegram бота в отдельном потоке."""
        if not config.TELEGRAM_BOT_TOKEN:
            self.log_message("Telegram Bot Token не настроен в config.py. Бот не будет запущен.", level="error")
            return

        try:
            # Создаем новый цикл событий для этого потока
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            self.telegram_app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

            # Добавляем обработчики команд и сообщений из handlers.py
            self.telegram_app.add_handler(CommandHandler("start", start_command))
            self.telegram_app.add_handler(CommandHandler("image", generate_image_command))
            self.telegram_app.add_handler(CommandHandler("post", generate_and_post_to_channel))
            self.telegram_app.add_handler(CommandHandler("poll", create_poll_command))
            self.telegram_app.add_handler(CommandHandler("voice", voice_command))
            self.telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

            self.log_message("Telegram бот готов к запуску polling...", level="info")
            # Запускаем polling внутри созданного цикла событий.
            # run_polling() является блокирующей, поэтому она должна быть запущена в loop.run_until_complete()
            loop.run_until_complete(self.telegram_app.run_polling(allowed_updates=Update.ALL_TYPES))
            self.log_message("Telegram бот polling завершен.", level="info") # Это сообщение появится только после остановки
        except Exception as e:
            self.log_message(f"Ошибка при запуске Telegram бота: {e}", level="critical")
        finally:
            # Закрываем цикл событий, когда он больше не нужен
            if loop and not loop.is_running(): # Проверяем, что цикл не запущен, прежде чем закрыть
                loop.close()
                self.log_message("Цикл событий Telegram бота закрыт.", level="info")


    def log_message(self, message: str, level: str = "info"):
        if level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        elif level == "critical":
            logger.critical(message)
        else:
            logger.debug(message)

    def show_frame(self, frame_to_show: customtkinter.CTkFrame, initial_focus_widget=None, position: str = "left"):
        if self.active_frame:
            self.active_frame.grid_forget()

        if position == "left":
            frame_to_show.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        elif position == "right":
            frame_to_show.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        else:
            self.log_message(f"Неизвестная позиция для фрейма: {position}", level="warning")
            return

        self.active_frame = frame_to_show
        if initial_focus_widget:
            initial_focus_widget.focus_set()

        self.log_message(f"Переключен на секцию: {frame_to_show._name.upper().replace('_FRAME', '').replace('_', ' ')}", level="info")

    def _run_async_task(self, coro_func, *args, callback=None, error_callback=None):
        """Запускает асинхронную корутину в отдельном потоке и обрабатывает результат/ошибки."""
        def run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                coro = coro_func(*args)
                result = loop.run_until_complete(coro)
                if callback:
                    self.after(0, lambda: callback(result))
            except asyncio.CancelledError:
                self.log_message("Асинхронная задача отменена.", level="warning")
            except Exception as e:
                self.log_message(f"Ошибка в асинхронной задаче: {type(e).__name__}: {e}", level="error")
                if error_callback:
                    self.after(0, lambda: error_callback(e))
            finally:
                loop.close()
                self.current_async_task = None
            
        if self.current_async_task and self.current_async_task.is_alive():
            self.log_message("Уже выполняется асинхронная задача. Дождитесь её завершения.", level="warning")
            return
            
        thread = threading.Thread(target=run_in_thread, daemon=True)
        self.current_async_task = thread
        thread.start()

    def add_chat_message(self, sender: str, message: str, color_tag: str = ""):
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", f"{sender}: {message}\n", color_tag)
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")

    def send_chat_message(self, event=None):
        user_message = self.chat_input.get().strip()
        if not user_message:
            self.log_message("Сообщение не может быть пустым.", level="warning")
            return

        self.add_chat_message("Вы", user_message)
        self.chat_input.delete(0, "end")
        self.log_message(f"Отправлено сообщение: '{user_message[:50]}...'")

        self._run_async_task(
            get_gemini_response, user_message,
            callback=self.handle_gemini_response,
            error_callback=lambda e: self.add_chat_message("Ошибка", f"Не удалось получить ответ: {e}")
        )

    def handle_gemini_response(self, response: str):
        self.add_chat_message("Оракул", response)
        self._run_async_task(speak_text, response)

    def start_voice_chat(self, event=None):
        self.log_message("Попытка начать голосовой ввод...", level="info")
        self.voice_input_button.configure(state="disabled", text="Слушаю...")
        self.voice_stop_button.configure(state="normal")
        
        self._run_async_task(
            listen_and_recognize,
            callback=self.handle_voice_input,
            error_callback=lambda e: self.log_message(f"Ошибка голосового ввода: {e}", level="error")
        )

    def stop_voice_chat(self, event=None):
        if self.current_async_task and self.current_async_task.is_alive():
            self.current_async_task = None 
            self.log_message("Голосовой ввод остановлен (попытка).", level="warning")
        
        self.voice_input_button.configure(state="normal", text="Начать голос (Ctrl+G)")
        self.voice_stop_button.configure(state="disabled")

    def handle_voice_input(self, recognized_text: str | None):
        self.voice_input_button.configure(state="normal", text="Начать голос (Ctrl+G)")
        self.voice_stop_button.configure(state="disabled")

        if recognized_text:
            self.chat_input.delete(0, "end")
            self.chat_input.insert(0, recognized_text)
            self.send_chat_message()
        else:
            self.log_message("Голос не распознан.", level="warning")

    def generate_topic(self):
        self.log_message("Генерирую тему поста...", level="info")
        self.suggest_topic_button.configure(state="disabled", text="Генерирую...")

        self._run_async_task(
            suggest_topic,
            callback=self.handle_topic,
            error_callback=lambda e: self.log_message(f"Ошибка генерации темы: {e}", level="error")
        )

    def handle_topic(self, topic: str):
        self.post_topic_entry.delete(0, "end")
        self.post_topic_entry.insert(0, topic)
        self.log_message("Тема успешно сгенерирована.", level="info")
        self.suggest_topic_button.configure(state="normal", text="Сгенерировать тему")

    def generate_post(self, event=None):
        topic = self.post_topic_entry.get().strip()
        style = self.post_style_combobox.get()

        if not topic:
            self.log_message("Пожалуйста, введите тему для поста.", level="warning")
            return

        self.log_message(f"Начинаю генерацию поста на тему '{topic}' в стиле '{style}'...", level="info")
        self.generate_post_button.configure(state="disabled", text="Генерирую...")
        self.clear_post_button.configure(state="disabled")
        self.copy_post_button.configure(state="disabled")
        self.publish_post_button.configure(state="disabled")

        self._run_async_task(
            generate_post_text, topic, style,
            callback=self.handle_generated_post,
            error_callback=lambda e: self.log_message(f"Ошибка генерации поста: {e}", level="error")
        )

    def handle_generated_post(self, generated_text: str):
        self.generated_post_display.configure(state="normal")
        self.generated_post_display.delete("1.0", "end")
        self.generated_post_display.insert("end", generated_text)
        self.generated_post_display.configure(state="disabled")
        self.log_message("Пост успешно сгенерирован.", level="info")
        self.generate_post_button.configure(state="normal", text="Сгенерировать пост (Ctrl+Q)")
        self.clear_post_button.configure(state="normal")
        self.copy_post_button.configure(state="normal")
        self.publish_post_button.configure(state="normal")
        self.generated_post_display.focus_set()

    def clear_generated_post(self):
        self.generated_post_display.configure(state="normal")
        self.generated_post_display.delete("1.0", "end")
        self.generated_post_display.configure(state="disabled")
        self.log_message("Поле сгенерированного поста очищено.", level="info")
        self.copy_post_button.configure(state="disabled")
        self.publish_post_button.configure(state="disabled")
        self.post_topic_entry.focus_set()

    def copy_post_to_clipboard(self, event=None):
        post_text = self.generated_post_display.get("1.0", "end").strip()
        if post_text:
            pyperclip.copy(post_text)
            self.log_message("Пост скопирован в буфер обмена.", level="info")
        else:
            self.log_message("Нет поста для копирования.", level="warning")

    def publish_post_ui(self, event=None):
        post_text = self.generated_post_display.get("1.0", "end").strip()
        channel_id = config.TELEGRAM_CHANNEL_ID

        if not channel_id:
            self.log_message("Telegram CHANNEL_ID не указан в config.py.", level="error")
            return
        if not post_text:
            self.log_message("Нет поста для публикации.", level="warning")
            return

        self.log_message(f"Попытка опубликовать пост в канал {channel_id}...", level="info")
        self.publish_post_button.configure(state="disabled", text="Публикую...")

        self._run_async_task(
            publish_text_message, channel_id, post_text,
            callback=self.handle_publish_result,
            error_callback=lambda e: self.log_message(f"Ошибка публикации поста: {e}", level="error")
        )

    def handle_publish_result(self, success: bool):
        if success:
            self.log_message("Пост успешно опубликован!", level="info")
        else:
            self.log_message("Не удалось опубликовать пост.", level="error")
        self.publish_post_button.configure(state="normal", text="Опубликовать пост (Ctrl+P)")

    def generate_poll_ui(self):
        self.log_message("Запрашиваю у Gemini опрос...", level="info")
        self.generate_poll_button.configure(state="disabled", text="Генерирую...")
        self.publish_poll_button.configure(state="disabled")

        self._run_async_task(
            generate_poll,
            callback=self.handle_generated_poll,
            error_callback=lambda e: self.log_message(f"Ошибка генерации опроса: {e}", level="error")
        )

    def handle_generated_poll(self, poll_data: tuple[str, list[str]]):
        question, options = poll_data
        self.poll_question_entry.delete(0, "end")
        self.poll_question_entry.insert(0, question)
        
        self.poll_options_textbox.delete("1.0", "end")
        self.poll_options_textbox.insert("1.0", "\n".join(options))
        
        self.log_message("Опрос успешно сгенерирован.", level="info")
        self.generate_poll_button.configure(state="normal", text="Сгенерировать Опрос")
        self.publish_poll_button.configure(state="normal")
        
    def publish_poll_ui(self, event=None):
        question = self.poll_question_entry.get().strip()
        options = [opt.strip() for opt in self.poll_options_textbox.get("1.0", "end").split("\n") if opt.strip()]
        channel_id = config.TELEGRAM_CHANNEL_ID

        if not channel_id:
            self.log_message("Telegram CHANNEL_ID не указан в config.py.", level="error")
            return
        if not question or not options:
            self.log_message("Вопрос или варианты опроса не могут быть пустыми.", level="warning")
            return

        self.log_message(f"Попытка опубликовать опрос в канал {channel_id}...", level="info")
        self.publish_poll_button.configure(state="disabled", text="Публикую...")

        self._run_async_task(
            publish_poll, channel_id, question, options,
            callback=self.handle_poll_publish_result,
            error_callback=lambda e: self.log_message(f"Ошибка публикации опроса: {e}", level="error")
        )

    def handle_poll_publish_result(self, success: bool):
        if success:
            self.log_message("Опрос успешно опубликован!", level="info")
        else:
            self.log_message("Не удалось опубликовать опрос.", level="error")
        self.publish_poll_button.configure(state="normal", text="Опубликовать Опрос (Ctrl+O)")

    def copy_logs_to_clipboard(self):
        """Копирует содержимое логов в буфер обмена."""
        logs_text = self.logs_display.get("1.0", "end").strip()
        if logs_text:
            pyperclip.copy(logs_text)
            self.log_message("Логи скопированы в буфер обмена.", level="info")
        else:
            self.log_message("Нет логов для копирования.", level="warning")


if __name__ == "__main__":
    app = App()
    app.mainloop()