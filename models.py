from typing import TypedDict, List, Literal,Optional
from pydantic import BaseModel
from enum import IntEnum
from langchain_core.messages import BaseMessage
##===================================================
Intent = [
            "greeting",
            "question",
            "voicemail",
            "meeting",
            "whatsapp",
            "lights",
            "goodbye",
        ]

##===================================================
class CallState(TypedDict):
    messages: List = []     # History of messages
    intent:str                      # the intent discovered initially
    action: str | None              # the action to do when returned
    step: str | None                # what step of the action are we at
    reply: str | None               # the response to say to the caller
    phone:str | None                # the phone number
    name:str | None                 # the callers Name
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
class OperationState(IntEnum):
    UNKNOWN     = 0
    INTENT      = 1
    WA_ASK      = 2
    WA_CONFIRM  = 3
    VOICEMAIL   = 4
    MEETING_ASK = 5
    MEETING_CONFIRM = 6
    LIGHTS      = 7
    HANGUP      = 99
##===================================================
class MeetingState(TypedDict):
    call_id: str
    user_input: Optional[str]
    meeting_type: Optional[str]
    date: Optional[str]
    time: Optional[str]
    email_address: Optional[str]
    physical_address: Optional[str]
    last_prompt: Optional[str]
    complete: bool
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
    action: str | bool | None = None
    intent: str | None = None
    step: str | None = None
##===================================================  
class CallInput(BaseModel):
    call_id: str
    user_input: str | None = None

# ##===================================================
class OperationResult(BaseModel):
    prompt:str = ''
    state:OperationState = OperationState.UNKNOWN
##===================================================