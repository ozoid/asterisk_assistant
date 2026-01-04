import requests
from dotenv import dotenv_values
##===================================================
class HomeAssistant:
    def __init__(self, *args, **kwargs):
        config = dotenv_values(".env")
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
            json=data,
            timeout=5
        ).raise_for_status()
    ##===================================================
##===================================================    