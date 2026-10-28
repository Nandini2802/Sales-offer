
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter(
    prefix="/dev",
    tags=["Development"],
)

HTML_PATH = Path(__file__).resolve().parent / "chat_test.html"


@router.get("/chat-test", include_in_schema=False)
async def chat_test():
    return FileResponse(
        HTML_PATH,
        media_type="text/html",
    )
