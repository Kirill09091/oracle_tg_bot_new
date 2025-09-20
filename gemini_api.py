# gemini_api.py
import google.generativeai as genai
import logging
from config import GEMINI_API_KEY # Импортируем ключ из config.py

logger = logging.getLogger(__name__)

# Настройка Gemini API при импорте модуля
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

async def get_gemini_response(prompt: str) -> str | None:
    """
    Отправляет запрос в Gemini API и возвращает сгенерированный текст.
    Возвращает None в случае ошибки или пустого ответа.
    """
    try:
        response = model.generate_content(prompt)
        # Проверяем, есть ли текст в ответе
        if response and response.text:
            return response.text
        else:
            logger.warning(f"Gemini вернул пустой или некорректный ответ для запроса: {prompt}")
            return None # Возвращаем None вместо строки ошибки, чтобы обработчик мог решить
    except Exception as e:
        logger.error(f"Ошибка при запросе к Gemini API: {e}", exc_info=True)
        return None # Возвращаем None вместо строки ошибки