import requests
from dotenv import dotenv_values
##===================================================
class HomeAssistant:
    def __init__(self, *args, **kwargs):
        config = dotenv_values(".env")
        self.HA_URL = config['HA_URL']
        self.HA_TOKEN = config['HA_TOKEN']
        self.headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        }
    ##===================================================
    def toggle_hallway_light(self,state: str):
        service = "turn_on" if state == "on" else "turn_off"
        data = {
            "entity_id": "light.hall_light"
        }
        requests.post(
            f"{HA_URL}/api/services/light/{service}",
            headers=self.headers,
            json=data,
            timeout=5
        ).raise_for_status()
    ##===================================================
##===================================================    