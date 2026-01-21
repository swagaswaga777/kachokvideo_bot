import asyncio
import logging
import os
import betterlogging as bl
from aiogram import Bot, Dispatcher
from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp import web
from redis.asyncio import Redis

from src.config import config
from src.handlers import common, media, inline, callbacks, admin, settings, schedule, profile
from src.middlewares.logging import LoggingMiddleware
from src.middlewares.sub_check import SubscriptionMiddleware
from src.middlewares.throttling import ThrottlingMiddleware
from src.middlewares.maintenance import MaintenanceMiddleware
from src.database.main import init_db
from src.database.redis import redis_client
from src.services.http_client import get_http_client
from src.services.task_queue import get_task_queue
from src.services.scheduler import get_scheduler
from src.services.notifications import get_notification_service

def setup_logging():
    bl.basic_colorized_config(level=logging.INFO)


# --- Health Check Web Server for Koyeb ---
async def start_health_server():
    """Start a simple HTTP server for Koyeb health checks."""
    app = web.Application()
    
    async def handle_health(request):
        return web.Response(text="OK", status=200)
    
    async def handle_root(request):
        return web.Response(text="Telegram Downloader Bot is running!", status=200)
    
    app.router.add_get('/', handle_root)
    app.router.add_get('/health', handle_health)
    
    # Koyeb expects port 8000 by default
    port = int(os.getenv('PORT', 8000))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logging.getLogger(__name__).info(f"Health check server started on port {port}")
    return runner


async def run_bot():
    """Main bot logic."""
    # Initialize static-ffmpeg to ensure ffmpeg binaries are available
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        logging.getLogger(__name__).warning("static-ffmpeg not found, relying on system ffmpeg")

    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting bot...")

    # Init DB
    await init_db()
    
    # Initialize performance services
    http_client = get_http_client()
    task_queue = get_task_queue()
    await task_queue.start()
    logger.info(f"Task queue started with {config.DOWNLOAD_WORKERS} workers")

    # Configure Bot with Local Bot API Server if enabled
    if config.USE_LOCAL_BOT_API and config.LOCAL_BOT_API_URL:
        logger.info(f"Using Local Bot API Server: {config.LOCAL_BOT_API_URL}")
        local_server = TelegramAPIServer.from_base(config.LOCAL_BOT_API_URL)
        session = AiohttpSession(api=local_server)
        bot = Bot(token=config.BOT_TOKEN.get_secret_value(), session=session)
        logger.info("Local Bot API enabled - file size limit increased to 2GB")
    else:
        bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    redis_url = config.REDIS_URL
    storage = RedisStorage.from_url(redis_url)
    dp = Dispatcher(storage=storage)
    
    # Initialize scheduler and notifications
    scheduler = get_scheduler()
    notification_service = get_notification_service()
    notification_service.set_bot(bot)
    await scheduler.start()
    await notification_service.start()
    
    # Set scheduler notification callback
    async def on_scheduled_complete(user_id, chat_id, message, result):
        await notification_service.notify_scheduled_ready(user_id, chat_id, message, result)
    
    scheduler.set_callbacks(
        download_callback=None,
        notify_callback=on_scheduled_complete
    )
    logger.info("Scheduler and notification services started")

    # Middlewares
    dp.update.middleware(LoggingMiddleware())
    dp.message.middleware(MaintenanceMiddleware())
    dp.message.middleware(SubscriptionMiddleware())
    dp.message.middleware(ThrottlingMiddleware(redis=redis_client))

    # Routers
    dp.include_router(admin.router)
    dp.include_router(profile.router)
    dp.include_router(settings.router)
    dp.include_router(schedule.router)
    dp.include_router(common.router)
    dp.include_router(callbacks.router)
    dp.include_router(media.router)
    dp.include_router(inline.router)

    # Delete webhook/drop pending updates
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    finally:
        # Cleanup services
        logger.info("Shutting down services...")
        await scheduler.stop()
        await notification_service.stop()
        await task_queue.stop()
        await http_client.close()
        await bot.session.close()
        logger.info("Cleanup complete")


async def main():
    """Run health server and bot concurrently."""
    # Start health check server first
    health_runner = await start_health_server()
    
    try:
        # Run bot
        await run_bot()
    finally:
        # Cleanup health server
        await health_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
