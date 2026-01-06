# Asterisk AI Assistant

An AI assistant for your telephone line.

Technologies used:
- FreePBX (Asterisk 22.6.0)
- FastAPI
- Vosk STT
- Google TTS
- Gemini 3.0
- langChain
- Redis
- Green-API (WhatsApp)
- Home Assistant

The AI will decide on what the caller wants and take one of the following actions:
- Forward call to Voicemail
- Forward call to Mobile Phone
- Take a WhatsApp Message and send to a number
- Take and schedule a meeting appointment
- Take a message and send to email
- Respond to a greeting
- Toggle the Light Switch via Home Assistant
- Respond to any other question

## Meeting Appointments:
The AI will request a date, time, meeting type (online, physical), email address and physical address through a series of questions. Once all the data is gathered, the final details are read back to the caller.

## Installation
1. Copy into /var/lib/asterisk/agi-bin/ai
2. Create a Custom Destination:  ai-entry,s,1
3. Add the following to your /etc/asterisk/extensions_custom.conf

```
[ai-entry]
  exten => s,1,NoOp(AI Entry Point)
    same => n,Progress()
    same => n,AGI(ai/ai_answer.py,${CALLERID(num)},${CALLERID(name)})
    same => n,Hangup()
```
4. Reload your Dial Plans: asterisk -rx "dialplan reload"
5. Use your Custom Destination in an IVR or elsewhere.


## Next Steps
Real-time chat (audio streaming)
