#!/usr/bin/env python3
from asterisk.agi import AGI
import sys, time
from vosk import Model, KaldiRecognizer
import wave
import json
from gtts import gTTS
from pydub import AudioSegment
import requests
from enum import IntEnum
from models import ChatRequest,ChatResponse
##===================================================
class AIState(IntEnum):
    START = 0
    RECORD = 1
    PROCESSING = 2
    RUN_ACTIONS = 3
    ANYTHING_ELSE = 4
    END = 99
##===================================================
class ActionResult(IntEnum):
    LEVEL0 = 0
    LEVEL1 = 1
    HANGUP = 2
##===================================================
class AIAnswer:
    def __init__(self, *args, **kwargs):
        self.agi       = AGI()
        self.call_id   = "unknown"
        self.call_name = "unknown"
        self.unique_id = "unknown"
        self.voskmodel = Model("/opt/vosk-model/vosk-model-small-en-us-0.15")
        self.max_turns = 3
        self.turn      = 0
        self.ai_state:AIState = AIState.START
    ##===================================================
    def getCallerID(self):
        self.unique_id = self.agi.get_variable("UNIQUEID")
        self.call_id = self.agi.get_variable("CALLERID(num)")
        self.call_name = self.agi.get_variable("CALLERID(name)")
        #self.call_id = self.agi.argv[1] if len(self.agi.argv) > 1 else "unknown"
        #self.call_name = self.agi.argv[2] if len(self.agi.argv) > 2 else "unknown"
    ##===================================================
    def answerCall(self):
        self.agi.answer()
        self.agi.stream_file("custom/ai_start")
    ##===================================================
    def recordFile(self) -> str:
        fname = "call_"
        filename = '/tmp/'+ fname + str(self.turn) 
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
    def convertAudioOut(self,filename:str) -> str:
        wav_file = f"/tmp/ai_reply_{self.turn}.wav"
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
    def queryAI(self,text:str,step:str|None = None) -> ChatResponse:
        payload = {
            "unique_id": self.unique_id,
            "call_id": self.call_id,
            "call_name": self.call_name,
            "text": text,
            "step": step,
        }
        cresp = ChatResponse()
        resp = requests.post("http://127.0.0.1:8000/chat",  json=payload, timeout=50)
        if resp.status_code !=200:
            cresp.reply = f"Invalid Request/Response from AI {resp.status_code}"
            return cresp
        jval = resp.json()
        cresp.reply = jval["reply"]
        cresp.action = jval["action"]
        cresp.response_text = jval["response_text"]
        cresp.step = jval["step"]
        return cresp
    ##===================================================
    def playVoice(self,text):
        tts_file = self.tts(text)
        wav_file = self.convertAudioOut(tts_file)
        self.agi.stream_file(wav_file)
    ##===================================================
    def doActions(self,cresp:ChatResponse) -> str:
        if cresp.action == None or cresp.action == "":
            self.ai_state = AIState.END
            return None

        if cresp.action == "hangup":
            self.agi.stream_file("custom/ai_bye")
            self.agi.hangup()
            self.ai_state = AIState.END
            return None

        elif cresp.action == "voicemail":
            mailbox = "1000"
            context = "default"
            self.agi.execute('Voicemail',f"{mailbox}@{context}")
            vmstatus = self.agi.get_variable("VMSTATUS")
            self.agi.stream_file("custom/ai_bye")
            self.agi.hangup()
            self.ai_state = AIState.END
            return None

        elif cresp.action == "whatsapp" and cresp.step == "collect_whatsapp_message":
            self.playVoice(cresp.response_text)
            self.ai_state = AIState.START
            return "confirm_whatsapp_message"

        self.ai_state = AIState.ANYTHING_ELSE
        return None
        
    ##===================================================
    def tts(self,text:str) -> str:
        tts_file = f"/tmp/ai_reply_{self.turn}.mp3"
        gTTS(text, lang="en").save(tts_file)
        return tts_file
    ##===================================================
    def run(self):
        text = ''
        next_step:str|None = None
        cresp = ChatResponse()
        while self.turn < self.max_turns:

            if self.ai_state == AIState.START:
                self.agi.verbose(f"Turn {self.turn + 1}", 3)
                self.ai_state = AIState.RECORD

            elif self.ai_state == AIState.RECORD:
                  self.agi.stream_file("beep")
                filename = self.recordFile()
                self.convertAudioIn(filename)
                text = self.stt(filename)
                self.ai_state = AIState.PROCESSING

            elif self.ai_state == AIState.PROCESSING:
                cresp = self.queryAI(text,next_step)
                next_step = None
                self.ai_state = AIState.RUN_ACTIONS

            elif self.ai_state == AIState.RUN_ACTIONS:
                next_step = self.doActions(cresp)
                if next_step is not None:
                    self.ai_state = AIState.PROCESSING
                

            elif self.ai_state == AIState.ANYTHING_ELSE:
                self.playVoice("Can I help with anything else?")
                self.ai_state = AIState.START

            elif self.ai_state == AIState.END:
                break

            time.sleep(0.05)
            self.turn += 1
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
