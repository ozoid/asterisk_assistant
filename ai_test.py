#!/usr/bin/env python3
from typing import TypedDict, List
from fastapi import FastAPI
from pydantic import BaseModel
from pathlib import Path
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver

from dotenv import dotenv_values
BASE_DIR = Path(__file__).resolve().parent
config = dotenv_values(BASE_DIR / ".env")

class CallState(TypedDict):
    messages: List[BaseMessage]
    intent: str

def intent_node(state):
    prompt = (
        "Classify intent: greeting, meeting, question, voicemail, goodbye.\n"
        f"User: {state['messages'][-1].content}"
    )
    intent = llm.invoke(prompt).content
    return {"intent": intent}

def ai_node(state: CallState):
    response = llm.invoke(state["messages"])
    return {
        "messages": state["messages"] + [response]
    }


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

graph = StateGraph(CallState)
graph.add_node("ai", ai_node)
graph.set_entry_point("ai")
graph.add_edge("ai", END)

# graph.add_conditional_edges(
#     "intent",
#     lambda s: s["intent"],
#     {
#         "goodbye": END,
#         "question": "ai",
#         "voicemail": "ai"
#     }
# )

memory = InMemorySaver()
app = graph.compile(checkpointer=memory)

call_id = "+4400000000"
caller_text = "How can I schedule a meeting with Steve?"
result = app.invoke(
    {
        "messages": [
            SystemMessage(content="You are a polite phone assistant."),
            HumanMessage(content=caller_text)
        ]
    },
    config={"thread_id": call_id}
)

reply = result["messages"][-1].content



print(reply[0]["text"])