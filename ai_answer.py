#!/usr/bin/env python3
from asterisk.agi import AGI
import sys, time
from vosk import Model, KaldiRecognizer
import wave
import threading
import json
from gtts import gTTS
from pydub import AudioSegment
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
        self.action_result:ActionResult = ActionResult(prompt='',result=ResultCode.UNKNOWN)
        self.executor = AsyncExecutor(max_workers=6)
    ##===================================================
    def setResult(self,prompt:str,result:ActionResult):
        with self.result_lock:
            self.action_result.prompt = prompt
            self.action_result.result = result
    ##===================================================
    def getResult(self) -> ActionResult:
        with self.result_lock:
            return self.action_result
    ##===================================================
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
        sound.export(filename, format="wav")
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
    def queryAI(self,text:str,step:str|None = None) -> ChatResponse:
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
        resp = requests.post("http://127.0.0.1:8000/chat",  json=payload, timeout=50)
        if resp.status_code !=200:
            cresp.reply = f"Invalid Request/Response from AI {resp.status_code}"
            return cresp
        jval = resp.json()
        cresp.reply = jval["reply"]
        cresp.action = jval["action"]
        cresp.intent = jval["intent"]
        cresp.step = jval["step"]
        return cresp
    ##===================================================
    def playVoice(self,text,uniqueid):
        tts_file = self.tts(text)
        wav_file = self.convertAudioOut(tts_file,uniqueid)
        self.agi.stream_file(wav_file,sample_offset=1)
    ##===================================================
    ##===================================================
    def ha_toggle_light():
        ha = HomeAssistant()
        ha.toggle_hallway_light()
    ##===================================================
    def whatsapp_message(message:str):
        wa = WhatsApp()
        wa.post_whatsApp(message)
    ##===================================================
    ## Possible Worker thread!
    def doResult(self,cresp:ChatResponse,err,ctx):
        '''Determine What action to take and set the ActionResult value,
           Can be triggered from the FastAPI callback (separate thread) or manually through quickFind.
        '''
        if cresp.action == None or cresp.action == "":
            self.agi.verbose(f"NOACTION",3)
            self.setResult(cresp.reply, ResultCode.UNKNOWN)
            return
        self.agi.verbose(f"Action:{cresp.action} Step:{cresp.step}",3)

        if cresp.action == "hangup":
            self.setResult(cresp.reply,ResultCode.HANGUP)
        elif cresp.action == "voicemail":
            self.setResult(cresp.reply,ResultCode.VOICEMAIL)
        elif cresp.action == "meeting" and cresp.step == "meeting_ask":
            self.setResult(cresp.reply,ResultCode.MEETING_ASK)
        elif cresp.action == "meeting" and cresp.step == "meeting_confirm":
            self.setResult(cresp.reply,ResultCode.MEETING_CONFIRM)
        elif cresp.action == "lights":
            self.setResult(cresp.reply,ResultCode.LIGHTS)
        elif cresp.action == "whatsapp" and cresp.step == "collect_whatsapp_message":
            self.setResult(cresp.reply,ResultCode.WA_ASK)
        elif cresp.action == "whatsapp" and cresp.step != "collect_whatsapp_message":
            self.setResult(cresp.reply,ResultCode.WA_CONFIRM)
    ##===================================================
    def doActions(self,cresp:ChatResponse):
        '''Do the action that was chosen and change the state'''
        action = self.getResult()
        self.agi.verbose(f"Do Action:{action.result.name}",3)
        if action.result == ResultCode.HANGUP:
            self.agi.stream_file("custom/ai_bye")
            self.agi.hangup()
            self.ai_state = AIState.END
            return None
        elif action.result == ResultCode.VOICEMAIL:
            mailbox = "1000"
            self.agi.execute(f"EXEC Voicemail {mailbox}@default")
            self.agi.stream_file("custom/ai_bye")
            self.agi.hangup()
            self.ai_state = AIState.END
            return None
        elif action.result == ResultCode.MEETING_ASK:
            self.playVoice(cresp.reply,self.unique_id)
            self.ai_state = AIState.START
            return "meeting_confirm"
        elif action.result == ResultCode.MEETING_CONFIRM:
            self.playVoice(cresp.reply,self.unique_id)
            self.ai_state = AIState.START
            return None
        elif action.result == ResultCode.LIGHTS:
            self.executor.submit(self.ha_toggle_light, timeout=30)
            self.playVoice("I have toggled the hallway light.",self.unique_id)
            self.ai_state = AIState.ANYTHING_ELSE
            return None
        elif action.result == ResultCode.WA_ASK:
            self.playVoice(cresp.reply,self.unique_id)
            self.ai_state = AIState.START
            return "confirm_whatsapp_message"
        elif action.result == ResultCode.WA_CONFIRM:
            self.executor.submit(self.whatsapp_message,cresp.reply, timeout=30)
            self.playVoice(cresp.reply,self.unique_id)
            self.ai_state = AIState.ANYTHING_ELSE
            return None
        self.ai_state = AIState.ANYTHING_ELSE
        return None
    ##===================================================
    def quickFind(self,text):
        '''Bypass AI and search the stt result for keywords'''
        def _quickFind(text):
            vmkeys = ["voicemail","voice mail"]
            wakeys = ["whatsapp","what's up","what lap"]
            likeys = ["lights"]
            zmkeys = ["zoom", "teams", "meeting", "call back"]
            vm = [kw for kw in vmkeys if (kw in text.lower())]
            if len(vm)>0: return "voicemail"
            wa = [kw for kw in wakeys if (kw in text.lower())]
            if len(wa)>0: return "whatsapp"
            li = [kw for kw in likeys if (kw in text.lower())]
            if len(li)>0: return "lights"
            return None
        #-------------------------------------
        found = _quickFind(text)    #TODO: only if in intent mode..
        step = None
        if found is not None: 
            self.agi.verbose(f"QuickFind:{found}",3)
            if found == "whatsapp":
                step = "collect_whatsapp_message"
            return (found,step)
        return (None,None)
    ##===================================================
    def run(self):
        '''Run the call answering loop max_turns to avoid infinite looping issues or people fooling around.'''
        turn = 0
        text = ''
        next_step = None
        cresp = ChatResponse(reply='')
        while turn < self.max_turns:
            self.agi.verbose(f"state:{self.ai_state.name} turn:{turn}",3)
            #--------------------------------------
            if self.ai_state == AIState.START:
                turn += 1
                self.ai_state = AIState.RECORD
            #--------------------------------------
            elif self.ai_state == AIState.RECORD:
                text = self.recordAndConvert(turn)
                self.agi.verbose(f"{text}")
                (found,step) = self.quickFind(text)
                if found is not None:       
                    cresp.action = found
                    cresp.step = step
                    self.doResult(cresp,None,None)
                    self.ai_state = AIState.RUN_ACTIONS
                    turn += 1
                    continue
                turn += 1
                self.ai_state = AIState.PROCESSING
            #--------------------------------------
            elif self.ai_state == AIState.PROCESSING:
                self.setResult('',ResultCode.UNKNOWN)
                self.executor.submit(self.queryAI, text, next_step, callback=self.doResult, timeout=60)#, context=self)
                self.playVoice("Please wait whilst I deal with your request.",self.unique_id)
                self.ai_state = AIState.WAIT_RESULT
            #--------------------------------------
            elif self.ai_state == AIState.WAIT_RESULT:
                action = self.getResult()
                if action.result != ResultCode.UNKNOWN:
                    self.ai_state = AIState.RUN_ACTIONS
                
                turn += 1
            #--------------------------------------
            elif self.ai_state == AIState.RUN_ACTIONS:
                turn += 1
                next_step = self.doActions(cresp)
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
