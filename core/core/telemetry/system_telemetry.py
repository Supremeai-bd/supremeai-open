import asyncio

import psutil

from core.logging_config import logger
from core.messaging.event_bus import error_event_bus
from core.swarm_pubsub import swarm_streamer


async def run_system_telemetry_loop(interval_seconds: int = 5) -> None:
    """
    বাংলা মন্তব্য: প্রতি ৫ সেকেন্ড পর পর CPU, Memory এবং Error-rate এর টেলিমেট্রি ডাটা
    সংগ্রহ করে swarm_streamer এর মাধ্যমে ব্রডকাস্ট করে।
    """
    logger.info("Starting System Telemetry Broadcaster...")
    # psutil cpu_percent-কে প্রথমবার কল করে ইনিশিয়ালাইজ করা হচ্ছে
    psutil.cpu_percent()

    last_emitted = error_event_bus.stats["total_emitted"]

    while True:
        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent

            current_emitted = error_event_bus.stats["total_emitted"]
            errors_in_interval = max(0, current_emitted - last_emitted)
            last_emitted = current_emitted

            # গত ইন্টারভালে সংঘটিত এররের সংখ্যাই এরর রেট হিসেবে ধরা হচ্ছে
            error_rate = float(errors_in_interval)

            payload = {
                "cpu": cpu,
                "memory": mem,
                "error_rate": error_rate,
            }
            await swarm_streamer.broadcast("SYSTEM_METRICS", payload)
        except asyncio.CancelledError:
            logger.info("System Telemetry Broadcaster stopped.")
            break
        except Exception as e:
            logger.error(f"Error in System Telemetry Broadcaster loop: {e}")

        await asyncio.sleep(interval_seconds)
