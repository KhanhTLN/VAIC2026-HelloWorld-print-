from __future__ import annotations

import json
import re
from collections.abc import Generator

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"


def _build_messages(system_prompt: str, messages: list[dict[str, str]] | None) -> list[dict[str, str]]:
    payload_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in messages or []:
        if "role" in msg and "content" in msg:
            payload_messages.append({"role": msg["role"], "content": msg["content"]})
    return payload_messages


def call_llm_json(system_prompt: str, messages: list[dict[str, str]], timeout: int = 30) -> dict:
    payload = {
        "model": MODEL_NAME,
        "messages": _build_messages(system_prompt, messages),
        "stream": False,
        "options": {"temperature": 0.0, "top_p": 0.9},
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    raw_content = response.json().get("message", {}).get("content", "").strip()

    json_block = raw_content
    if "```" in raw_content:
        json_block = raw_content.split("```")[-2]
    json_block = json_block.strip()
    match = re.search(r"\{.*\}", json_block, re.DOTALL)
    if match:
        json_block = match.group(0)
    return json.loads(json_block)


def call_llm_stream(system_prompt: str, messages: list[dict[str, str]]) -> Generator[str, None, None]:
    payload = {
        "model": MODEL_NAME,
        "messages": _build_messages(system_prompt, messages),
        "stream": True,
        "options": {"temperature": 0.15, "top_p": 0.9},
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=90, stream=True)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                chunk = json.loads(line.decode("utf-8"))
                raw_content = chunk.get("message", {}).get("content", "")
                cleaned_content = re.sub(r"[\u4e00-\u9fff]", "", raw_content)
                yield cleaned_content
    except Exception as exc:
        yield f"Lỗi kết nối bộ não AI Local (Ollama): {str(exc)}"
