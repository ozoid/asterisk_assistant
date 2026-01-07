import requests
import json
from dotenv import dotenv_values
from pathlib import Path
##===================================================
class HomeAssistant:
    def __init__(self, *args, **kwargs):
        BASE_DIR = Path(__file__).resolve().parent
        config = dotenv_values(BASE_DIR / ".env")
        self.HA_URL = config['HA_URL']
        self.HA_TOKEN = config['HA_TOKEN']
        self.headers = {
            "Authorization": f"Bearer {self.HA_TOKEN}",
            "Content-Type": "application/json",
        }
    ##===================================================
    def toggle_hallway_light(self):
        service = "toggle"
        data = {
            "entity_id": "light.hall_light"
        }
        requests.post(
            f"{self.HA_URL}/api/services/light/{service}",
            headers=self.headers,
            data=json.dumps(data),
            timeout=15
        ).raise_for_status()
        
    ##===================================================
##===================================================    