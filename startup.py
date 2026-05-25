import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_api():
    import uvicorn
    config = uvicorn.Config("main:app", host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def run_bot():
    import bot as bot_module
    await bot_module.main()

async def main():
    await asyncio.gather(
        run_api(),
        run_bot(),
    )

if __name__ == "__main__":
    asyncio.run(main())
