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
            action=None,
            step=None,
            reply=None,
            phone=call_id,
            name=None,
        )
    jobj = json.loads(cast(str, tstate))
    cs = CallState(
        messages=jobj["messages"],
        intent=jobj["intent"],
        action=jobj["action"],
        step=jobj["step"],
        reply=jobj["reply"],
        phone=jobj["phone"],
        name=jobj["name"],
        )
    return cs
    
##==================================================
def load_meeting_state(call_id:str)->MeetingState:
    tstate = rdis.get(f"meeting_state_{call_id}")
    if tstate is None or tstate == "":
        return MeetingState(
            call_id=call_id,
            user_input=None,
            complete=False,
            meeting_type=None,
            date=None,
            time = None,
            email_address=None,
            physical_address=None,
            name=None,
            last_prompt=None
        )
    jobj =  json.loads(cast(str, tstate))
    ms = MeetingState(
        call_id=call_id,
        user_input=jobj["user_input"],
        complete=jobj["complete"],
        meeting_type=jobj["meeting_type"],
        date=jobj["date"],
        time = jobj["time"],
        email_address=jobj["email_address"],
        physical_address=jobj["physical_address"],
        name=jobj["name"],
        last_prompt=jobj["last_prompt"]
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
    ms = MeetingState(
        call_id=str(input.call_id),
        user_input=input.text,
        complete= False,
        meeting_type=None,
        date=None,
        time = None,
        email_address=None,
        physical_address=None,
        name=None,
        last_prompt=""
        )
    state = load_meeting_state(input.call_id)  # Redis / DB
    if state is not None:
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
    if state is not None:
        state["messages"] = [input.text] #[HumanMessage(content=input.text)]
        state["step"] = input.step
        state["phone"] = input.call_id
        state["name"] = input.call_name
    result = graph_app.graph.invoke(state,config={"thread_id": input.call_id})
    save_state(input.call_id,state)
    cr = ChatResponse(
        reply=result.get("reply",""),
        action=result.get("action","unknown"),
        intent=result.get("intent","intent"),
        step=result.get("step",""),
    )
    print(cr)
    return cr
##===================================================
##===================================================