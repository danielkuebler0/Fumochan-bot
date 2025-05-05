import requests
from typing import List, Optional
import configparser
import time

def load_config(path = "config.ini") -> str:
        config = configparser.ConfigParser()
        config.read(path)
        return config["STRAWPOLL"]["token"]

class StrawpollAPI:
    def __init__(self, base_url="https://api.strawpoll.com/v3"):
        self.base_url = base_url
        self.api_key = load_config()
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key
            }
    

    def create_poll(self, title:str, options: List[str], duration: int) -> dict:
        if len(options) < 2:
            raise ValueError("Input at least 2 options.")
        
        current_unix = int(time.time())
        deadline = current_unix + duration*60

        payload = {
            "title": title,
            "poll_options": [{"value": opt} for opt in options],
            "poll_config": {"is_multiple_choice": True,
                            "deadline_at": deadline
                            }
        }

        response = requests.post(f"{self.base_url}/polls", headers = self.headers, json = payload)

        if response.status_code == 201:
            return response.json()
        else:
            raise Exception(f"API error {response.status_code}: {response.text}")
        
    def get_poll_url(self, poll_data: dict) -> str:
         return poll_data.get("url", "No URL found")
