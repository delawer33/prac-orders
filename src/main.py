import uvicorn
import asyncio

from src.config import Settings

settings = Settings()


async def main() -> None:
    uvicorn.run(
        'src.application:get_app',
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
        factory=True,
    )

if __name__ == '__main__':
    asyncio.run(main())
