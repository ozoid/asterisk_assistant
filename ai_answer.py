#!/usr/bin/env python3
from asterisk.agi import AGI
import time
from datetime import datetime
from vosk import Model, KaldiRecognizer
import wave
import threading
import json
import redis
from gtts import gTTS
from pydub import AudioSegment, effects
import requests
from home_assistant import HomeAssistant
from whatsapp import WhatsApp
from models import *
from async_executor import AsyncExecutor
##===================================================
class AIAnswer:
    def __init__(self, *args, **kwargs):
        self.agi       = AGI()
        self.call_id   = "unknown"
        self.call_name = "unknown"
        self.unique_id = "unknown"
        self.voskmodel = Model("/opt/vosk-model/vosk-model-small-en-us-0.15")
        self.max_turns = 60
        self.ai_state:AIState = AIState.START
        self.result_lock = threading.Lock()
        self.operation_result:OperationResult = OperationResult(prompt='',state=OperationState.INTENT)
        self.executor = AsyncExecutor(max_workers=6)
        self.rdis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    ##===================================================
    def setResult(self,prompt:str,state:OperationState):
        with self.result_lock:
            self.operation_result.prompt = prompt
            self.operation_result.state = state
    ##===================================================
    def getResult(self) -> OperationResult:
        with self.result_lock:
            return self.operation_result
    ##==================================================
    def clear_state(self,call_id):
        return self.rdis.set(f"chat_state_{call_id}","")
    ##==================================================
    def clear_meeting_state(self,call_id):
        return self.rdis.set(f"meeting_state_{call_id}","")
    ##==================================================
    def getCallerID(self):
        self.unique_id = self.agi.get_variable("UNIQUEID")
        self.call_id = self.agi.get_variable("CALLERID(num)")
        self.call_name = self.agi.get_variable("CALLERID(name)")
        self.agi.verbose(f"{self.call_id} {self.call_name} {self.unique_id}",3)
    ##===================================================
    def answerCall(self):
        self.agi.answer()
        self.agi.stream_file("custom/ai_start")
    ##===================================================
    def recordFile(self,turn) -> str:
        fname = "call_"
        filename = '/tmp/'+ fname + str(turn) 
        format = 'wav' #ulaw'
        intkey = '#'
        timeout = 5000
        beep = ''
        offset = '0'
        silence = 's=2'
        self.agi.execute('RECORD FILE', (filename), (format), (intkey), (timeout), (offset), (beep), (silence))
        return filename + ".wav"
    ##===================================================
    def convertAudioIn(self,filename:str):
        sound = AudioSegment.from_file(filename)
        sound = sound.set_channels(1).set_frame_rate(16000)
        normalisedsound = effects.normalize(sound)
        normalisedsound.export(filename, format="wav")
    ##===================================================
    def convertAudioOut(self,filename:str,turn) -> str:
        wav_file = f"/tmp/ai_reply_{turn}.wav"
        AudioSegment.from_mp3(filename).export(wav_file, format="wav",parameters=["-ar", "8000","-ac","1"])
        return wav_file.replace(".wav","")
    ##===================================================
    def stt(self,filename:str) -> str:
        wf = wave.open(filename, "rb")
        rec = KaldiRecognizer(self.voskmodel, wf.getframerate())
        text = ""
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                text += res.get("text","") + " "
        # Get final chunk
        res = json.loads(rec.FinalResult())
        text += res.get("text","")
        return text.strip()
    ##===================================================
    def tts(self,text:str) -> str:
        tts_file = f"/tmp/ai_reply_{self.turn}.mp3"
        gTTS(text, lang="en").save(tts_file)
        return tts_file
    ##===================================================
    def recordAndConvert(self,turn) ->str:
        self.agi.stream_file("beep")
        filename = self.recordFile(turn)
        self.agi.stream_file("beep")
        self.convertAudioIn(filename)
        return self.stt(filename)
    ##===================================================
    def generalAIPost(self,endpoint:str,text:str,step:str|None = None) -> ChatResponse:
        self.agi.verbose(f"{endpoint}AI",3)
        if step is None:
            step = ''
        payload = {
            "unique_id": self.unique_id,
            "call_id": self.call_id,
            "call_name": self.call_name,
            "text": text,
            "step": step,
        }
        cresp = ChatResponse(reply='')
        resp = requests.post(f"http://127.0.0.1:8000/{endpoint}",  json=payload, timeout=50)
        if resp.status_code !=200:
            cresp.reply = f"Invalid Request/Response from AI {resp.status_code}"
            cresp.action = "error"
            return cresp
        jval = resp.json()
        cresp.reply = jval["reply"]
        cresp.action = jval["action"]
        cresp.intent = jval["intent"]
        cresp.step = jval["step"]
        return cresp
    ##===================================================
    ##===================================================
    def playVoice(self,text,uniqueid)->bool:
        if text is None or text == "":
            return False
        tts_file = self.tts(text)
        wav_file = self.convertAudioOut(tts_file,uniqueid)
        self.agi.stream_file(wav_file,sample_offset=1)
        return True
    ##===================================================
    ##===================================================
    def ha_toggle_light(self):
        ha = HomeAssistant()
        ha.toggle_hallway_light()
    ##===================================================
    def whatsapp_message(self,message:str):
        wa = WhatsApp()
        wa.post_whatsApp(message)
    ##===================================================
    ## Possible Worker thread!
    def doResult(self,cresp:ChatResponse,err,ctx):
        '''Determine What action to take and set the ActionResult value,
           Can be triggered from the FastAPI callback (separate thread) or manually through quickFind.
        '''
