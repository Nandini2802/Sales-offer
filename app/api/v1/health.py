
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.startup_checks import run_startup_checks
from app.core.dependencies import get_db


router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    return {
        "status": "healthy"
    }


@router.get("/ready")
async def ready(request: Request):

    clients = request.app.state.clients

    dependency_status = await run_startup_checks(clients)

    is_ready = all(
        status == "healthy"
        for status in dependency_status.values()
    )

    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={
            "status": "ready" if is_ready else "not_ready",
            "dependencies": dependency_status,
        },
    )


@router.get("/test-db", include_in_schema=False)
async def test_db(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text("SELECT 1"))

    return {
        "status": "connected",
        "database": "postgresql",
        "test_result": result.scalar_one(),
    }
