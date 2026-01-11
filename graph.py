from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import  SystemMessage, AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from dotenv import dotenv_values
from models import Intent,CallState,MeetingState
from pathlib import Path
from state_store import StateStore
import json

##===================================================
class ChatModel:
    def __init__(self, *args, **kwargs):
        BASE_DIR = Path(__file__).resolve().parent
        self.config = dotenv_values(BASE_DIR / ".env")
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
            [meeting_type, name, date, time, email_address, physical_address]

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
            - hangup
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
        self.tconfig: RunnableConfig = {  "configurable": {
            "thread_id": "thread-00",
            #**user_config
        }}
        self.graph.invoke(StateStore.emptyCallState("00"),config=self.tconfig)
        self.meeting_graph = self.build_meeting_graph()
        self.meeting_graph.invoke(StateStore.emptyMeetingState("00"),config=self.tconfig)
        print("Warmup complete")
    ##===================================================
    def cleanResponse(self, response: AIMessage) -> str | None:
        content = response.content
        if not content:
            return None
        if isinstance(content, str):
            return content
        first = content[0]
        if isinstance(first, dict) and "text" in first:
            text = first["text"]
            if isinstance(text, str) and "json" in text:
                return text.replace("```json", "").replace("```", "")
            else:
                return text
        print(f"Exception=No Data")
        return None
    ##===================================================
    def extract_info(self,state: MeetingState) -> MeetingState:
        print("node_extract_info")
        if not state.get("user_input"):
            return state

        response = self.extract_chain.invoke({
            "input": state["user_input"]
        },
        {"configurable": {"thread_id": state["call_id"]}})
        cleaned = self.cleanResponse(response)
        print(cleaned)
        if cleaned is None:
            print("Extract Exception=No Data")
            return state
        try:
            data = json.loads(cleaned)
        except Exception:
            print("Extract Exception=Extract_Info")
            return state

        for key in ["meeting_type","name", "date", "time", "email_address", "physical_address"]:
            if key in data and not state.get(key):
                state[key] = data[key]
        print(f"Extract State:{state}")
        return state
    ##===================================================
    def decide_next_step(self,state: MeetingState) -> str:
        if not state.get("meeting_type"):
            return "ask_type"
        if not state.get("name"):
            return "ask_name"
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
    def ask_name(self,state: MeetingState) -> MeetingState:
        print("node_ask_name")
        state["last_prompt"] = "Can I take your name please?"
        return state
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
        graph.add_node("ask_name", self.ask_name)
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
                "ask_name":"ask_name",
                "ask_email": "ask_email",
                "ask_physical": "ask_physical",
                "confirm": "confirm"
            }
        )
        memory = InMemorySaver()
        return graph.compile(checkpointer=memory)
    ##===================================================
    def greeting_node(self,state: CallState) -> CallState:
        print("node_greeting")
        reply = "Hello! How can I help you today?"
        state["reply"] = reply
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def question_node(self,state: CallState) -> CallState:
        print("node_question")
        response:AIMessage = self.llm.invoke([self.SYSTEM_PROMPT] + state["messages"])
        reply = self.cleanResponse(response)
        state["reply"] = reply
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def unknown_node(self,state: CallState) -> CallState:
        print("node_unknown")
        response:AIMessage = self.llm.invoke([self.SYSTEM_PROMPT] + state["messages"])
        print(response)
        reply = self.cleanResponse(response)
        state["reply"] = reply
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def voicemail_node(self,state: CallState) -> CallState:
        print("node_voicemail")
        reply = "Forwarding to Voicemail."
        state["reply"] = reply
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def mobile_node(self,state: CallState) -> CallState:
        print("node_mobile")
        reply = "Forwarding to Mobile Phone."
        state["reply"] = reply
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def goodbye_node(self,state: CallState) -> CallState:
        print("node_goodbye")
        reply = "Goodbye. Have a nice day."
        state["reply"] = reply
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def lights_node(self,state: CallState) -> CallState:
        print("node_lights")
        reply = "I have toggled the hallway light."
        state["reply"] = reply
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def whatsapp_node(self,state: CallState) -> CallState:
        step = state.get("step","")
        print(f"node_whatsapp {step}")
        if step == "collect_whatsapp_message" or step == "":
            reply = "What is the WhatsApp message you would like to send?"
            step = "collect_whatsapp_message"
        elif step == "confirm_whatsapp_message":
            reply = "Your WhatsApp message has been sent."
            step = "confirm_whatsapp_message"
        state["reply"] = reply
        state["step"] = step
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def meeting_node(self,state: CallState) -> CallState:
        print("node_meeting")
        #response:AIMessage = self.llm.invoke([self.SYSTEM_PROMPT] + [self.MEETING_PROMPT] + state["messages"])
        #reply = self.cleanResponse(response)
        reply = "When would you like the meeting to take place?"
        state["reply"] = reply
        state["step"] = "meeting_ask"
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def meeting_confirm_node(self,state: CallState) -> CallState:
        print("node_meeting")
        response:AIMessage = self.llm.invoke([self.SYSTEM_PROMPT] + [SystemMessage(content=self.MEETING_CONFIRM_PROMPT.format(phone=state["phone"]))] + state["messages"])
        reply = self.cleanResponse(response)
        state["reply"] = reply
        state["step"] = "meeting_confirm"
        state["messages"] += [SystemMessage(content=reply)]
        return state
    ##===================================================
    def intent_node(self,state: CallState) -> CallState:
        print("node_intent")
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
        response = self.cleanResponse(intent)
        print(f"Intent chosen:{response}")
        if response not in Intent:
            print(f"intent {response} not in Intents")
        state["reply"] = response
        state["step"] = None        
        return state
    ##===================================================   
    def call_router(self,state: CallState) -> CallState:
        step = state.get("step")
        intent = state.get("intent")
       
        if intent == "whatsapp":
            if step == "complete_whatsapp_message":
                intent= "goodbye"
        state["intent"] = intent
        state["step"] = None        
        return state
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
        graph.add_node("whatsapp", self.whatsapp_node)        # ask for message
        graph.add_node("lights", self.lights_node)
        graph.add_node("goodbye", self.goodbye_node)
        graph.add_node("hangup", self.goodbye_node)
        graph.add_node("router", self.call_router)
        graph.set_entry_point("router")
        
        graph.add_conditional_edges(
            "router",
            lambda s: s["intent"],{
                "intent": "intent",
                "whatsapp": "whatsapp",
                "greeting": "greeting",
                "question": "question",
                "voicemail": "voicemail",
                "mobile": "mobile",
                "meeting": "meeting_ask",
                "lights": "lights",
                "goodbye": "goodbye",
                "hangup": "goodbye",
                "unknown": END,
                END: END,
            },
        )

        graph.add_conditional_edges(
            "intent",
            lambda s: s["intent"],
            {
                "greeting": "greeting",
                "question": "question",
                "voicemail": "voicemail",
                "mobile": "voicemail",
                "meeting": "meeting_ask",
                "whatsapp": "whatsapp",
                "lights": "lights",
                "goodbye": "goodbye",
                "hangup": "goodbye",
                "unknown": END,
            }
        )
        graph.add_edge("router", END)
        graph.add_edge("greeting", END)
        graph.add_edge("question", END)
        graph.add_edge("voicemail", END)
        graph.add_edge("mobile", END)
        graph.add_edge("unknown", END)
        graph.add_edge("meeting_ask",END)
        graph.add_edge("meeting_confirm", END)
        graph.add_edge("whatsapp", END)
        graph.add_edge("lights", END)
        graph.add_edge("goodbye", END)
        graph.add_edge("hangup", END)
        
        memory = InMemorySaver()
        return graph.compile(checkpointer=memory)