#!/usr/bin/env python3
import os
from asterisk.agi import AGI
import time
from datetime import datetime
from vosk import Model, KaldiRecognizer
import wave
import random
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
from dotenv import dotenv_values
##===================================================
class AIAnswer:
    def __init__(self, *args, **kwargs):
        self.agi       = AGI()
        self.call_id   = "unknown"
        self.call_name = "unknown"
        self.unique_id = "unknown"
        self.config = dotenv_values(".env")
        self.voskmodel = Model("/opt/vosk-model/vosk-model-small-en-us-0.15")
        self.max_turns = 60
        self.ai_state:AIMode = AIMode.START
        self.result_lock = threading.Lock()
        self.operation_result:OperationResult = OperationResult(prompt='',state=OperationMode.INTENT)
        self.executor = AsyncExecutor(max_workers=6)
        self.rdis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    ##===================================================
    def setResult(self,prompt:str,state:OperationMode):
        with self.result_lock:
            self.operation_result.prompt = prompt
            self.operation_result.state = state
    ##===================================================
    def getResult(self) -> OperationResult:
        with self.result_lock:
            return self.operation_result
    ##==================================================
    def clear_state(self):
        return self.rdis.set(f"chat_state_{self.call_id}","")
    ##==================================================
    def clear_meeting_state(self):
        return self.rdis.set(f"meeting_state_{self.call_id}","")
    ##==================================================
    def getCallerID(self):
        self.uid = self.agi.get_variable("UNIQUEID")
        self.call_id = self.agi.get_variable("CALLERID(num)")
        self.call_name = self.agi.get_variable("CALLERID(name)")
        self.unique_id = f"{self.call_id}_{self.uid}_0"
        self.agi.verbose(f"{self.call_id} {self.call_name} {self.unique_id}",3)
    ##===================================================
    def answerCall(self):
        self.agi.answer()
        self.agi.stream_file("custom/ai_start")
    ##===================================================
    def recordFile(self) -> str:
        fname = "call_"
        filename = '/tmp/'+ fname + self.unique_id
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
        normalisedsound = effects.normalize(sound)
        normalisedsound = normalisedsound.set_channels(1).set_frame_rate(16000)
        normalisedsound.export(filename, format="wav")
    ##===================================================
    def convertAudioOut(self,filename:str) -> str:
        wav_file = f"/tmp/stt_{self.unique_id}.wav"
        audio = AudioSegment.from_mp3(filename)
        #audio = audio.set_channels(1).set_frame_rate(8000)
        audio = AudioSegment.silent(20) + audio + AudioSegment.silent(20)
        audio.export(wav_file, format="wav",  parameters=["-ar", "8000","-ac","1"])
        with open(wav_file, "rb") as f:
            os.fsync(f.fileno())
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
        tts_file = f"/tmp/tts_{self.unique_id}.mp3"
        gTTS(text, lang="en").save(tts_file)
        return tts_file
    ##===================================================
    def recordAndConvert(self) ->str:
        self.agi.stream_file("beep")
        filename = self.recordFile()
        self.agi.stream_file("beep")
        self.convertAudioIn(filename)
        return self.stt(filename)
    ##===================================================
    def generalAIPost(self,endpoint:str,text:str,step:str|None = None) -> ChatResponse:
        self.agi.verbose(f"{endpoint}AI",3)
        if step is None:
            step = ''
        payload = {
            "unique_id": self.uid,
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
    def pleaseWait(self):
        waits = ["Please wait while I deal with your request.",
                 "Please wait while I check that for you.",
                 "Hold on a sec, I'll look into that for you.",
                 "Hang on while I think about that for a moment."]
        chosen = waits[random.randint(0, len(waits))]
        self.playVoice(chosen)
        
    ##===================================================
    def playVoice(self,text)->bool:
        if not text:
            return False
        tts_file = self.tts(text)
        wav_file = self.convertAudioOut(tts_file)
        self.agi.stream_file(wav_file)
        return True
    ##===================================================
    def actionHangUp(self):
        self.agi.stream_file("custom/ai_bye")
        self.clear_meeting_state()
        self.clear_state()
        self.agi.hangup()
    ##===================================================
    def actionVoicemail(self):
        mailbox = "1000"
        self.agi.execute(f"EXEC Voicemail {mailbox}@default")
        self.agi.stream_file("custom/ai_bye")
        self.agi.hangup()
    ##===================================================
    def actionMobile(self):
        destination = self.config["MOBILE_NUM"]
        self.agi.execute(f"EXEC Dial PJSIP/{destination}")
        self.agi.stream_file("custom/ai_bye")
        self.agi.hangup()
    ##===================================================
    def actionMeetingAsk(self,prompt:str):
        self.agi.verbose(prompt,3)
        if self.playVoice(prompt):
            self.agi.verbose(f"played:{prompt}",3)
    ##===================================================
    def actionMeetingConfirm(self,prompt:str):
        self.playVoice(prompt)
    ##===================================================
    def actionQuestion(self,prompt:str):
        self.playVoice(prompt)
        self.setResult('',OperationMode.INTENT)
    ##===================================================
    def actionLights(self):
        def toggleLight():
            ha = HomeAssistant()
            ha.toggle_hallway_light()

        self.executor.submit(toggleLight, timeout=30)
        self.playVoice("I have toggled the hallway light.")
        self.setResult('',OperationMode.INTENT)
    ##===================================================
    def actionWAAsk(self,prompt:str):
        self.playVoice(prompt)
        self.setResult(prompt,OperationMode.WA_CONFIRM)
    ##===================================================
    def actionWAConfirm(self, prompt):
        def whatsappMessage(message:str)->str|None:
            wa = WhatsApp()
            result = wa.post_whatsApp(message)
            return result
        dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = f"tel:{self.call_id} name:{self.call_name} DT:{dt} - {prompt} [ID:{self.unique_id}]"
        self.agi.verbose(data,3)
        #self.executor.submit(whatsappMessage, data, timeout=30)
        result = whatsappMessage(data)
        if result is None:
            self.playVoice(f"Thank you, I will send the message: {prompt} to Steve.")
        else:
            self.playVoice(f"Oh No, the message didn't Send. {result}")

        self.setResult('',OperationMode.INTENT)
    ##===================================================
    ## [Possible] Worker thread!
    def doResult(self,cresp:ChatResponse,err,ctx):
        '''Determine What action to take and set the ActionResult value,
           Can be triggered from the FastAPI callback (separate thread) or manually through quickFind.
        '''
        if cresp.action == None or cresp.action == "":
            self.setResult(cresp.reply, OperationMode.INTENT)
        elif cresp.action == "unknown":
            self.setResult(cresp.reply,OperationMode.INTENT)
        elif cresp.action == "question":
            self.setResult(cresp.reply,OperationMode.QUESTION)
        elif cresp.action == "intent":
            self.setResult(cresp.reply,OperationMode.INTENT)
        elif cresp.action == "hangup":
            self.setResult(cresp.reply,OperationMode.HANGUP)
        elif cresp.action == "voicemail":
            self.setResult(cresp.reply,OperationMode.VOICEMAIL)
        elif cresp.action == "mobile":
            self.setResult(cresp.reply,OperationMode.MOBILE)
        elif cresp.action == "meeting" and cresp.step == "meeting_ask":
            self.setResult(cresp.reply,OperationMode.MEETING_ASK)
        elif cresp.action == "meeting" and cresp.step == "meeting_confirm":
            self.setResult(cresp.reply,OperationMode.MEETING_CONFIRM)
        elif cresp.action == "meeting" and cresp.step == "end":
            self.setResult(cresp.reply,OperationMode.HANGUP)
        elif cresp.action == "lights":
            self.setResult(cresp.reply,OperationMode.LIGHTS)
        elif cresp.action == "whatsapp" and cresp.step == "collect_whatsapp_message":
            self.setResult(cresp.reply,OperationMode.WA_ASK)
        elif cresp.action == "whatsapp" and cresp.step == "confirm_whatsapp_message":
            self.setResult(cresp.reply,OperationMode.WA_CONFIRM)

        self.agi.verbose(f"Action:{cresp.action} Step:{cresp.step} Operation:{self.getResult().state.name}",3)
    ##===================================================
    def doActions(self,cresp:ChatResponse)->str|None:
        '''Do the action that was chosen and change the state'''
        operation:OperationResult = self.getResult()
        self.agi.verbose(f"Do Action:{operation.state.name}",3)

        if operation.state == OperationMode.INTENT:
            self.playVoice(f"I'm sorry, I didn't understand you, please try again.")
            self.setResult("",OperationMode.INTENT)
            self.ai_state = AIMode.START
            return None
        elif operation.state == OperationMode.QUESTION:
            self.actionQuestion(operation.prompt)
            self.ai_state = AIMode.START
            return None
        elif operation.state == OperationMode.HANGUP:
            self.actionHangUp()
            self.ai_state = AIMode.END
            return None
        elif operation.state == OperationMode.VOICEMAIL:
            self.actionVoicemail()
            self.ai_state = AIMode.END
            return None
        elif operation.state == OperationMode.MOBILE:
            self.actionMobile()
            self.ai_state = AIMode.END
            return None
        elif operation.state == OperationMode.MEETING_ASK:
            self.actionMeetingAsk(operation.prompt)
            self.ai_state = AIMode.START
            return None
        elif operation.state == OperationMode.MEETING_CONFIRM:
            self.actionMeetingConfirm(operation.prompt)
            self.ai_state = AIMode.START
            return None
        elif operation.state == OperationMode.LIGHTS:
            self.actionLights()
            self.ai_state = AIMode.ANYTHING_ELSE
            return None
        elif operation.state == OperationMode.WA_ASK:
            self.actionWAAsk(operation.prompt)
            self.ai_state = AIMode.START
            return "confirm_whatsapp_message"
        elif operation.state == OperationMode.WA_CONFIRM:
            self.actionWAConfirm(cresp.reply)
            self.ai_state = AIMode.ANYTHING_ELSE
            return None
        self.agi.verbose("OPState not found",3)
        #self.ai_state = AIState.ANYTHING_ELSE
        return None
    ##===================================================
    def quickFind(self,text):
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
            self.unique_id = f"{self.call_id}_{self.uid}_{turn}"
            self.agi.verbose(f"-= AIState:{self.ai_state.name} Turn:{turn} Operation:{operation.state.name} =-",3)
            #--------------------------------------
            if self.ai_state == AIMode.START:
                turn += 1
                self.ai_state = AIMode.RECORD
            #--------------------------------------
            elif self.ai_state == AIMode.RECORD:
                text = self.recordAndConvert()
                self.agi.verbose(f"{text}",3)
                cresponse.reply = text
                # if operation.state == OperationState.INTENT:
                #     (found,step,reply) = self.quickFind(text)
                #     if found is not None:       
                #         cresponse.action = found
                #         cresponse.step = step
                #         cresponse.reply = reply
                #         self.doResult(cresponse,None,None)
                #         self.ai_state = AIState.RUN_ACTIONS
                #         turn += 1
                #         continue
                turn += 1
                self.ai_state = AIMode.PROCESSING
            #--------------------------------------
            elif self.ai_state == AIMode.PROCESSING:
                if operation.state == OperationMode.MEETING_ASK or operation.state == OperationMode.MEETING_CONFIRM:
                    self.executor.submit(self.generalAIPost,"meeting", text, next_step, callback=self.doResult, timeout=60)#, context=self)
                elif operation.state == OperationMode.WA_CONFIRM:
                    cresponse.action == "whatsapp" 
                    cresponse.step == "confirm_whatsapp_message"
                    self.ai_state = AIMode.RUN_ACTIONS
                    continue
                else:
                    self.executor.submit(self.generalAIPost,"chat", text, next_step, callback=self.doResult, timeout=60)#, context=self)
                self.setResult('',OperationMode.UNKNOWN)
                self.pleaseWait()
                self.ai_state = AIMode.WAIT_RESULT
            #--------------------------------------
            elif self.ai_state == AIMode.WAIT_RESULT:
                if operation.state != OperationMode.UNKNOWN:
                    self.ai_state = AIMode.RUN_ACTIONS
                
                turn += 1
            #--------------------------------------
            elif self.ai_state == AIMode.RUN_ACTIONS:
                turn += 1
                next_step = self.doActions(cresponse)
            #--------------------------------------
            elif self.ai_state == AIMode.UNKNOWN:
                self.playVoice("I am sorry, I have not been able to deal with your request. Please try again.")
                turn = 1
                self.ai_state = AIMode.START
            #--------------------------------------
            elif self.ai_state == AIMode.ANYTHING_ELSE:
                self.playVoice("Can I help with anything else?")
                turn += 1
                self.ai_state = AIMode.START
            #--------------------------------------
            elif self.ai_state == AIMode.END:
                break
            #--------------------------------------
            time.sleep(0.5)
        self.agi.stream_file("custom/ai_bye")
        self.agi.hangup()
        self.agi.verbose("Stopped",3)
    ##===================================================
    def newCall(self):
        self.answerCall()
        self.getCallerID()
        self.run()
    ##===================================================

ai = AIAnswer()
ai.newCall()
##===================================================
##===================================================
