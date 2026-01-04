from fastapi import FastAPI #, BackgroundTasks
from langchain_core.messages import HumanMessage
from graph import ChatModel
from models import ChatRequest, ChatResponse

import redis
##===================================================
app = FastAPI()
graph_app = ChatModel()
rdis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
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