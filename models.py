from pydantic import BaseModel
##===================================================
class ChatRequest(BaseModel):
    unique_id: str
    call_id: str | None = None
    call_name: str | None = None
    text: str
    chat_history: str | None = None
    step: str | None = None
##===================================================
class ChatResponse(BaseModel):
    reply: str
    action: str | None = None
    response_text: str | None = None
    step: str | None = None
##===================================================    
##===================================================