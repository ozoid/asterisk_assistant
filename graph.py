from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import  SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from dotenv import dotenv_values
from models import CallState, MeetingState, Intent
import json

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
            This part of the conversation requires you to extract details for a meeting from the callers responses.
            The meeting type can be a phone call, a Zoom/Teams online meeting or a physical in-person meeting.
            If the meeting is online you do not need the physical address,
              if the meeting is a physical in-person you do not need the email address,
              if the meeting is a phone call, we already have the number from the telephone system.
            Return a clean JSON serialized object with any of:
            [meeting_type, date, time, email_address, physical_address]

            meeting_type can be one of: [zoom, teams, physical, phonecall]
            Only include fields you are confident about."""
        self.MEETINGWRAP = ChatPromptTemplate.from_messages([
            ("system", self.MEETING_PROMPT),
            ("human", "{input}")
            ])

        self.MEETING_CONFIRM_PROMPT = """
            Please now ensure you have all of the relevant meeting information so we can confirm the meeting details with the caller.
        """
        #self.MEETING_PROMPT.extend([("system",self.MEETING_CONFIRM_PROMPT)])

        
        
        self.INTENT_PROMPT = """
            Classify the caller's intent.

            Choose ONE of:
            - greeting
            - question
            - voicemail
            - meeting
            - mobile
            - whatsapp
            - lights
            - goodbye
            - unknown

            Return ONLY the intent word.
            Caller: "{text}"
        """

        self.extract_chain = self.MEETINGWRAP | self.llm
        
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
        self.meeting_graph = self.build_meeting_graph()
        self.meeting_graph.invoke({

        })
        print("Warmup complete")
    ##===================================================
    def cleanResponse(self,response:AIMessage) ->str|None:
        if response.content is None:
            return None
        if len(response.content) == 0:
            return None
        if response.content[0]['text'] is not None:
            return response.content[0]['text'].replace("```json","").replace("```","")
        return None
    ##===================================================
    def extract_info(self,state: MeetingState) -> MeetingState:
        print("node_extract_info")
        if not state.get("user_input"):
            return state

        response = self.extract_chain.invoke({
            "input": state["user_input"]
        })
        cleaned = self.cleanResponse(response)
        print(cleaned)
        if cleaned is None:
            print("Exception=No Data")
            return state
        try:
            data = json.loads(self.cleanResponse(response))
        except Exception:
            print("Exception=Extract_Info")
            return state

        for key in ["meeting_type", "date", "time", "email_address", "physical_address"]:
            if key in data and not state.get(key):
                state[key] = data[key]
        print(f"Extract State:{state}")
        return state
    ##===================================================
    def decide_next_step(self,state: MeetingState) -> str:
        if not state.get("meeting_type"):
            return "ask_type"
        if not state.get("date"):
            return "ask_date"
        if not state.get("time"):
            return "ask_time"
        if not state.get("physical_address") and state.get("meeting_type") == "physical":
            return "ask_physical"
        if not state.get("email_address") and state.get("meeting_type") != "physical" and state.get("meeting_type") != "phonecall":
            return "ask_email"
        return "confirm"
    ##===================================================
    def ask_type(self,state: MeetingState) -> MeetingState:
        print("node_ask_type")
        state["last_prompt"] = "What type of meeting do you want, an online Zoom, Teams meeting or an in-person meeting?"
        return state
    ##===================================================
    def ask_purpose(self,state: MeetingState) -> MeetingState:
        print("node_ask_purpose")
        state["last_prompt"] = "What is the purpose of the meeting?"
        return state
    ##===================================================
    def ask_date(self,state: MeetingState) -> MeetingState:
        print("node_ask_date")
        state["last_prompt"] = "What date should the meeting take place?"
        return state
    ##===================================================
    def ask_time(self,state: MeetingState) -> MeetingState:
        print("node_ask_time")
        state["last_prompt"] = "What time should the meeting start?"
        return state
    ##===================================================
    def ask_email(self,state: MeetingState) -> MeetingState:
        print("node_ask_email")
        state["last_prompt"] = "What is your email address?"
        return state
    ##===================================================
    def ask_physical(self,state: MeetingState) -> MeetingState:
        print("node_ask_physical")
        state["last_prompt"] = "What is the address you wish Steve to attend?"
        return state
    ##===================================================
    def confirm_meeting(self,state: MeetingState) -> MeetingState:
        print("node_confirm_meeting")
        added = ''
        if state.get("physical_address"):
            added = f"in location {state['physical_address']}"
        summary = (
            f"I will schedule a meeting of type {state['meeting_type']} "
            f"on {state['date']} at {state['time']} {added}"
            "Is this correct?"
        )
        state["last_prompt"] = summary
        state["complete"] = True
        return state
    ##===================================================
    def build_meeting_graph(self):
        graph = StateGraph(MeetingState)

        graph.add_node("extract", self.extract_info)

        graph.add_node("ask_type", self.ask_type)
        #graph.add_node("ask_purpose", self.ask_purpose)
        graph.add_node("ask_date", self.ask_date)
        graph.add_node("ask_time", self.ask_time)
        graph.add_node("ask_email", self.ask_email)
        graph.add_node("ask_physical", self.ask_physical)
        graph.add_node("confirm", self.confirm_meeting)

        graph.set_entry_point("extract")

        graph.add_conditional_edges(
            "extract",
            self.decide_next_step,
            {
                "ask_type": "ask_type",
                "ask_date": "ask_date",
                "ask_time": "ask_time",
                #"ask_purpose":"ask_purpose",
                "ask_email": "ask_email",
                "ask_physical": "ask_physical",
                "confirm": "confirm"
            }
        )

        return graph.compile()
    ##===================================================
    ##===================================================
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
        reply = "Forwarding to Voicemail."
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply": reply,
            "action": "voicemail"
        }
    ##===================================================
    def mobile_node(self,state: CallState):
        print("node_mobile")
        reply = "Forwarding to Mobile Phone."
        return {
            **state,
            "step": None,
            "messages": state["messages"] + [SystemMessage(content=reply)],
            "reply": reply,
            "action": "mobile"
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
        #response:AIMessage = self.llm.invoke([self.SYSTEM_PROMPT] + [self.MEETING_PROMPT] + state["messages"])
        #reply = self.cleanResponse(response)
        reply = "When would you like the meeting to take place?"
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
        response:AIMessage = self.llm.invoke([self.SYSTEM_PROMPT] + [SystemMessage(content=self.MEETING_CONFIRM_PROMPT.format(phone=state.phone))] + state["messages"])
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
            return END
        if step == "confirm_whatsapp_message":
            return "whatsapp_confirm"

        return "intent"
    ##===================================================
    ##===================================================
    def intent_node(self,state: CallState):
        print("node_intent")
        print(state)
        last_msg = ""
        if len(state["messages"]) >0:
            last_msg = state["messages"][-1]
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
        graph.add_node("mobile", self.mobile_node)
        graph.add_node("meeting_ask", self.meeting_node)
        graph.add_node("meeting_confirm",self.meeting_confirm_node)
        graph.add_node("whatsapp_ask", self.whatsapp_node)        # ask for message
        graph.add_node("whatsapp_confirm", self.whatsapp_confirm_node)
        graph.add_node("lights", self.lights_node)
        graph.add_node("goodbye", self.goodbye_node)
        graph.set_entry_point("intent")
        
        graph.add_conditional_edges("whatsapp_ask", self.route_by_step)
        graph.add_conditional_edges("whatsapp_confirm", self.route_by_step)
        #graph.add_conditional_edges("meeting_ask", self.route_by_step)
        #graph.add_conditional_edges("meeting_confirm", self.route_by_step)
        
        graph.add_conditional_edges(
            "intent",
            lambda s: s["intent"],
            {
                "greeting": "greeting",
                "question": "question",
                "voicemail": END,
                "mobile": END,
                "meeting": "meeting_ask",
                "whatsapp": "whatsapp_ask",
                "lights": "lights",
                "goodbye": "goodbye",
                "unknown": END,
            }
        )
        
        graph.add_edge("greeting", END)
        graph.add_edge("question", END)
        graph.add_edge("voicemail", END)
        graph.add_edge("mobile", END)
        graph.add_edge("meeting_ask",END)
        graph.add_edge("meeting_confirm", END)
        graph.add_edge("whatsapp_ask", END)
        graph.add_edge("whatsapp_confirm", END)
        graph.add_edge("lights", END)
        graph.add_edge("goodbye", END)
        
        memory = InMemorySaver()
        return graph.compile(checkpointer=memory)