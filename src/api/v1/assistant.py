from fastapi import APIRouter, Depends
from pydantic import BaseModel
from src.services.ai import ai_service
from src.middleware.auth import verify_firebase_token

router = APIRouter()

class ChatMessage(BaseModel):
    message: str

@router.post("/chat")
async def chat_helper(data: ChatMessage, token: dict = Depends(verify_firebase_token)):
    reply = await ai_service.generate_chat_response(data.message)
    return {"reply": reply}

