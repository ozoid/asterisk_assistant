from fastapi import FastAPI #, BackgroundTasks
from langchain_core.messages import HumanMessage
from graph import ChatModel
from models import ChatRequest, ChatResponse,CallInput
import json
import redis
##===================================================
app = FastAPI()
graph_app = ChatModel()
rdis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
##===================================================
def load_state(call_id):
    tstate = rdis.get(f"chat_state_{call_id}")
    if tstate is None or tstate == "":
        return {"messages":[],"intent":"unknown"}
    return json.loads(tstate)
##==================================================
def load_meeting_state(call_id):
    tstate = rdis.get(f"meeting_state_{call_id}")
    if tstate is None or tstate == "":
        return {"call_id":"0","complete":False}
    return json.loads(tstate)
##==================================================
def save_state(call_id,state):
    jstate = json.dumps(state)
    return rdis.set(f"chat_state_{call_id}",jstate)
##==================================================
def save_meeting_state(call_id,state):
    jstate = json.dumps(state)
    return rdis.set(f"meeting_state_{call_id}",jstate)
##==================================================
def clear_state(call_id):
    return rdis.set(f"chat_state_{call_id}","")
##==================================================
def clear_meeting_state(call_id):
    return rdis.set(f"meeting_state_{call_id}","")
##==================================================
@app.post("/meeting", response_model=ChatResponse)
def meeting(input: ChatRequest):
    state = load_meeting_state(input.call_id)  # Redis / DB
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
        reply=new_state.get("last_prompt"),
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
    state["messages"] = [input.text] #[HumanMessage(content=input.text)]
    state["step"] = input.step
    state["phone"] = input.call_id
    state["name"] = input.call_name
    result = graph_app.graph.invoke(state,config={"thread_id": input.call_id})
    save_state(input.call_id,state)
    cr = ChatResponse(
        reply=result.get("reply"),
        action=result.get("action"),
        intent=result.get("intent"),
        step=result.get("step"),
    )
    print(cr)
    return cr
##===================================================
##===================================================