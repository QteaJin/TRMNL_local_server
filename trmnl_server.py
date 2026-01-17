from fastapi import FastAPI, Header, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from typing import Optional
import uvicorn
import logging
import json
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trmnl_api_mock.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="TRMNL Local API Mock")

# --- Конфигурация генерации изображения ---
IMAGE_WIDTH = 800
IMAGE_HEIGHT = 480
FONT_SIZE = 60
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" # Путь к системному шрифту на Raspberry Pi
# Если DejaVuSans-Bold.ttf не найден, замените на другой или загрузите
# Например, можно скачать с Google Fonts и положить рядом с trmnl_server.py:
# FONT_PATH = "arial.ttf"

# Часовой пояс (например, 'Europe/Moscow'). Замените на свой, если нужно.
# Список доступных часовых поясов можно найти тут:
# https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
TIMEZONE = 'Europe/Moscow'
local_tz = pytz.timezone(TIMEZONE)


def log_request_details(request: Request, endpoint_name: str, received_headers: dict):
    """Log full request details including headers for debugging"""
    logger.info(f"\n{'=' * 80}")
    logger.info(f"ENDPOINT: {endpoint_name}")
    logger.info(f"TIMESTAMP: {datetime.now().isoformat()}")
    logger.info(f"METHOD: {request.method}")
    logger.info(f"PATH: {request.url.path}")
    logger.info(f"QUERY STRING: {request.url.query}")

    logger.info("HEADERS RECEIVED:")
    for header_name, header_value in request.headers.items():
        if header_name.lower() not in ['host', 'user-agent', 'accept', 'accept-encoding', 'connection']:
            logger.info(f"  {header_name}: {header_value}")

    logger.info("PARSED PARAMETERS:")
    for param_name, param_value in received_headers.items():
        if param_value is not None:
            logger.info(f"  {param_name}: {param_value}")


def log_response_details(endpoint_name: str, status_code: int, response_body: dict):
    """Log response details for debugging"""
    logger.info(f"RESPONSE STATUS: {status_code}")
    logger.info(f"RESPONSE BODY:")
    logger.info(json.dumps(response_body, indent=2, default=str))
    logger.info(f"{'=' * 80}\n")


@app.get("/api/setup")
async def api_setup(request: Request,
                    id: Optional[str] = Header(None),
                    fw_version: Optional[str] = Header(None),
                    model: Optional[str] = Header(None),
                    status_override: Optional[int] = None):
    """Return a setup response. Use `?status_override=404` to simulate non-200 status.

    Headers received from device:
    - id (from "ID")
    - fw_version (from "FW-Version")
    - model (from "Model")
    """
    # Log incoming request
    log_request_details(request, "GET /api/setup", {
        "id": id,
        "fw_version": fw_version,
        "model": model,
        "status_override": status_override
    })

    status_code = status_override or 200

    if status_code != 200:
        response_body = {
            "status": status_code,
            "message": "simulated status error"
        }
        log_response_details("GET /api/setup", 200, response_body)
        return JSONResponse(status_code=200, content=response_body)

    response_body = {
        "status": 200,
        "api_key": "local-test-api-key",
        "friendly_id": "TRMNL-LOCAL-1234",
        "image_url": str(request.base_url).rstrip("/") + "/images/example.bmp",
        "message": "ok"
    }

    log_response_details("GET /api/setup", 200, response_body)
    return response_body


# --- Функция для генерации BMP с текущим временем ---
def generate_time_image():
    try:
        # Создаем новое черно-белое изображение
        img = Image.new('1', (IMAGE_WIDTH, IMAGE_HEIGHT), color=255)  # 255 = белый фон
        draw = ImageDraw.Draw(img)

        # Загружаем шрифт
        try:
            font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        except IOError:
            logger.warning(f"Шрифт {FONT_PATH} не найден. Использую шрифт по умолчанию.")
            font = ImageFont.load_default()

        # Получаем текущее время в заданном часовом поясе
        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        now_local = now_utc.astimezone(local_tz)

        time_str = now_local.strftime("%H:%M:%S")
        date_str = now_local.strftime("%Y-%m-%d")

        # Определяем размеры текста
        bbox_time = draw.textbbox((0, 0), time_str, font=font)
        text_width_time = bbox_time[2] - bbox_time[0]
        text_height_time = bbox_time[3] - bbox_time[1]

        bbox_date = draw.textbbox((0, 0), date_str, font=font)
        text_width_date = bbox_date[2] - bbox_date[0]
        text_height_date = bbox_date[3] - bbox_date[1]

        # Центрируем текст
        x_time = (IMAGE_WIDTH - text_width_time) / 2
        y_time = (IMAGE_HEIGHT - text_height_time) / 2 - text_height_date / 2  # Чуть выше центра для времени

        x_date = (IMAGE_WIDTH - text_width_date) / 2
        y_date = (IMAGE_HEIGHT - text_height_date) / 2 + text_height_time / 2  # Чуть ниже центра для даты

        # Рисуем текст черным цветом (0)
        draw.text((x_time, y_time), time_str, font=font, fill=0)
        draw.text((x_date, y_date), date_str, font=font, fill=0)

        # Сохраняем изображение в BMP формате
        img.save(last_generated_image_path)
        logger.info(f"Сгенерировано новое изображение: {last_generated_image_path}")
    except Exception as e:
        logger.error(f"Ошибка при генерации изображения: {e}")
        # В случае ошибки, убедимся, что файл display.bmp существует, даже если он пустой
        if not os.path.exists(last_generated_image_path):
            Image.new('1', (IMAGE_WIDTH, IMAGE_HEIGHT), color=0).save(last_generated_image_path)


