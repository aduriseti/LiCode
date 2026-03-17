import asyncio
from opencode_ai import AsyncOpencode

async def test():
    client = AsyncOpencode(base_url="http://127.0.0.1:4096")
    try:
        # Check standard endpoints typical for such SDKs
        if hasattr(client, 'app') and hasattr(client.app, 'providers'):
            res = await client.app.providers()
            print("FOUND PROVIDERS VIA APP:", res)
        else:
            print("Client attrs:", [a for a in dir(client) if not a.startswith('_')])
            print("App attrs:", [a for a in dir(client.app) if not a.startswith('_')])
    except Exception as e:
        print("ERROR:", e)

asyncio.run(test())
