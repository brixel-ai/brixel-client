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
        # On est dans une boucle déjà active
        loop.create_task(_send_message(broker, msg))  # ça ne bloque pas
    except RuntimeError:
        # Pas de boucle active, on en crée une juste pour cette tâche
        asyncio.run(_send_message(broker, msg))
