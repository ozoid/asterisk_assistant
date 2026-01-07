from typing import  List, Optional, TypedDict
from pydantic import BaseModel
from enum import IntEnum
from langchain_core.messages import BaseMessage
##===================================================
Intent = [
            "greeting",
            "question",
            "voicemail",
            "meeting",
            "mobile",
            "whatsapp",
            "lights",
            "goodbye",
        ]

##===================================================
class AIMode(IntEnum):
    UNKNOWN     = 0
    START       = 1
    RECORD      = 2
    PROCESSING  = 3
    WAIT_RESULT = 4
    RUN_ACTIONS = 5
    ANYTHING_ELSE = 6
    END         = 99
##===================================================
class OperationMode(IntEnum):
    UNKNOWN     = 0
    INTENT      = 1
    WA_ASK      = 2
    WA_CONFIRM  = 3
    VOICEMAIL   = 4
    MEETING_ASK = 5
    MEETING_CONFIRM = 6
    LIGHTS      = 7
    MOBILE      = 8
    QUESTION    = 9
    HANGUP      = 99
##===================================================
class ChatRequest(BaseModel):
    unique_id: str
    call_id: str
    call_name: Optional[str]
    text: str
    messages: List[str]
    intent: str
    step: Optional[str] = None
##===================================================
class ChatResponse(BaseModel):
    reply: str
    #action: str | bool | None = None
    intent: Optional[str] = None
    step: Optional[str] = None
##===================================================
# class OperationResult(BaseModel):
#     prompt:str = ''
#     state:OperationMode = OperationMode.UNKNOWN
##===================================================
class MeetingState(TypedDict):
    call_id: str
    name: Optional[str] 
    user_input: Optional[str] 
    meeting_type: Optional[str] 
    date: Optional[str] 
    time: Optional[str] 
    email_address: Optional[str] 
    physical_address:Optional[str] 
    last_prompt: Optional[str]
    complete: bool
##===================================================
class CallState(TypedDict):
    messages:List[str]                 # History of messages
    intent:str                         # the intent/operation mode 
    step: Optional[str]                # what step of the action are we at
    reply: Optional[str]               # the response to say to the caller
    phone:Optional[str]                # the phone number
    name:Optional[str]                 # the callers Name
    ##===================================================