from fastapi import FastAPI, BackgroundTasks
from langchain_core.messages import HumanMessage
from graph import ChatModel
from models import ChatRequest, ChatResponse
from home_assistant import HomeAssistant
from whatsapp import WhatsApp
import redis
##===================================================
app = FastAPI()
graph_app = ChatModel()
rdis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
##===================================================
@app.post("/warmup")
async def warmup(background_tasks: BackgroundTasks):
    background_tasks.add_task(do_warmup)
    return {"status": "warming"}
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
    chat_hist = ''#rdis.get(f"chat_hist_{req.call_id}")
    print(f"ChatHist:{chat_hist} {req.call_id}")       
    result = graph_app.graph.invoke(
        {
            "messages": [HumanMessage(content=req.text)],
            "intent": None,
            "action": None,
            "step": req.step,
            "chat_history": chat_hist
        },
        config={"thread_id": req.call_id}
    )
    if chat_hist is None:
        chat_hist = ""
    reply = result["messages"][-1].content
    action = result.get("intent")
    response_text = result.get("response_text")
    step = result.get("step")

    print(f"reply:{reply} action:{action} response:{response_text} step:{step}")
    #rdis.set(f"chat_hist_{req.call_id}", f"{chat_hist}\n{req.text}\n{reply}\n" )
    
    
    # if action == "lights":
    #     ha_toggle_light()
    #     action = None
    # if action == "whatsapp":
    #     whatsapp_message(f"{req.text} {reply}")
    #     action = None

    return ChatResponse(
        reply=reply,
        action=action,
        response_text=response_text,
        step=step,
    )
##===================================================
##===================================================