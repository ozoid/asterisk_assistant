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
    if tstate is None:
        return {"messages":[],"intent":"unknown"}
    return json.loads(tstate)
##==================================================
def load_meeting_state(call_id):
    tstate = rdis.get(f"meeting_state_{call_id}")
    if tstate is None:
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
@app.post("/meeting", response_model=ChatResponse)
def meeting(input: ChatRequest):
    state = load_state(input.call_id)  # Redis / DB
    state["user_input"] = input.text
    state["call_id"] = input.call_id
    state["complete"] = False
    new_state = graph_app.meeting_graph.invoke(state)
    save_state(input.call_id, new_state)
    return ChatResponse(
        reply=new_state["last_prompt"],
        action=new_state.get("complete", False),
        intent="rmeeting",
        step=None,
    )
##===================================================
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    chat_hist = ''#rdis.get(f"chat_hist_{req.call_id}")
    print(f"ChatHist:{chat_hist} {req.call_id}")       
    result = graph_app.graph.invoke(
        {
            "messages": [HumanMessage(content=req.text)],
            "intent": None,
            "action": None,
            "step": req.step,
            "reply": '',
            "phone": req.call_id,
            "name": req.call_name,
        },
        config={"thread_id": req.call_id}
    )
    if chat_hist is None:
        chat_hist = ""
    reply = result.get("reply") #result["messages"][-1].content
    action = result.get("action")
    intent = result.get("intent")
    step = result.get("step")

    print(f"reply:{reply} action:{action} intent:{intent} step:{step}")
    #rdis.set(f"chat_hist_{req.call_id}", f"{chat_hist}\n{req.text}\n{reply}\n" )
    return ChatResponse(
        reply=reply,
        action=action,
        intent=intent,
        step=step,
    )
##===================================================
##===================================================