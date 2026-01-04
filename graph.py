from typing import TypedDict, List, Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage,HumanMessage
from dotenv import dotenv_values
##===================================================
Intent = [
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
    messages: List[BaseMessage]     # History of messages
    intent:str                      # the intent discovered initially
    action: str | None              # the action to do when returned
    step: str | None                # what step of the action are we at
    reply: str | None               # the response to say to the caller
    phone:str | None                # the phone number
    name:str | None                 # the callers Name
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
            - Keep replies under 2 short sentences.
            - Ask only one question at a time.
            - Be polite and concise and stay positive.
            - If the caller wants to end the call, say goodbye.
        """)
        self.MEETING_PROMPT = """
            This part of the conversation requires you to take details for a meeting.
            The meeting can be an online Zoom or Microsoft Teams meeting or and in person meeting and requires the following information from the caller:
            - the date and time of the meeting.
            - if the meeting is online the callers email address.
            - if the caller wants to be called back at the specified date and time, please ensure the phone number "{phone}" is correct with the caller.
            - if the meeting is in person, a physical UK address including postcode.
        """

        self.MEETING_CONFIRM_PROMPT = """
            This part of the conversation requires you to confirm the details for a meeting.
            Please ensure you have the date and time, the email address if online or the physical address if the meeting is in person or the phone number "{phone}" is correct.
        """
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
    ##===================================================
    def do_warmup(self):
        self.llm.invoke("Say OK")
        self.graph = self.build_graph()
        self.graph.invoke({
             "messages": [],
             "intent": None,
             "step": None
         },
         config={"thread_id": "00"}
        )
        print("Warmup complete")
    ##===================================================
    def cleanResponse(self,response:AIMessage):
        if response.content is None:
            return ''
        if len(response.content) == 0:
            return ''
        if response.content[0]['text'] is not None:
            return response.content[0]['text']
        return ''
    ##===================================================
    def greeting_node(self,state: CallState):
        print("node_greeting")
        reply = "Hello! How can I help you today?"
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply":reply,
            "action": None
        }
    ##===================================================
    def question_node(self,state: CallState):
        print("node_question")
        response:AIMessage = self.llm.invoke([self.SYSTEM_PROMPT] + state["messages"])
        reply = self.cleanResponse(response)
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply": reply,
            "action": None
        }
    ##===================================================
    def unknown_node(self,state: CallState):
        print("node_unknown")
        response:AIMessage = self.llm.invoke([self.SYSTEM_PROMPT] + state["messages"])
        reply = self.cleanResponse(response)
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply": reply,
            "action": None
        }
    ##===================================================
    def voicemail_node(self,state: CallState):
        print("node_voicemail")
        reply = "Please leave your message after the tone."
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply": reply,
            "action": "voicemail"
        }
    ##===================================================
    def goodbye_node(self,state: CallState):
        print("node_goodbye")
        reply = "Goodbye. Have a nice day."
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply": reply,
            "action": "hangup"
        }
    ##===================================================
    def lights_node(self,state: CallState):
        print("node_lights")
        reply = "I have toggled the hallway light."
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply": reply,
            "action": "lights"
        }
    ##===================================================
    def whatsapp_node(self,state: CallState):
        print("node_whatsapp")
        reply = "What is the WhatsApp message you would like to send?"
        return {
            **state,
            "action": "whatsapp",
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "step": "collect_whatsapp_message",
            "reply": reply,
        }
    ##===================================================
    def whatsapp_confirm_node(self,state: CallState):
        print("node_whatsapp_confirm")
        reply = "Your WhatsApp message has been sent."
        return {
            **state,
            "action": "whatsapp",
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "step": "confirm_whatsapp_message",
            "reply": reply
        }
    ##===================================================
    def meeting_node(self,state: CallState):
        print("node_meeting")
        response:AIMessage = self.llm.invoke([SystemMessage(content=self.SYSTEM_PROMPT)] + [SystemMessage(content=self.MEETING_PROMPT.format(phone=state.phone))] + state["messages"])
        reply = self.cleanResponse(response)
        return {
            **state,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply": reply,
            "action": "meeting",
            "step": "meeting_ask"
        }
    ##===================================================
    def meeting_confirm_node(self,state: CallState):
        print("node_meeting")
        response:AIMessage = self.llm.invoke([SystemMessage(content=self.SYSTEM_PROMPT)] + [SystemMessage(content=self.MEETING_CONFIRM_PROMPT.format(phone=state.phone))] + state["messages"])
        reply = self.cleanResponse(response)
        return {
            **state,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply": reply,
            "action": "meeting",
            "step": "meeting_confirm"
        }
    ##===================================================
    def route_by_step(self,state):
        step = state.get("step")
        if step == "collect_whatsapp_message":
            return "whatsapp_ask"
        if step == "confirm_whatsapp_message":
            return "whatsapp_confirm"
        if step == "meeting_ask":
            return "meeting_ask"
        if step == "meeting_confirm":
            return "meeting_confirm"
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
        last_msg = ""
        if len(state["messages"]) >0:
            last_msg = state["messages"][-1].content
        else:
            return {
                **state,
                "intent": "unknown"
            }    
        namestr = ""
        if state["name"] is not None and state["name"] != "":
            namestr = f"\nThe callers name is {state['name']}"
        intent:AIMessage = self.llm.invoke(self.INTENT_PROMPT.format(text=last_msg+namestr))
        reply = self.cleanResponse(intent)
        print(f"Intent chosen:{reply}")
        if reply not in Intent:
            print(f"intent {reply} not in Intents")
            #intent = "unknown"

        return {
            **state,
            "intent": reply
        }
    ##===================================================    
    def build_graph(self):
        graph = StateGraph(CallState)
        graph.add_node("intent", self.intent_node)
        graph.add_node("greeting", self.greeting_node)
        graph.add_node("question", self.question_node)
        graph.add_node("unknown", self.unknown_node)
        graph.add_node("voicemail", self.voicemail_node)
        graph.add_node("meeting_ask", self.meeting_node)
        graph.add_node("meeting_confirm",self.meeting_confirm_node)
        graph.add_node("whatsapp_ask", self.whatsapp_node)        # ask for message
        graph.add_node("whatsapp_confirm", self.whatsapp_confirm_node)
        graph.add_node("lights", self.lights_node)
        graph.add_node("goodbye", self.goodbye_node)
        graph.set_entry_point("intent")
        
        graph.add_conditional_edges("whatsapp_ask", self.route_by_step)
        graph.add_conditional_edges("whatsapp_confirm", self.route_by_step)
        graph.add_conditional_edges("meeting_ask", self.route_by_step)
        graph.add_conditional_edges("meeting_confirm", self.route_by_step)
        
        graph.add_conditional_edges(
            "intent",
            lambda s: s["intent"],
            {
                "greeting": "greeting",
                "question": "question",
                "voicemail": END,
                "meeting": "meeting_ask",
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
        graph.add_edge("meeting_confirm", END)
        graph.add_edge("whatsapp_confirm", END)
        graph.add_edge("lights", END)
        graph.add_edge("goodbye", END)
        
        # # All paths end
        # for node in ["greeting", "question", "voicemail","meeting","whatsapp","lights", "goodbye"]:
        #     graph.add_edge(node, END)
        memory = InMemorySaver()
        return graph.compile(checkpointer=memory)