import os
from dotenv import dotenv_values
import requests
import json
##===================================================
class WhatsApp:
    def __init__(self, *args, **kwargs):
        config = dotenv_values(".env")
        watoken = config['WA_TOKEN']
        wainstance = config['WA_INSTANCE']
        self.stevewa = config['WA_MOBILE']
        self.WHATSAPP_URL = f"https://7107.api.green-api.com/waInstance{wainstance}/sendMessage/{watoken}" 
        self.headers = {
            "Content-Type": "application/json",
        }
    ##===================================================
    def post_whatsApp(self,message):
        wajson = { 
            "chatId": self.stevewa,
            "message": message 
        }
        requests.post(
            self.WHATSAPP_URL, 
            data = json.dumps(wajson),
            headers=self.headers,
            timeout=5
        ).raise_for_status()
        
    ##===================================================
##===================================================