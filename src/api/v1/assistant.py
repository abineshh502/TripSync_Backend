from fastapi import APIRouter
from pydantic import BaseModel
from src.services.ai import ai_service

router = APIRouter()

class ChatMessage(BaseModel):
    message: str

@router.post("/chat")
async def chat_helper(data: ChatMessage):
    reply = await ai_service.generate_chat_response(data.message)
    return {"reply": reply}
