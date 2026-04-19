import uvicorn
import asyncio


async def main() -> None:
    uvicorn.run('src.application:get_app', host='localhost', port=8001, reload=True, factory=True)

if __name__ == '__main__':
    asyncio.run(main())
