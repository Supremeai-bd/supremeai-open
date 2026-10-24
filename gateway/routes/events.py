import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from core.messaging.pubsub import global_pubsub

router = APIRouter(tags=["Events"])


async def _event_generator(request: Request):
    """বাংলা মন্তব্য: dashboard SSE event generator — subscribe করে এবং event stream পাঠায়।

    Yields:
        dict: event type এবং data সহ SSE frame।
    """
    # বাংলা মন্তব্য: তিনটি চ্যানেলে subscribe করা হচ্ছে
    dashboard_queue = await global_pubsub.subscribe("dashboard_events")
    metrics_queue = await global_pubsub.subscribe("metrics_events")
    tasks_queue = await global_pubsub.subscribe("browser_tasks")

    try:
        while True:
            # Wait for an event or a heartbeat timeout (20s)
            # asyncio.wait দিয়ে তিনটি queue race করানো হচ্ছে
            dashboard_task = asyncio.create_task(dashboard_queue.get())
            metrics_task = asyncio.create_task(metrics_queue.get())
            tasks_task = asyncio.create_task(tasks_queue.get())

            done, pending = await asyncio.wait(
                [dashboard_task, metrics_task, tasks_task],
                timeout=20,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not done:
                # Heartbeat — connection জীবিত রাখতে ping পাঠানো হচ্ছে
                yield {"event": "ping", "data": ""}
            else:
                for task in done:
                    result = task.result()
                    # বাংলা মন্তব্য: result-এ 'type' এবং 'payload' থাকবে বলে ধরা হচ্ছে
                    yield {
                        "event": result.get("type", "message"),
                        "data": json.dumps(result.get("payload", {})),
                    }

            # বাংলা মন্তব্য: pending tasks cancel করা হচ্ছে memory leak এড়াতে
            for t in pending:
                t.cancel()

            # If client disconnected, break
            if await request.is_disconnected():
                break
    finally:
        # বাংলা মন্তব্য: cleanup — সব channel থেকে unsubscribe করা হচ্ছে
        await global_pubsub.unsubscribe("dashboard_events", dashboard_queue)
        await global_pubsub.unsubscribe("metrics_events", metrics_queue)
        await global_pubsub.unsubscribe("browser_tasks", tasks_queue)


@router.get("/dashboard/stream")
def dashboard_stream(request: Request):
    """
    SSE endpoint for dashboard metrics and events.
    Yields data when published to 'dashboard_events' channel.
    Maintains connection with a 20s heartbeat.
    """
    return EventSourceResponse(_event_generator(request))


# বাংলা মন্তব্য: টেস্টের backward compatibility এর জন্য event_generator কে
# dashboard_stream function-এর attribute হিসেবে expose করা হচ্ছে।
dashboard_stream.event_generator = _event_generator
