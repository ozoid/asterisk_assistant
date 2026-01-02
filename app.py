from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from graph import build_graph
from models import ChatRequest, ChatResponse
from home_assistant import HomeAssistant
from whatsapp import WhatsApp
import redis
##===================================================
app = FastAPI()
graph_app = build_graph()
rdis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
##===================================================
def ha_toggle_light():
    ha = HomeAssistant()
    ha.toggle_hallway_light("on")
##===================================================
def whatsapp_message(message):
    wa = WhatsApp()
    wa.post_whatsApp(message)
##===================================================
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    chat_hist = rdis.get(f"chat_hist_{req.call_id}")
           
    result = graph_app.invoke(
        {
            "messages": [HumanMessage(content=req.text)],
            "intent": None,
            "action": None,
            "chat_history": chat_hist
        },
        config={"thread_id": req.call_id}
    )
    if chat_hist is None:
        chat_hist = ""
    print(req.text)
    reply = result["messages"][-1].content
    print(reply)
    rdis.set(f"chat_hist_{req.call_id}", f"{chat_hist} {req.text} {reply}" )
    action = result.get("action")
    print(action)
    if action == "lights":
        ha_toggle_light()
        action = None
    if action == "whatsapp":
        whatsapp_message(f"{req.text} {reply}")
        action = None

    return ChatResponse(
        reply=reply,
        action=action
    )
##===================================================
##===================================================