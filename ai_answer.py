#!/usr/bin/env python3
from asterisk.agi import AGI
import sys
from vosk import Model, KaldiRecognizer
import wave
import json
from gtts import gTTS
from pydub import AudioSegment
import requests
from models import ChatRequest,ChatResponse
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
    ##===================================================
    def getCallerID(self):
        self.unique_id = self.agi.get_variable("UNIQUEID")
        self.call_id = (
            self.agi.argv[1]
            if len(self.agi.argv) > 1
            else self.agi.get_variable("CALLERID(num)")
        )
        self.call_name = (
            self.agi.argv[2]
            if len(self.agi.argv) > 2
            else self.agi.get_variable("CALLERID(name)")
        )
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
    def queryAI(self,text:str) -> ChatResponse:
        payload = {
            "unique_id": self.unique_id,
            "call_id": self.call_id,
            "call_name": self.call_name,
            "text": text
        }

        resp = requests.post("http://127.0.0.1:8000/chat",  json=payload, timeout=50)
        jval = resp.json()
        cresp = ChatResponse()
        cresp.reply = jval["reply"]
        cresp.action = jval["action"]
        return cresp
    ##===================================================
    def doActions(self,cresp:ChatResponse) -> bool:
        if cresp.action == None or cresp.action == "":
            return True
        if cresp.action == "hangup":
            self.agi.hangup()
            self.agi.stream_file("custom/ai_bye")
            return False
        elif cresp.action == "voicemail":
            mailbox = "1000"
            context = "default"
            self.agi.execute('Voicemail',f"{mailbox}@{context}")
            vmstatus = self.agi.get_variable("VMSTATUS")
            return False
            #record_voicemail()
        return True
    ##===================================================
    def tts(self,text:str) -> str:
        tts_file = f"/tmp/ai_reply_{self.turn}.mp3"
        gTTS(text, lang="en").save(tts_file)
        return tts_file
    ##===================================================
    def run(self):
        self.agi.verbose(f"Turn {self.turn + 1}", 3)
        self.agi.stream_file("beep")

        filename = self.recordFile(turn)
        self.convertAudioIn(filename)
        text = self.stt(filename)
        cresp = self.query_ai(text)
        carry_on = self.doActions(cresp)
        if carry_on:
            tts_file = self.tts(cresp.reply)
            wav_file = self.convertAudioOut(tts_file)
            self.agi.stream_file(wav_file)
        self.turn += 1
    ##===================================================
    def newCall(self):
        self.turn = 0
        self.answerCall()
        while self.turn < self.max_turns:
            self.run()
    ##===================================================

ai = AIAnswer()
ai.newCall()
##===================================================


# agi = AGI()
# agi.verbose("AI AGI started", 3)

# model = Model("/opt/vosk-model/vosk-model-small-en-us-0.15")
# MAX_TURNS = 3
# turn = 0
# agi.answer()

# #state = agi.get_variable("CHANNEL(state)")
# #agi.verbose(f"Channel state: {state}", 3)

# agi.stream_file("custom/ai_start")

# while turn < MAX_TURNS:
#     agi.verbose(f"Turn {turn+1}", 3)
#     # Record caller
#     agi.stream_file("beep")
#     try:
#         filename = recordFile(turn)
#         # Convert WAV to PCM 16k mono if needed
#         sound = AudioSegment.from_file(filename)
#         sound = sound.set_channels(1).set_frame_rate(16000)
#         sound.export(filename, format="wav")
#         # STT: Vosk
#         wf = wave.open(filename, "rb")
#         rec = KaldiRecognizer(model, wf.getframerate())
#         text = ""
#         while True:
#             data = wf.readframes(4000)
#             if len(data) == 0:
#                 break
#             if rec.AcceptWaveform(data):
#                 res = json.loads(rec.Result())
#                 text += res.get("text","") + " "
#         # Get final chunk
#         res = json.loads(rec.FinalResult())
#         text += res.get("text","")

#         agi.verbose(f"Caller said: {text}", 3)

#         if text.strip() == "":
#             break

#         cresp = query_ai(call_id,text)
#         if action == "hangup":
#             agi.hangup()
#             agi.stream_file("custom/ai_bye")
#             break
#         elif action == "voicemail":
#             pass
#             #record_voicemail()

#         tts_file = f"/tmp/ai_reply_{turn}.mp3"
#         gTTS(reply, lang="en").save(tts_file)

#         # Convert MP3 to WAV Asterisk can play
#         wav_file = f"/tmp/ai_reply_{turn}.wav"
#         AudioSegment.from_mp3(tts_file).export(wav_file, format="wav",parameters=["-ar", "8000","-ac","1"])

#         # Play reply
#         agi.stream_file(wav_file.replace(".wav",""))

#         turn += 1
#     except asterisk.agi.AGIError as e:
#         agi.verbose(f"An Error Occurred:{e}",3)
#     except:
#         agi.verbosr(f"An Other Error Occurred",3)

# #agi.stream_file("custom/ai_bye")
# agi.verbose("AGI finished", 3)
