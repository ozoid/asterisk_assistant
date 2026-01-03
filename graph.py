from typing import TypedDict, List, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, SystemMessage
from dotenv import dotenv_values
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
class CallState(TypedDict):
    messages: List[BaseMessage]
    intent: Intent | None
    action: str | None
    step: str | None
    chat_history: str | None
    response_text: str | None
##===================================================
class ChatModel:
    def __init__(self, *args, **kwargs):
        self.config = dotenv_values(".env")
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3-pro-preview",
            temperature=1.0,  # Gemini 3.0+ defaults to 1.0
            max_tokens=None,
            timeout=None,
            max_retries=2,
            api_key=self.config["GEMINI_API_KEY"]
        )
        
        self.SYSTEM_PROMPT = SystemMessage(content="""
            You are a telephone voice assistant.
            Rules:
            - Keep replies under 2 short sentences
            - Ask only one question at a time
            - Be polite and concise
            - If the caller wants to end the call, say goodbye
        """)

        self.INTENT_PROMPT = """
            Classify the caller's intent.

            Choose ONE of:
            - greeting
            - question
            - voicemail
            - meeting
            - whatsapp
            - lights
            - goodbye
            - unknown

            Return ONLY the intent word.
            Caller: "{text}"
        """
        
        self.do_warmup()
        self.graph = self.build_graph()
    ##===================================================
    def greeting_node(self,state: CallState):
        print("node_greeting")
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [
                SystemMessage(content="Hello! How can I help you today?")
            ],
            "action": None
        }
    ##===================================================
    def question_node(self,state: CallState):
        print("node_question")
        response = self.llm.invoke([self.SYSTEM_PROMPT] + state["messages"])
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [response],
            "action": None
        }
    ##===================================================
    def voicemail_node(self,state: CallState):
        print("node_voicemail")
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [
                SystemMessage(content="Please leave your message after the tone.")
            ],
            "action": "voicemail"
        }
    ##===================================================
    def goodbye_node(self,state: CallState):
        print("node_goodbye")
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [
                SystemMessage(content="Goodbye. Have a nice day.")
            ],
            "action": "hangup"
        }
    ##===================================================
    def lights_node(self,state: CallState):
        print("node_lights")
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [
                SystemMessage(content="I have toggled the hallway light.")
            ],
            "action": "lights"
        }
    ##===================================================
    def whatsapp_node(self,state: CallState):
        print("node_whatsapp")
        return {
            **state,
            "step": "collect_whatsapp_message",
            "response_text": "What is the message you would like to send?",
        }
    ##===================================================
    def whatsapp_confirm_node(self,state: CallState):
        print("node_whatsapp_confirm")

        return {
            **state,
            "step": "confirm_whatsapp_message",
            "response_text": "Your WhatsApp message has been sent."
        }

    ##===================================================
    def meeting_node(self,state: CallState):
        print("node_meeting")
        return {
            **state,
            # "messages": state["messages"] + [
            #     SystemMessage(content="When would you like to schedule a meeting?")
            # ],
            "response_text": "When would you like to schedule a meeting?",
            "action": "meeting"
        }
    ##===================================================
    def route_by_step(self,state):
        step = state.get("step")
        if step == "collect_whatsapp_message":
            return END
        if step == "confirm_whatsapp_message":
            return "whatsapp_confirm"

        return "intent"
    ##===================================================
    def route_by_intent(self,state):
        intent = state.get("intent")

        if intent == "light_on":
            return "light_on_node"
        if intent == "light_off":
            return "light_off_node"
        if intent == "greeting":
            return "greeting_node"

        return "question_node"  # fallback
    ##===================================================
    def intent_node(self,state: CallState):
        print("node_intent")
        last_msg = state["messages"][-1].content

        intent = self.llm.invoke(
            self.INTENT_PROMPT.format(text=last_msg)
        ).content[0]["text"]

        print(f"Intent chosen:{intent}")

        if intent.strip() not in Intent:
            print("intent not in Intent")
            #intent = "unknown"

        return {
            **state,
            "intent": intent
        }
    ##===================================================
    def do_warmup(self):
        # Force-load LLM
        self.llm.invoke("Say OK")
        # Build and cache graph
        # graph = self.build_graph()
        # # Optional: run a dummy pass
        # graph.invoke({
        #     "messages": [],
        #     "intent": None,
        #     "step": None
        # },
        # config={"thread_id": req.call_id}
        # )
        print("Warmup complete")
        #return graph
    ##===================================================    
    def build_graph(self):
        graph = StateGraph(CallState)
        graph.add_node("intent", self.intent_node)
        graph.add_node("greeting", self.greeting_node)
        graph.add_node("question", self.question_node)
        graph.add_node("voicemail", self.voicemail_node)
        graph.add_node("meeting", self.meeting_node)
        graph.add_node("whatsapp_ask", self.whatsapp_node)        # ask for message
        graph.add_node("whatsapp_confirm", self.whatsapp_confirm_node)
        graph.add_node("lights", self.lights_node)
        graph.add_node("goodbye", self.goodbye_node)
        graph.set_entry_point("intent")
        
        graph.add_conditional_edges("whatsapp_ask", self.route_by_step)
        graph.add_conditional_edges("whatsapp_confirm", self.route_by_step)
        
        graph.add_conditional_edges(
            "intent",
            lambda s: s["intent"],
            {
                "greeting": "greeting",
                "question": "question",
                "voicemail": "voicemail",
                "meeting": "meeting",
                "whatsapp": "whatsapp_ask",
                "lights": "lights",
                "goodbye": "goodbye",
                "unknown": END,
            }
        )
        
        # graph.add_conditional_edges(
        #    "intent_node",
        #     route_by_intent,
        #     {
        #         "lights": "lights",
        #         "greeting_node": "greeting_node",
        #         "question_node": "question_node",
        #     }
        # )

        graph.add_edge("greeting", END)
        graph.add_edge("question", END)
        graph.add_edge("voicemail", END)
        graph.add_edge("meeting", END)
        graph.add_edge("lights", END)
        graph.add_edge("goodbye", END)
        
        # # All paths end
        # for node in ["greeting", "question", "voicemail","meeting","whatsapp","lights", "goodbye"]:
        #     graph.add_edge(node, END)
        memory = InMemorySaver()
        return graph.compile(checkpointer=memory)