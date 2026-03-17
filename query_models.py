import asyncio
import os
from opencode_ai import AsyncOpencode

async def main():
    api_url = os.environ.get("OPENCODE_API_URL", "http://127.0.0.1:4096")
    client = AsyncOpencode(base_url=api_url)
    try:
        res = await client.app.providers()
        for p in res.providers:
            print(f"Provider: {p.id}")
            for m in p.models.keys():
                print(f"  - {m}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
