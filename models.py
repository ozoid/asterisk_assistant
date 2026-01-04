from pydantic import BaseModel
from enum import IntEnum
##===================================================
class AIState(IntEnum):
    UNKNOWN     = 0
    START       = 1
    RECORD      = 2
    PROCESSING  = 3
    WAIT_RESULT = 4
    RUN_ACTIONS = 5
    ANYTHING_ELSE = 6
    END         = 99
##===================================================
class ResultCode(IntEnum):
    UNKNOWN     = 0
    WA_ASK      = 1
    WA_CONFIRM  = 2
    VOICEMAIL   = 3
    MEETING_ASK = 4
    MEETING_CONFIRM = 5
    LIGHTS      = 6
    HANGUP      = 99
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
# ##===================================================
class ActionResult(BaseModel):
    prompt:str
    result:ResultCode #= ResultCode.UNKNOWN
##===================================================