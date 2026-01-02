# Asterisk AI Assistant

An AI assistant for your telephone line.

- FreePBX (Asterisk)
- Vosk STT
- Google TTS
- Gemini 3.0
- Green-API (WhatsApp)
- Home Assistant
- FastAPI
- langChain
- Redis

## Installation
1. Copy into /var/lib/asterisk/agi-bin/ai
2. Create a Custom Destination:  ai-entry,s,1
3. Add the following to your /etc/asterisk/extensions_custom.conf

`[ai-entry]
exten => s,1,NoOp(AI Entry Point)
 same => n,Progress()
 same => n,AGI(ai/ai_answer.py,${CALLERID(num)},${CALLERID(name)})
 same => n,Hangup()`


4. Reload your Dial Plans: asterisk -rx "dialplan reload"
5. Use your Custom Destination in an IVR or elsewhere.