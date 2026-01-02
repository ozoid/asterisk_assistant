from typing import TypedDict, List, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, SystemMessage
from dotenv import dotenv_values
##===================================================
config = dotenv_values(".env")

llm = ChatGoogleGenerativeAI(
    model="gemini-3-pro-preview",
    #temperature=1.0,  # Gemini 3.0+ defaults to 1.0
    temperature=0.3,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    api_key=config["GEMINI_API_KEY"]
    # other params...
)
##===================================================
SYSTEM_PROMPT = SystemMessage(content="""
You are a telephone voice assistant.

Rules:
- Keep replies under 2 short sentences
- Ask only one question at a time
- Be polite and concise
- If the caller wants to end the call, say goodbye
""")
##===================================================
Intent = Literal[
    "greeting",
    "question",
    "voicemail",
    "meeting",
    "whatsapp",
    "lights",
    "goodbye",
]
##===================================================

INTENT_PROMPT = """
Classify the caller's intent.

Choose ONE of:
- greeting
- question
- voicemail
- meeting
- whatsapp
- lights
- goodbye

Return ONLY the intent word.
Caller: "{text}"
"""
##===================================================
class CallState(TypedDict):
    messages: List[BaseMessage]
    intent: Intent | None
    action: str | None
##===================================================
def greeting_node(state: CallState):
    return {
        "messages": state["messages"] + [
            SystemMessage(content="Hello! How can I help you today?")
        ],
        "action": None
    }
##===================================================
def question_node(state: CallState):
    response = llm.invoke(state["messages"])
    return {
        "messages": state["messages"] + [response],
        "action": None
    }
##===================================================
def voicemail_node(state: CallState):
    return {
        "messages": state["messages"] + [
            SystemMessage(content="Please leave your message after the tone.")
        ],
        "action": "voicemail"
    }
##===================================================
def goodbye_node(state: CallState):
    return {
        "messages": state["messages"] + [
            SystemMessage(content="Goodbye. Have a nice day.")
        ],
        "action": "hangup"
    }
##===================================================
def lights_node(state: CallState):
    return {
        "messages": state["messages"] + [
            SystemMessage(content="I have toggled the hallway light.")
        ],
        "action": "lights"
    }
##===================================================
def whatsapp_node(state: CallState):
    return {
        "messages": state["messages"] + [
            SystemMessage(content="What is the message you would like to send?")
        ],
        "action": "whatsapp"
    }
##===================================================
def meeting_node(state: CallState):
    return {
        "messages": state["messages"] + [
            SystemMessage(content="When would you like to schedule a meeting?")
        ],
        "action": "meeting"
    }
##===================================================
def intent_node(state: CallState):
    last_msg = state["messages"][-1].content

    intent = intent_llm.invoke(
        INTENT_PROMPT.format(text=last_msg)
    ).content.strip().lower()

    if intent not in Intent:
        intent = "unknown"

    return {
        "intent": intent
    }

##===================================================
def ai_node(state: CallState):
    messages = [SYSTEM_PROMPT] + state["messages"]
    response = llm.invoke(messages)
    return {
        "messages": state["messages"] + [response]
    }
##===================================================
def build_ai_graph():
    graph = StateGraph(CallState)
    graph.add_node("ai", ai_node)
    graph.set_entry_point("ai")
    graph.add_edge("ai", END)

    memory = InMemorySaver()
    return graph.compile(checkpointer=memory)
##===================================================

def build_graph():
    graph = StateGraph(CallState)
    
    graph.add_node("intent", intent_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("question", question_node)
    graph.add_node("voicemail", voicemail_node)
    graph.add_node("meeting", meeting_node)
    graph.add_node("whatsapp", whatsapp_node)
    graph.add_node("lights", lights_node)
    graph.add_node("goodbye", goodbye_node)

    graph.set_entry_point("intent")

    graph.add_conditional_edges(
        "intent",
        lambda s: s["intent"],
        {
            "greeting": "greeting",
            "question": "question",
            "voicemail": "voicemail",
            "meeting": "meeting",
            "whatsapp": "whatsapp",
            "lights": "lights",
            "goodbye": "goodbye",
            "unknown": "question"
        }
    )

    # All paths end
    for node in ["greeting", "question", "voicemail","meeting","whatsapp","lights", "goodbye"]:
        graph.add_edge(node, END)

    memory = InMemorySaver()
    return graph.compile(checkpointer=memory)