@app.get("/api/display")
async def api_display(request: Request,
                      id: Optional[str] = Header(None),
                      access_token: Optional[str] = Header(None)):
    log_request_details(request, "GET /api/display", {"id": id})

    # Генерируем новое изображение перед каждым запросом display
    generate_time_image()

    # Генерируем новый ID файла, чтобы заставить ESP32 обновить картинку
    unique_filename = f"f_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    content = {
        "status": 0,  # КРИТИЧЕСКИ ВАЖНО: 0 вместо 200
        "image_url": f"{str(request.base_url).rstrip('/')}/images/display.bmp",
        "filename": unique_filename,
        "update_firmware": False,
        "firmware_url": None,
        "refresh_rate": 60,  # Обновление каждые 60 секунд
        "reset_firmware": False
    }

    log_response_details("GET /api/display", 200, content)
    return JSONResponse(status_code=200, content=content)


@app.post("/api/log")
async def api_log(request: Request, id: Optional[str] = Header(None), access_token: Optional[str] = Header(None),
                  no_content: Optional[bool] = False):
    """Accept logs in format {"logs": [ ... ]}. Use `?no_content=1` to get 204 response.

    Headers received from device:
    - id (from "ID")
    - access_token (from "Access-Token")
    """
    # Log incoming request headers
    log_request_details(request, "POST /api/log", {
        "id": id,
        "access_token": access_token,
        "no_content": no_content
    })

    if no_content:
        response_body = {"result": "ok"}
        return JSONResponse(status_code=200, content=response_body)

    try:
        body = await request.json()
        logger.info("REQUEST BODY:")
        logger.info(json.dumps(body, indent=2, default=str))
    except Exception as e:
        logger.error(f"Failed to parse JSON body: {e}")
        response_body = {"error": "invalid json"}
        log_response_details("POST /api/log", 400, response_body)
        return JSONResponse(status_code=400, content=response_body)

    if not isinstance(body, dict) or "logs" not in body or not isinstance(body["logs"], list):
        response_body = {"error": "expected {\"logs\": [...] }"}
        log_response_details("POST /api/log", 400, response_body)
        return JSONResponse(status_code=400, content=response_body)

    # Basic validation of first log entry if present
    if len(body["logs"]) > 0:
        first = body["logs"][0]
        required = ["created_at", "id", "message"]
        missing = [k for k in required if k not in first]
        if missing:
            response_body = {"error": f"missing fields: {missing}"}
            log_response_details("POST /api/log", 400, response_body)
            return JSONResponse(status_code=400, content=response_body)

    response_body = {"result": "ok"}
    log_response_details("POST /api/log", 200, response_body)
    return JSONResponse(status_code=200, content=response_body)


