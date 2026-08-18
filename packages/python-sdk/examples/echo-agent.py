import asyncio
import os

from asterisk_ai_gateway import GatewayClient


async def main() -> None:
    client = GatewayClient(
        os.environ["GATEWAY_URL"], os.environ["GATEWAY_API_KEY"], os.environ["AGENT_SLUG"]
    )
    await client.connect()
    try:
        async for message in client.messages():
            if message["type"] == "audio":
                await client.send_audio(str(message["call_id"]), message["audio"])
    finally:
        await client.close()


asyncio.run(main())
