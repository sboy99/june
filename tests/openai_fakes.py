"""Fake OpenAI-compatible endpoint shared by unit and contract tests."""

import json

import httpx2

PLANTED_KEY = "sk-planted-secret-1234567890"


def completion(message=None, finish="stop", usage=None):
    body = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": message or {"role": "assistant", "content": "hi"},
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return body


class Server:
    """A fake OpenAI endpoint: replays canned responses and records requests."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        status, body = item if isinstance(item, tuple) else (200, item)
        return httpx2.Response(status, json=body)

    @property
    def last_body(self):
        return json.loads(self.requests[-1].content)
