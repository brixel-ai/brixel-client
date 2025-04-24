import inspect
import asyncio

async def _send_message(broker, msg):
    if hasattr(broker, "send") and inspect.iscoroutinefunction(broker.send):
        await broker.send(msg)
    elif hasattr(broker, "put"):
        await (broker.put if inspect.iscoroutinefunction(broker.put) else lambda x: broker.put(x))(msg)
    elif hasattr(broker, "append"):
        broker.append(msg)
    elif hasattr(broker, "asend"):
        await broker.asend(msg)
    elif callable(broker):
        result = broker(msg)
        if inspect.isawaitable(result):
            await result
    else:
        raise TypeError("Unsupported message_broker type")

def sync_send(broker, msg):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_message(broker, msg))
    except RuntimeError:
        asyncio.run(_send_message(broker, msg))

def safe_enum_value(enum_class, value):
    try:
        return enum_class(value)
    except ValueError:
        return None