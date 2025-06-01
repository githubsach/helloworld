import os
import random
import json
from locust import HttpUser, task, between
from dotenv import load_dotenv

load_dotenv()

PROMPT_FILE_PATH = os.getenv("PROMPT_FILE_PATH", "prompts.txt")
VLLM_PROXY_HOST = os.getenv("VLLM_PROXY_HOST", "http://localhost:8000")

# Read prompt list
with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
    prompts = [line.strip() for line in f if line.strip()]

class PromptUser(HttpUser):
    wait_time = between(1, 3)  # seconds between requests

    @task
    def send_prompt(self):
        prompt = random.choice(prompts)
        version = None  # Optional: could be 'v1', 'v2', etc.
        payload = {"prompt": prompt}
        if version:
            payload["version"] = version
        self.client.post(
            "/generate",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
