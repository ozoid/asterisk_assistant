from typing import cast
from fastapi import FastAPI #, BackgroundTasks
from graph import ChatModel
from models import CallState, ChatRequest, ChatResponse, MeetingState
import json
from types import SimpleNamespace
import redis
##===================================================
app = FastAPI()
graph_app = ChatModel()
rdis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
##===================================================
def load_state(call_id) -> CallState:
    tstate = rdis.get(f"chat_state_{call_id}")
    if tstate is None or tstate == "":
        return CallState(
            messages=[],
            intent='unknown',
            phone=call_id,
        )
    jobj = json.loads(cast(str, tstate))
    cs = CallState(
        messages=jobj.get("messages"),
        intent=jobj.get("intent"),
        step=jobj.get("step",None),
        reply=jobj.get("reply",None),
        phone=jobj.get("phone",None),
        name=jobj.get("name",None),
        )
    return cs
    
##==================================================
def load_meeting_state(call_id:str)->MeetingState:
    tstate = rdis.get(f"meeting_state_{call_id}")
    if tstate is None or tstate == "":
        return MeetingState(
            call_id=call_id,
            complete=False,
        )
    jobj =  json.loads(cast(str, tstate))
    ms = MeetingState(
        call_id=call_id,
        user_input=jobj.get("user_input",None),
        complete=jobj.get("complete",None),
        meeting_type=jobj.get("meeting_type",None),
        date=jobj.get("date",None),
        time = jobj.get("time",None),
        email_address=jobj.get("email_address",None),
        physical_address=jobj.get("physical_address",None),
        name=jobj.get("name",None),
        last_prompt=jobj.get("last_prompt",None),
        )
    return ms
##==================================================
def save_state(call_id,state):
    jstate = json.dumps(state)
    return rdis.set(f"chat_state_{call_id}",jstate)
##==================================================
def save_meeting_state(call_id,state):
    jstate = json.dumps(state)
    return rdis.set(f"meeting_state_{call_id}",jstate)
##==================================================
@app.post("/meeting", response_model=ChatResponse)
def meeting(input: ChatRequest):
    state = load_meeting_state(input.call_id)
    state["user_input"] = input.text #[HumanMessage(content=input.text)] 
    state["call_id"] = input.call_id
    state["complete"] = False
    new_state = graph_app.meeting_graph.invoke(state,config={"thread_id": input.call_id})
    save_meeting_state(input.call_id, new_state)
    step = 'meeting_ask'
    end_step = new_state.get("complete", False)
    if end_step:
        step="meeting_confirm"
    cr = ChatResponse(
        reply=new_state.get("last_prompt",""),
        action='meeting',
        intent="meeting",
        step=step,
    )
    print(cr)
    return cr
##===================================================
@app.post("/chat", response_model=ChatResponse)
def chat(input: ChatRequest):
    state = load_state(input.call_id)
    state["messages"] += [input.text] #[HumanMessage(content=input.text)]
    state["step"] = input.step
    state["phone"] = input.call_id
    state["name"] = input.call_name
    state["intent"] = input.intent
    result = graph_app.graph.invoke(state,config={"thread_id": input.call_id})
    save_state(input.call_id,state)
    cr = ChatResponse(
        reply=result.get("reply",""),
        intent=result.get("intent","intent"),
        step=result.get("step",""),
    )
    print(cr)
    return cr
##===================================================
##===================================================