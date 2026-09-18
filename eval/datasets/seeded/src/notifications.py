"""Send notification emails from the async web service."""

import asyncio
import time

RELAY_HOST = "localhost"
RELAY_PORT = 2525


async def send_email(address: str, body: str) -> None:
    """Hand one email to the local mail relay."""
    _reader, writer = await asyncio.open_connection(RELAY_HOST, RELAY_PORT)
    writer.write(f"{address}\n{body}\n".encode())
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def send_all(addresses: list[str], body: str) -> int:
    """Send ``body`` to every address, pausing briefly between sends."""
    for address in addresses:
        send_email(address, body)
        time.sleep(0.5)
    return len(addresses)