#        self.agi.verbose(f"Start Action:{cresp.action} Step:{cresp.step} Operation:{self.getResult().state.name}",3)
        if cresp.action == None or cresp.action == "":
            self.agi.verbose(f"NOACTION",3)
            self.setResult(cresp.reply, OperationState.UNKNOWN)
            return
        
        if cresp.action == "intent":
            self.setResult(cresp.reply,OperationState.INTENT)
        elif cresp.action == "hangup":
            self.setResult(cresp.reply,OperationState.HANGUP)
        elif cresp.action == "voicemail":
            self.setResult(cresp.reply,OperationState.VOICEMAIL)
        elif cresp.action == "meeting" and cresp.step == "meeting_ask":
            self.setResult(cresp.reply,OperationState.MEETING_ASK)
        elif cresp.action == "meeting" and cresp.step == "meeting_confirm":
            self.setResult(cresp.reply,OperationState.MEETING_CONFIRM)
        elif cresp.action == "meeting" and cresp.step == "end":
            self.setResult(cresp.reply,OperationState.HANGUP)
        elif cresp.action == "lights":
            self.setResult(cresp.reply,OperationState.LIGHTS)
        elif cresp.action == "whatsapp" and cresp.step == "collect_whatsapp_message":
            self.setResult(cresp.reply,OperationState.WA_ASK)
        elif cresp.action == "whatsapp" and cresp.step == "confirm_whatsapp_message":
            self.setResult(cresp.reply,OperationState.WA_CONFIRM)
        

        self.agi.verbose(f"Action:{cresp.action} Step:{cresp.step} Operation:{self.getResult().state.name}",3)
    ##===================================================
    def doActions(self,cresp:ChatResponse)->str|None:
        '''Do the action that was chosen and change the state'''
        operation:OperationResult = self.getResult()
        self.agi.verbose(f"Do Action:{operation.state.name}",3)

        if operation.state == OperationState.INTENT:
            self.playVoice(f"Operation:Intent.",self.unique_id)
            self.ai_state = AIState.START
            return None
        elif operation.state == OperationState.HANGUP:
            self.agi.stream_file("custom/ai_bye")
            self.clear_meeting_state()
            self.clear_state()
            self.agi.hangup()
            self.ai_state = AIState.END
            return None
        elif operation.state == OperationState.VOICEMAIL:
            mailbox = "1000"
            self.agi.execute(f"EXEC Voicemail {mailbox}@default")
            self.agi.stream_file("custom/ai_bye")
            self.agi.hangup()
            self.ai_state = AIState.END
            return None
        elif operation.state == OperationState.MEETING_ASK:
            #cresp.step = "meeting_confirm"
            cresp.reply = operation.prompt
            self.agi.verbose("meetingAsk",3)
            self.agi.verbose(cresp.reply,3)
            if self.playVoice(cresp.reply,self.unique_id):
                self.agi.verbose(f"played:{cresp.reply}",3)
            self.ai_state = AIState.START
            return None
        elif operation.state == OperationState.MEETING_CONFIRM:
            cresp.reply = operation.prompt
            cresp.step = "end"
            self.playVoice(cresp.reply,self.unique_id)
            self.ai_state = AIState.START
            return None
        elif operation.state == OperationState.LIGHTS:
            self.executor.submit(self.ha_toggle_light, timeout=30)
            self.playVoice("I have toggled the hallway light.",self.unique_id)
            self.ai_state = AIState.ANYTHING_ELSE
            return None
        elif operation.state == OperationState.WA_ASK:
            cresp.reply = operation.prompt
            self.playVoice(cresp.reply,self.unique_id)
            self.setResult(cresp.reply,OperationState.WA_CONFIRM)
            self.ai_state = AIState.START
            return "confirm_whatsapp_message"
        elif operation.state == OperationState.WA_CONFIRM:
            #cresp.reply = operation.prompt
            dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = f"tel:{self.call_id} name:{self.call_name} DT:{dt}\n {cresp.reply}"
            self.executor.submit(self.whatsapp_message, data, timeout=30)
            self.playVoice(cresp.reply,self.unique_id)
            self.setResult('',OperationState.INTENT)
            self.ai_state = AIState.ANYTHING_ELSE
            return None
        self.agi.verbose("OPState not found",3)
        #self.ai_state = AIState.ANYTHING_ELSE
        return None
    ##===================================================
    def quickFind(self,text,cresp:ChatResponse):
        '''Bypass AI and search the stt result for keywords'''
        def _quickFind(text):
            vmkeys = ["voicemail","voice mail"]
            wakeys = ["whatsapp","what's up","what lap"]
            likeys = ["lights"]
            zmkeys = ["zoom", "teams", "meeting", "call back",]
            vm = [kw for kw in vmkeys if (kw in text.lower())]
            if len(vm)>0: return ("voicemail","","Connecting to Voicemail")
            wa = [kw for kw in wakeys if (kw in text.lower())]
            if len(wa)>0: return ("whatsapp","collect_whatsapp_message","What is the message you would like to send?")
            li = [kw for kw in likeys if (kw in text.lower())]
            if len(li)>0: return ("lights","","Are you sure you want to toggle the hallway light?")
            li = [kw for kw in zmkeys if (kw in text.lower())]
            if len(li)>0: return ("meeting","meeting_ask","What date and time would you like the meeting?")
            return (None,None,None)
        #-------------------------------------
        
        (found,step,reply) = _quickFind(text)    #TODO: only if in intent mode..
        if found is not None: 
            self.agi.verbose(f"QuickFind:{found}",3)
            if found == "whatsapp":
                step = "collect_whatsapp_message"
            return (found,step,reply)
        return None
    ##===================================================
    def run(self):
        '''Run the call answering loop max_turns to avoid infinite looping issues or people fooling around.'''
        turn = 0
        text = ''
        next_step = None
        cresponse:ChatResponse = ChatResponse(reply='')
        while turn < self.max_turns:
            operation = self.getResult()
            self.agi.verbose(f"-= AIState:{self.ai_state.name} Turn:{turn} Operation:{operation.state.name} =-",3)
            #--------------------------------------
            if self.ai_state == AIState.START:
                turn += 1
                self.ai_state = AIState.RECORD
            #--------------------------------------
            elif self.ai_state == AIState.RECORD:
                text = self.recordAndConvert(turn)
                self.agi.verbose(f"{text}")
                # if operation.state == OperationState.INTENT:
                #     (found,step,reply) = self.quickFind(text,cresponse)
                #     if found is not None:       
                #         cresponse.action = found
                #         cresponse.step = step
                #         cresponse.reply = reply
                #         self.doResult(cresponse,None,None)
                #         self.ai_state = AIState.RUN_ACTIONS
                #         turn += 1
                #         continue
                turn += 1
                self.ai_state = AIState.PROCESSING
            #--------------------------------------
            elif self.ai_state == AIState.PROCESSING:
                if operation.state == OperationState.MEETING_ASK or operation.state == OperationState.MEETING_CONFIRM:
                    self.executor.submit(self.generalAIPost,"meeting", text, next_step, callback=self.doResult, timeout=60)#, context=self)
                elif operation.state == OperationState.WA_ASK:
                    pass
                elif operation.state == OperationState.WA_CONFIRM:
                    cresponse.reply = "Thank you. I will send your message to Steve."
                    cresponse.action == "whatsapp" 
                    cresponse.step == "confirm_whatsapp_message"
                    self.ai_state = AIState.RUN_ACTIONS
                    continue
                else:
                    self.executor.submit(self.generalAIPost,"chat", text, next_step, callback=self.doResult, timeout=60)#, context=self)
                self.setResult('',OperationState.UNKNOWN)
                self.playVoice("Please wait whilst I deal with your request.",self.unique_id)
                self.ai_state = AIState.WAIT_RESULT
            #--------------------------------------
            elif self.ai_state == AIState.WAIT_RESULT:
                if operation.state != OperationState.UNKNOWN:
                    self.ai_state = AIState.RUN_ACTIONS
                
                turn += 1
            #--------------------------------------
            elif self.ai_state == AIState.RUN_ACTIONS:
                turn += 1
                next_step = self.doActions(cresponse)
            #--------------------------------------
            elif self.ai_state == AIState.UNKNOWN:
                self.playVoice("I am sorry, I have not been able to deal with your request. Please try again.",self.unique_id)
                turn = 1
                self.ai_state = AIState.START
            #--------------------------------------
            elif self.ai_state == AIState.ANYTHING_ELSE:
                self.playVoice("Can I help with anything else?",self.unique_id)
                turn += 1
                self.ai_state = AIState.START
            #--------------------------------------
            elif self.ai_state == AIState.END:
                break
            #--------------------------------------
            time.sleep(0.5)
        self.agi.stream_file("custom/ai_bye")
        self.agi.hangup()
        self.agi.verbose("Stopped",3)
    ##===================================================
    def newCall(self):
        self.turn = 0
        self.answerCall()
        self.getCallerID()
        self.run()
    ##===================================================

ai = AIAnswer()
ai.newCall()
##===================================================
##===================================================
