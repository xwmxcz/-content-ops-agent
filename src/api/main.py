"""FastAPI app for the modern Content Ops Agent backend."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import agent, auth, calendar, content, health, jobs, media, memory, models, publish, stats
from src.api.security import AuthMiddleware
from src.utils import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the DB schema once at startup. Per-task ContentStore instances in the
    # job runner and pipeline worker then run with initialize_schema=False, so the
    # create_all / ALTER DDL no longer executes on every job.
    from src.api.dependencies import get_store

    get_store()
    yield


app = FastAPI(
    title="Content Ops Agent API",
    version="0.1.0",
    description="REST API for content generation, refinement, scheduling, and analytics.",
    lifespan=lifespan,
)

app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(models.router, prefix="/api/models", tags=["models"])
app.include_router(content.router, prefix="/api/content", tags=["content"])
app.include_router(media.router, prefix="/api", tags=["media"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["calendar"])
app.include_router(publish.router, prefix="/api/publish", tags=["publish"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
