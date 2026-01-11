import redis
import json
from typing import cast
from models import MeetingState,CallState

##===================================================
class StateStore:
    def __init__(self, *args, **kwargs):
        self.rdis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.call_store = "call_state_"
        self.meeting_store = "meeting_state_"
        pass
    ##===================================================
    @staticmethod
    def emptyCallState(call_id):
        return CallState(
                messages=[],
                intent='unknown',
                phone=call_id,
                step=None,
                reply=None,
                name=None,
                text=None
            )
    ##===================================================
    @staticmethod
    def emptyMeetingState(call_id):
        return MeetingState(
                call_id=call_id,
                complete=False,
                user_input=None,
                meeting_type=None,
                date=None,
                time = None,
                email_address=None,
                physical_address=None,
                name=None,
                last_prompt = None,
            )
    ##===================================================
    def loadCallState(self,call_id:str) -> CallState:
        tstate = self.rdis.get(f"{self.call_store}{call_id}")
        if tstate is None or tstate == "":
            return self.emptyCallState(call_id)
        jobj = json.loads(cast(str, tstate))
        cs = CallState(
            messages=jobj.get("messages"),
            intent=jobj.get("intent"),
            step=jobj.get("step",None),
            reply=jobj.get("reply",None),
            phone=jobj.get("phone",None),
            name=jobj.get("name",None),
            text=jobj.get("text",None),
            )
        return cs
    ##===================================================    
    def loadMeetingState(self,call_id:str)->MeetingState:
        tstate = self.rdis.get(f"{self.meeting_store}{call_id}")
        if tstate is None or tstate == "":
            return self.emptyMeetingState(call_id)
        jobj =  json.loads(cast(str, tstate))
        ms = MeetingState(
            call_id=call_id,
            user_input=jobj.get("user_input",None),
            complete=jobj.get("complete",False),
            meeting_type=jobj.get("meeting_type",None),
            date=jobj.get("date",None),
            time = jobj.get("time",None),
            email_address=jobj.get("email_address",None),
            physical_address=jobj.get("physical_address",None),
            name=jobj.get("name",None),
            last_prompt=jobj.get("last_prompt",None),
            )
        return ms
    ##===================================================
    def saveCallState(self,call_id,state):
        jstate = json.dumps(state)
        return self.rdis.set(f"{self.call_store}{call_id}",jstate)
    ##===================================================
    def saveMeetingState(self,call_id,state):
        jstate = json.dumps(state)
        return self.rdis.set(f"{self.meeting_store}{call_id}",jstate)
    ##===================================================
     ##==================================================
    def clearCallState(self,call_id):
        return self.rdis.set(f"{self.call_store}{call_id}","{}")
        
    ##==================================================
    def clearMeetingState(self,call_id):
        return self.rdis.set(f"{self.meeting_store}{call_id}","{}")
    ##===================================================