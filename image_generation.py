# image_generation.py
import requests
import base64
import logging
from config import STABILITY_API_KEY # Импортируем ключ из config.py

logger = logging.getLogger(__name__)

# URL для API Stability AI (Stable Diffusion XL)
STABILITY_API_URL = "https://api.stability.ai/v1/generation/stable-diffusion-xl-beta-v2-2-2/text-to-image"

async def generate_image(prompt: str) -> str | None:
    """
    Генерирует изображение на основе текстового описания (промпта)
    с использованием Stability AI.
    Возвращает base64-строку изображения или None в случае ошибки.
    """
    if not STABILITY_API_KEY:
        logger.error("Stability AI API ключ не установлен в config.py.")
        return None

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {STABILITY_API_KEY}"
    }

    payload = {
        "text_prompts": [
            {
                "text": prompt,
                "weight": 1
            }
        ],
        "cfg_scale": 7,
        "height": 512,
        "width": 512,
        "samples": 1,
        "steps": 30,
    }

    try:
        logger.info(f"Отправка запроса на генерацию изображения с промптом: '{prompt[:100]}...'")
        response = requests.post(
            STABILITY_API_URL,
            headers=headers,
            json=payload
        )
        response.raise_for_status() # Вызывает исключение для ошибок HTTP (4xx или 5xx)

        data = response.json()

        if data and "artifacts" in data and len(data["artifacts"]) > 0:
            # Изображение возвращается в base64
            base64_image = data["artifacts"][0]["base64"]
            logger.info("Изображение успешно сгенерировано Stability AI.")
            return base64_image
        else:
            logger.warning("Stability AI вернул некорректный или пустой ответ для изображения.")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка HTTP при запросе к Stability AI: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка при генерации изображения: {e}", exc_info=True)
        return None