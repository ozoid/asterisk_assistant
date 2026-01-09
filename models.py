from typing import  List, Optional, TypedDict
from pydantic import BaseModel
from enum import IntEnum
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
    ERROR       = 10
    GREETING    = 11
    ANYTHING_ELSE = 12
    HANGUP      = 99

    @staticmethod
    def intent(mode):
        intents = {OperationMode.INTENT:"intent",
                   OperationMode.UNKNOWN:"unknown",
                   OperationMode.WA_ASK:"whatsapp",      
                   OperationMode.WA_CONFIRM:"whatsapp",  
                   OperationMode.VOICEMAIL:"voicemail",   
                   OperationMode.MEETING_ASK:"meeting", 
                   OperationMode.MEETING_CONFIRM:"meeting",
                   OperationMode.LIGHTS:"lights",      
                   OperationMode.MOBILE:"mobile",      
                   OperationMode.QUESTION:"question",    
                   OperationMode.ERROR:"error",       
                   OperationMode.HANGUP:"hangup",
                   OperationMode.GREETING:"greeting",
        }
        return intents[mode]
        
##===================================================
class ChatRequest(BaseModel):
    unique_id: str
    call_id: str
    call_name: Optional[str] = None
    text: str
    messages: List[str] = []
    intent: str = "unknown"
    step: Optional[str] = None
##===================================================
class ChatResponse(BaseModel):
    reply: str
    intent: Optional[str] = None
    step: Optional[str] = None
    text: str
##===================================================
class StoreDeet(BaseModel):
    name: str
    call_id: str
##===================================================
##===================================================
class StoreResult(BaseModel):
    success: bool