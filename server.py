"""FastAPI development server entry point."""
import uvicorn

from src.utils import config


if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.API_RELOAD,
        log_level=config.LOG_LEVEL.lower(),
    )
