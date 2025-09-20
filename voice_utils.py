# voice_utils.py
import speech_recognition as sr
from gtts import gTTS
import os
import logging
import asyncio
import tempfile
from pydub import AudioSegment
from pydub.playback import play
# Строка 'from pydub.utils import get_probes_from_codec_paths' УДАЛЕНА!

logger = logging.getLogger(__name__)

# Следующие строки были удалены, так как ffmpeg.exe и ffprobe.exe
# теперь должны быть в PATH или непосредственно в папке Python
# os.environ["FFPROBE_PATH"] = r"C:\ffmpeg\bin\ffprobe.exe"
# os.environ["FFMPEG_PATH"] = r"C:\ffmpeg\bin\ffmpeg.exe"
# get_probes_from_codec_paths()


# Объект для распознавания речи
recognizer = sr.Recognizer()

async def listen_and_recognize() -> str | None:
    """
    Слушает микрофон и распознает речь.
    Возвращает распознанный текст или None в случае ошибки.
    """
    with sr.Microphone() as source:
        logger.info("Слушаю ваш голос...")
        try:
            # Установим порог шума адаптивно
            recognizer.adjust_for_ambient_noise(source)
            # Увеличили таймауты, чтобы дать больше времени на реакцию и фразу
            audio = recognizer.listen(source, timeout=10, phrase_time_limit=15)
            logger.info("Распознаю речь...")
            # Используем Google Web Speech API для распознавания
            text = await asyncio.to_thread(
                recognizer.recognize_google, audio, language="ru-RU" # Можно "uk-UA" для украинского
            )
            logger.info(f"Распознано: '{text}'")
            return text
        except sr.UnknownValueError:
            logger.warning("Не удалось распознать речь.")
            return None
        except sr.RequestError as e:
            logger.error(f"Ошибка запроса к сервису распознавания речи: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Неизвестная ошибка при прослушивании или распознавании: {e}", exc_info=True)
            return None

async def speak_text(text: str, lang: str = 'ru') -> bool:
    """
    Преобразует текст в речь и воспроизводит её с помощью gTTS и pydub.
    """
    filepath = None # Объявляем filepath здесь, чтобы он был доступен в finally
    try:
        # Создаем временный MP3 файл
        # tempfile гарантирует уникальное имя файла
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            filepath = fp.name

        tts = gTTS(text=text, lang=lang)
        # Сохраняем в отдельном потоке, так как gTTS.save() может быть блокирующим
        await asyncio.to_thread(tts.save, filepath)
        logger.info(f"Сгенерирован аудиофайл: {filepath}")

        # Загружаем аудиофайл с помощью pydub и воспроизводим его
        audio = AudioSegment.from_file(filepath, format="mp3")
        # Воспроизводим в отдельном потоке, так как play() является блокирующим
        await asyncio.to_thread(play, audio)

        logger.info(f"Воспроизведен текст: '{text}'")
        return True
    except Exception as e:
        logger.error(f"Ошибка при синтезе или воспроизведении речи: {e}", exc_info=True)
        return False
    finally:
        # Удаляем временный файл после воспроизведения
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Удален временный аудиофайл: {filepath}")

# Пример использования (можно закомментировать/удалить после тестирования)
# async def main_test_voice():
#     print("Скажите что-нибудь...")
#     recognized_text = await listen_and_recognize()
#     if recognized_text:
#         print(f"Вы сказали: {recognized_text}")
#         await speak_text(f"Вы сказали: {recognized_text}. Это очень интересно!")
#     else:
#         print("Не могу распознать.")
#         await speak_text("Извините, я вас не расслышал.")

# if __name__ == "__main__":
#     import asyncio
#     # Настройка базового логирования для теста
#     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     asyncio.run(main_test_voice())