# 🤖 Ultimate Video Downloader Bot

Профессиональный Telegram бот для скачивания видео с 10+ платформ без водяных знаков.

## ✨ Возможности

- **🎥 Мульти-платформенность**: YouTube, TikTok (без WM), Instagram, Pinterest, VK и др.
- **📁 Файлы до 2GB**: Поддержка Local Bot API Server
- **⚡ Высокая производительность**: Асинхронная архитектура
- **📉 Экономия ресурсов**: Режим `LOW_MEMORY_MODE` для 512MB RAM
- **💎 Premium система**: Подписки, Telegram Stars
- **👑 Админ-панель**: Управление пользователями и статистикой

---

## 🚀 Deployment на Koyeb

### 1. Fork репозитория на GitHub

### 2. Создайте приложение в Koyeb
- Подключите GitHub репозиторий
- Выберите ветку `main`

### 3. Добавьте переменные окружения (Secrets):

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен от @BotFather |
| `ADMIN_IDS` | ID администраторов |
| `TELEGRAM_API_ID` | От https://my.telegram.org (для 2GB файлов) |
| `TELEGRAM_API_HASH` | От https://my.telegram.org |

### 4. Настройки сервиса:
- **Instance**: nano (512MB) или small (1GB)
- **Region**: fra (Frankfurt)
- **Port**: 8000 (автоматически)

### 5. Deploy!

---

## 🐳 Docker Compose (Локально)

```bash
# 1. Клонируйте
git clone https://github.com/YOUR_USERNAME/bot.git
cd bot

# 2. Настройте .env
cp .env.example .env
nano .env  # Добавьте BOT_TOKEN

# 3. Запустите
docker-compose up -d --build
```

---

## ⚙️ Конфигурация (.env)

```env
# Обязательно
BOT_TOKEN=your_bot_token
ADMIN_IDS=123456789

# Redis
REDIS_URL=redis://localhost:6379/0

# Local Bot API (для файлов > 50MB)
USE_LOCAL_BOT_API=false
TELEGRAM_API_ID=your_id
TELEGRAM_API_HASH=your_hash

# Оптимизация
LOW_MEMORY_MODE=true
MAX_VIDEO_SIZE_MB=45
```

---

## 🛠 Технологии

- **Python 3.11** + **aiogram 3.x**
- **yt-dlp** (загрузка медиа)
- **aiohttp** (health check сервер)
- **SQLAlchemy** + **Redis**
- **FFmpeg** (обработка видео)
- **Local Bot API** (до 2GB файлов)

---

## 📁 Структура проекта

```
bot/
├── src/
│   ├── main.py           # Точка входа + health server
│   ├── config.py         # Конфигурация
│   ├── handlers/         # Обработчики команд
│   ├── services/         # Бизнес-логика
│   └── middlewares/      # Middleware
├── docker-compose.yml    # Docker с Bot API
├── Dockerfile            # Образ бота
├── Dockerfile.bot-api    # Образ Local Bot API
├── koyeb.yaml           # Koyeb конфиг
├── requirements.txt
└── .env.example
```

---

## 🔒 Безопасность

- ✅ Whitelist доменов
- ✅ SSRF Protection
- ✅ Rate Limiting
- ✅ Role Based Access

---

## 📝 License

MIT
