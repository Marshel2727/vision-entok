import uvicorn

from app import create_app
from app.config import settings


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
    )