@app.get("/firmware/{version}/firmware.bin")
async def firmware_bin(request: Request, version: str, redirect: Optional[bool] = False, size: Optional[int] = None):
    """Serve a dummy firmware binary for given version.

    Options:
    - ?redirect=1 -> return 307 to signed binary
    - ?size=<bytes> -> return payload of requested size (for OTA testing)
    """
    logger.info(f"\n{'=' * 80}")
    logger.info(f"ENDPOINT: GET /firmware/{{version}}/firmware.bin")
    logger.info(f"TIMESTAMP: {datetime.now().isoformat()}")
    logger.info(f"PATH: {request.url.path}")
    logger.info(f"QUERY STRING: {request.url.query}")
    logger.info(f"Parameters:")
    logger.info(f"  version: {version}")
    logger.info(f"  redirect: {redirect}")
    logger.info(f"  size: {size}")

    if redirect:
        url = str(request.base_url).rstrip("/") + f"/firmware/{version}/signed.bin"
        logger.info(f"RESPONSE STATUS: 307")
        logger.info(f"Location: {url}")
        logger.info(f"{'=' * 80}\n")
        return RedirectResponse(url=url, status_code=307)

    if size is None:
        content = b"FAKEFIRMWAREDATA-" + version.encode()
    else:
        # generate pseudo-random content pattern of requested size
        chunk = (b"FIRMWARE-" + version.encode() + b"-")
        repeated = chunk * (size // len(chunk)) + chunk[: (size % len(chunk))]
        content = repeated

    headers = {
        "Content-Disposition": f'attachment; filename="firmware-{version}.bin"',
        "Content-Length": str(len(content))
    }

    logger.info(f"RESPONSE STATUS: 200")
    logger.info(f"RESPONSE HEADERS:")
    logger.info(f"  Content-Length: {len(content)}")
    logger.info(f"  Content-Disposition: {headers['Content-Disposition']}")
    logger.info(f"RESPONSE BODY: Binary firmware data ({len(content)} bytes)")
    logger.info(f"{'=' * 80}\n")

    return Response(content=content, media_type="application/octet-stream", headers=headers)


@app.head("/firmware/{version}/firmware.bin")
async def firmware_head(request: Request, version: str, size: Optional[int] = None):
    """Respond to HEAD with correct headers (Content-Length etc.)"""
    logger.info(f"\n{'=' * 80}")
    logger.info(f"ENDPOINT: HEAD /firmware/{{version}}/firmware.bin")
    logger.info(f"TIMESTAMP: {datetime.now().isoformat()}")
    logger.info(f"PATH: {request.url.path}")
    logger.info(f"QUERY STRING: {request.url.query}")
    logger.info(f"Parameters:")
    logger.info(f"  version: {version}")
    logger.info(f"  size: {size}")

    # Reuse logic to determine length without creating giant payload
    if size is None:
        content_length = len(b"FAKEFIRMWAREDATA-" + version.encode())
    else:
        chunk = (b"FIRMWARE-" + version.encode() + b"-")
        content_length = size
    headers = {
        "Content-Disposition": f'attachment; filename="firmware-{version}.bin"',
        "Content-Length": str(content_length)
    }

    logger.info(f"RESPONSE STATUS: 200")
    logger.info(f"RESPONSE HEADERS:")
    logger.info(f"  Content-Length: {content_length}")
    logger.info(f"  Content-Disposition: {headers['Content-Disposition']}")
    logger.info(f"{'=' * 80}\n")

    return Response(content=b"", media_type="application/octet-stream", headers=headers)


@app.get("/firmware/{version}/signed.bin")
async def firmware_signed(request: Request, version: str):
    """Simulate a signed firmware binary target for redirects."""
    logger.info(f"\n{'=' * 80}")
    logger.info(f"ENDPOINT: GET /firmware/{{version}}/signed.bin")
    logger.info(f"TIMESTAMP: {datetime.now().isoformat()}")
    logger.info(f"PATH: {request.url.path}")
    logger.info(f"Parameters:")
    logger.info(f"  version: {version}")

    content = b"SIGNEDFAKEFIRMWARE-" + version.encode()
    headers = {"Content-Disposition": f'attachment; filename="firmware-{version}-signed.bin"'}

    logger.info(f"RESPONSE STATUS: 200")
    logger.info(f"RESPONSE HEADERS:")
    logger.info(f"  Content-Length: {len(content)}")
    logger.info(f"  Content-Disposition: {headers['Content-Disposition']}")
    logger.info(f"RESPONSE BODY: Binary signed firmware data ({len(content)} bytes)")
    logger.info(f"{'=' * 80}\n")

    return Response(content=content, media_type="application/octet-stream", headers=headers)


import os
from fastapi.responses import FileResponse
from fastapi import HTTPException

# Create images directory if it doesn't exist
os.makedirs("images", exist_ok=True)


@app.get("/images/{name}")
async def serve_image(name: str, request: Request):
    """
    Просто отдает файл из папки /images по его имени.
    """
    log_request_details(request, f"GET /images/{{name}}", {"name": name})

    # Защита от попыток выйти за пределы папки
    if '..' in name or name.startswith('/'):
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Путь к файлу на диске
    image_path = os.path.join("images", name)

    # Проверяем, существует ли файл
    if os.path.exists(image_path):
        logger.info(f"Файл найден, отправляю: {image_path}")
        return FileResponse(image_path, media_type="image/bmp")

    # Если файла нет
    logger.error(f"Файл НЕ найден: {image_path}")
    raise HTTPException(status_code=404, detail="Image not found on disk")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=65111, log_level="info")
