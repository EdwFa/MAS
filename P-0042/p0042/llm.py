"""Модель — функция llm(prompt | messages) -> str.

ScriptedLLM — заглушка для тестов: отвечает заранее заданными строками.
LocalLLM — любой локальный сервер с OpenAI-совместимым API (Ollama, vLLM, llama.cpp).
Данные пациента не уходят за пределы контура (152-ФЗ): адрес по умолчанию — localhost.
"""
import json
import os
import re
import urllib.request

THINK = re.compile(r"<think>.*?</think>", re.S)


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self.replies:
            raise RuntimeError("ScriptedLLM: ответы закончились")
        r = self.replies.pop(0)
        return r(prompt) if callable(r) else r


class LocalLLM:
    def __init__(self, model=None, base_url=None, temperature=0.0, timeout=120):
        self.model = model or os.environ.get("P0042_MODEL", "qwen3:8b")
        self.base_url = (base_url or os.environ.get("P0042_BASE_URL", "http://localhost:11434/v1")).rstrip("/")
        if not self.base_url.startswith(("http://localhost", "http://127.0.0.1")):
            raise ValueError("модель должна быть локальной: данные пациента не покидают контур")
        self.temperature, self.timeout = temperature, timeout

    def __call__(self, prompt):
        messages = prompt if isinstance(prompt, list) else [{"role": "user", "content": prompt}]
        body = json.dumps({"model": self.model, "messages": messages,
                           "temperature": self.temperature}).encode()
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            content = json.loads(resp.read())["choices"][0]["message"]["content"] or ""
        return THINK.sub("", content).strip()      # рассуждающие модели (qwen3, deepseek-r1) пишут <think>…</think>
