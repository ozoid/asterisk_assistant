from fastapi import FastAPI 
from graph import ChatModel
from models import  ChatRequest, ChatResponse, StoreDeet, StoreResult
from state_store import StateStore, CallState, MeetingState
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import  SystemMessage, AIMessage, BaseMessage, HumanMessage

##===================================================
app = FastAPI()
graph_app = ChatModel()
store = StateStore()
##==================================================
@app.post("/clear_state", response_model=StoreResult)
async def clearState(details:StoreDeet):
    if details.name == "meeting" or details.name == "all":
        store.clearMeetingState(details.call_id)
    if details.name == "call" or details.name == "all":
        store.clearCallState(details.call_id)
    return StoreResult(success=True)
##==================================================
@app.post("/meeting", response_model=ChatResponse)
async def meeting(input: ChatRequest):
    state:MeetingState = store.loadMeetingState(input.call_id) #StateStore.emptyMeetingState(input.call_id) #
    state["user_input"] = input.text #[HumanMessage(content=input.text)] 
    state["call_id"] = input.call_id
    state["complete"] = False
    tconfig: RunnableConfig = {  "configurable": {
        "thread_id": input.call_id,
        #**user_config
    }}
    # result = MeetingState
    result = graph_app.meeting_graph.invoke(state,config=tconfig)
    print(result)
    store.saveMeetingState(input.call_id, result)
    step = ""
    if result.get("complete",True):
        step = "complete"
    cr = ChatResponse(
        reply=result.get("last_prompt","error"),
        intent="meeting",
        step=step,
        text= input.text
    )
    print(cr)
    return cr
##===================================================
@app.post("/chat", response_model=ChatResponse)
async def chat(input: ChatRequest):
    state:CallState = store.loadCallState(input.call_id) # StateStore.emptyCallState(input.call_id)
    state["messages"] += [HumanMessage(content=input.text)] #[HumanMessage(content=input.text)]
    state["step"] = input.step
    state["phone"] = input.call_id
    state["name"] = input.call_name
    state["intent"] = input.intent
    state["reply"] = ""
    tconfig: RunnableConfig = {  "configurable": {
        "thread_id": input.call_id,
        #**user_config
    }}
    result = graph_app.graph.invoke(state,config=tconfig)
    print(result)
    store.saveCallState(input.call_id,result)
    cr = ChatResponse(
        reply=result.get("reply","error"),
        intent=result.get("intent","intent"),
        step=result.get("step",""),
        text= input.text
    )
    print(cr)
    return cr
##===================================================
##===================================================