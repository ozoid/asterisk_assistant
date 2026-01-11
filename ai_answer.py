#!/usr/bin/env python3
import os
from asterisk.agi import AGI
import time
from datetime import datetime
from vosk import Model, KaldiRecognizer
from pathlib import Path
import wave
import random
import threading
import json
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
        self.uid   = "unknown"
        self.call_id   = "unknown"
        self.call_name = "unknown"
        self.unique_id = "unknown"
        BASE_DIR = Path(__file__).resolve().parent
        self.config = dotenv_values(BASE_DIR / ".env")
        self.voskmodel = Model("/opt/vosk-model/vosk-model-small-en-us-0.15")
        self.max_turns = 240
        self.ai_state:AIMode = AIMode.START
        self.mode_lock = threading.Lock()
        self.operation_mode:OperationMode = OperationMode.INTENT
        self.response_lock = threading.Lock()
        self.current_response:ChatResponse = ChatResponse(reply='',text='')
        self.executor = AsyncExecutor(max_workers=4)
        self.time = None
    ##===================================================
    def timer(self,fn:str):
        if self.time is None:
            self.time = time.monotonic()
            self.agi.verbose(f"Function:{fn} 0",3)
            return
        now = time.monotonic()
        self.agi.verbose(f"Function:{fn} {now - self.time}",3)
        self.time = now
    ##===================================================
    def setResult(self,reponse:ChatResponse):
        with self.response_lock:
            self.current_response = reponse
    ##===================================================
    def setReply(self,reply:str):
        with self.response_lock:
            self.current_response.reply = reply
    ##===================================================
    def setText(self,text:str):
        with self.response_lock:
            self.current_response.text = text
    ##===================================================
    def setStep(self,step:str|None):
        with self.response_lock:
            self.current_response.step = step
    ##===================================================
    def getResult(self) -> ChatResponse:
        with self.response_lock:
            return self.current_response
    ##===================================================
    def setMode(self,state:OperationMode):
        with self.mode_lock:
            self.operation_mode = state
    ##===================================================
    def getMode(self) -> OperationMode:
        with self.mode_lock:
            return self.operation_mode
    ##==================================================
    def getCallerID(self):
        self.uid = self.agi.get_variable("UNIQUEID")
        self.call_id = self.agi.get_variable("CALLERID(num)")
        self.call_name = self.agi.get_variable("CALLERID(name)")
        self.unique_id = f"{self.call_id}_{self.uid}_0"
    ##===================================================
    def answerCall(self):
        self.agi.answer()
        self.agi.stream_file("custom/ai_start")
    ##===================================================
    def recordFile(self) -> str:
        tstr = str(time.monotonic())
        filename = f"/tmp/call_{self.unique_id}_{tstr}"
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
        tstr = str(time.monotonic())
        wav_file = f"/tmp/stt_{self.unique_id}_{tstr}.wav"
        audio = AudioSegment.from_mp3(filename)
        #audio = audio.set_channels(1).set_frame_rate(8000)
        audio = AudioSegment.silent(20) + audio + AudioSegment.silent(20)
        audio.export(wav_file, format="wav",  parameters=["-ar", "8000","-ac","1"])
        with open(wav_file, "rb") as f:
            os.fsync(f.fileno()) # ensure closed/done
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
        tstr = str(time.monotonic())
        tts_file = f"/tmp/tts_{self.unique_id}_{tstr}.mp3"
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
    def clearState(self,name:str):
        payload = StoreDeet(
            name=name,
            call_id=self.call_id
        )
        data = payload.model_dump_json(exclude_unset=True, exclude_none=True).encode("utf-8")
        response = requests.post(f"http://127.0.0.1:8000/clear_state",  data=data, timeout=5)
        if response.status_code !=200:
            return False
        jval = response.json()
        if jval.get("success",False) == True:
            return True
        return False
    ##===================================================
    def generalAIPost(self,endpoint:str,text:str,intent:str,step:str|None = None) -> ChatResponse:
        self.agi.verbose(f"{endpoint}AI")
        if step is None:
            step = ''
        payload = ChatRequest(
            unique_id=self.uid,
            call_id=self.call_id,
            call_name=self.call_name,
            text=text,
            messages=[],
            intent=intent,
            step=step,
        )
        cresp = ChatResponse(reply='',text=text)
        data = payload.model_dump_json(exclude_unset=True, exclude_none=True).encode("utf-8")
        response = requests.post(f"http://127.0.0.1:8000/{endpoint}",  data=data, timeout=50)
        if response is None or response.status_code !=200:
            cresp.reply = f"Invalid Request/Response from AI"
            cresp.intent = "error"
            return cresp
        jval = response.json()
        cresp.reply = jval["reply"]
        cresp.intent = jval["intent"]
        cresp.step = jval["step"]
        return cresp
    ##===================================================
    def pleaseHangOn(self):
        waits = ["Thank you for waiting, I shall be with you soon.",
                 "Thank you for holding on, I am working my hardest to deal with your request.",
                 "Sorry for the delay, my computer seems to be running slow today.",
                 "Please continue to hold for a second, I am nearly done."]
        chosen = waits[random.randint(0, len(waits))]
        self.playVoice(chosen)
        self.playMusic()
    ##===================================================
    def pleaseWait(self):
        waits = ["Please wait while I deal with your request.",
                 "Please wait while I check that for you.",
                 "Hold on a second, I'll look into that for you.",
                 "Hang on while I think about that for a moment."]
        chosen = waits[random.randint(0, len(waits))]
        self.playVoice(chosen)
        self.playMusic()
    ##===================================================
    def playMusic(self):
        self.agi.execute(f"EXEC StartMusicOnHold default")
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
        self.clearState("all")
        self.agi.hangup()
    ##===================================================
    def actionVoicemail(self):
        mailbox = "1000"
        self.agi.execute(f"EXEC Voicemail {mailbox}@default")
        self.actionHangUp()
    ##===================================================
    def actionMobile(self):
        destination = self.config["MOBILE_NUM"]
        self.agi.execute(f"EXEC Dial PJSIP/{destination}")
        self.actionHangUp()
    ##===================================================
    def actionLights(self):
        def toggleLight():
            ha = HomeAssistant()
            ha.toggle_hallway_light()

        threading.Thread(target=toggleLight,daemon=True).start()
        self.playVoice("I have toggled the hallway light.")
    ##===================================================
    def actionWAConfirm(self, prompt,message):
        def whatsappMessage(message:str)->str|None:
            wa = WhatsApp()
            wa.post_whatsApp(message)

        dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = f"tel:{self.call_id} name:{self.call_name} DT:{dt} - {message} [ID:{self.unique_id}]"
        threading.Thread(target=whatsappMessage,args=[data],daemon=True).start()
        self.playVoice(f"Thank you, I will send the message: {message} to Steve.")
    ##===================================================
    ## Worker thread!
    def doResult(self,cresp:ChatResponse,err,ctx):
        '''Determine What action to take and set the ActionResult value,
           Triggered from the FastAPI callback (separate thread) [or manually through quickFind].
        '''
        self.setResult(cresp)
        if cresp.intent == None or cresp.intent == "":
            self.setMode(OperationMode.INTENT)
        elif cresp.intent == "goodbye":
            self.setMode(OperationMode.HANGUP)
        elif cresp.intent == "unknown":
            self.setMode(OperationMode.INTENT)
        elif cresp.intent == "error":
            self.setMode(OperationMode.ERROR)
        elif cresp.intent == "question":
            self.setMode(OperationMode.QUESTION)
        elif cresp.intent == "intent":
            self.setMode(OperationMode.INTENT)
        elif cresp.intent == "hangup":
            self.setMode(OperationMode.HANGUP)
        elif cresp.intent == "voicemail":
            self.setMode(OperationMode.VOICEMAIL)
        elif cresp.intent == "mobile":
            self.setMode(OperationMode.MOBILE)
        elif cresp.intent == "meeting" and cresp.step == "complete":
            self.setMode(OperationMode.MEETING_CONFIRM)
        elif cresp.intent == "meeting":
            self.setMode(OperationMode.MEETING_ASK)
        elif cresp.intent == "lights":
            self.setMode(OperationMode.LIGHTS)
        elif cresp.intent == "whatsapp" and cresp.step == "collect_whatsapp_message":
            self.setMode(OperationMode.WA_ASK)
        elif cresp.intent == "whatsapp" and cresp.step == "confirm_whatsapp_message":
            self.setMode(OperationMode.WA_CONFIRM)
    ##===================================================
    def doActions(self)->str|None:
        '''Do the action that was chosen and change the state'''
        operation:OperationMode = self.getMode()
        cresp:ChatResponse = self.getResult()

        if operation == OperationMode.INTENT:
            self.playVoice("Can I help with anything else?")
            self.setMode(OperationMode.INTENT)
            self.ai_state = AIMode.START
            return None
        elif operation == OperationMode.ERROR:
            self.playVoice(f"I'm sorry, there seems to have been an error, I shall put you through to voicemail. ")
            self.actionVoicemail()
            self.ai_state = AIMode.END
            return None
        elif operation == OperationMode.QUESTION:
            self.playVoice(cresp.reply)
            self.setMode(OperationMode.INTENT)
            self.ai_state = AIMode.RUN_ACTIONS
            return None
        elif operation == OperationMode.HANGUP:
            self.actionHangUp()
            self.ai_state = AIMode.END
            return None
        elif operation == OperationMode.VOICEMAIL:
            self.actionVoicemail()
            self.ai_state = AIMode.END
            return None
        elif operation == OperationMode.MOBILE:
            self.actionMobile()
            self.ai_state = AIMode.END
            return None
        elif operation == OperationMode.MEETING_ASK:
            self.playVoice(cresp.reply)
            self.ai_state = AIMode.START
            return None
        elif operation == OperationMode.MEETING_CONFIRM:
            self.playVoice(cresp.reply)
            self.setMode(OperationMode.INTENT)
            self.ai_state = AIMode.RUN_ACTIONS
            return None
        elif operation == OperationMode.LIGHTS:
            self.actionLights()
            self.setMode(OperationMode.INTENT)
            self.ai_state = AIMode.RUN_ACTIONS
            return None
        elif operation == OperationMode.WA_ASK:
            self.playVoice(cresp.reply)
            self.setMode(OperationMode.WA_CONFIRM)
            self.ai_state = AIMode.START
            return "confirm_whatsapp_message"
        elif operation == OperationMode.WA_CONFIRM:
            self.actionWAConfirm(cresp.reply,cresp.text)
            self.setMode(OperationMode.INTENT)
            self.ai_state = AIMode.RUN_ACTIONS
            return None
        elif operation == OperationMode.ANYTHING_ELSE:
            self.setMode(OperationMode.INTENT)
            self.ai_state = AIMode.RUN_ACTIONS
            return None
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
        '''Run Call Answering Loop.'''
        turn = 0
        text = ''
        next_step = None
        while turn < self.max_turns:
            operation = self.getMode()
            self.unique_id = f"{self.call_id}_{self.uid}_{turn}"
            self.agi.verbose(f"{self.ai_state.name} {operation.name}",3)
            #--------------------------------------
            if self.ai_state == AIMode.START:
                turn = 0
                text = ''
                self.ai_state = AIMode.RECORD
            #--------------------------------------
            elif self.ai_state == AIMode.RECORD:
                text = self.recordAndConvert()
                self.setText(text)
                self.ai_state = AIMode.PROCESSING
            #--------------------------------------
            elif self.ai_state == AIMode.PROCESSING:
                intent = OperationMode.intent(operation)
                if operation == OperationMode.MEETING_ASK or operation == OperationMode.MEETING_CONFIRM:
                    self.executor.submit(self.generalAIPost,"meeting", text, intent, next_step, callback=self.doResult, timeout=60)#, context=self)
                elif operation == OperationMode.WA_CONFIRM:
                    self.ai_state = AIMode.RUN_ACTIONS
                    continue
                else:
                    self.executor.submit(self.generalAIPost,"chat", text, intent, next_step, callback=self.doResult, timeout=60)#, context=self)
                self.setMode(OperationMode.UNKNOWN)
                self.pleaseWait()
                self.ai_state = AIMode.WAIT_RESULT
            #--------------------------------------
            elif self.ai_state == AIMode.WAIT_RESULT:
                if turn % 60 == 0: # every 30 seconds play please hang-on
                    self.pleaseHangOn()
                if operation != OperationMode.UNKNOWN:
                    self.ai_state = AIMode.RUN_ACTIONS
            #--------------------------------------
            elif self.ai_state == AIMode.RUN_ACTIONS:
                #self.executor.shutdown()
                next_step = self.doActions()
                self.setStep(next_step)
            #--------------------------------------
            elif self.ai_state == AIMode.UNKNOWN:
                self.playVoice("I am sorry, I have not been able to deal with your request. Please try again.")
                self.ai_state = AIMode.START
            #--------------------------------------
            elif self.ai_state == AIMode.END:
                break
            #--------------------------------------
            turn += 1
            time.sleep(0.5)
        self.actionHangUp()
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
