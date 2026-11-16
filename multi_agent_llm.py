"""Isolated transport settings for the versioned multi-agent experiment."""

from local_llm import OllamaClient as LocalClient, validate_model_tag
from multi_agent_protocol import FROZEN_PROTOCOL


class MultiAgentClient(LocalClient):
    """Use the existing local-only transport without changing baseline calls."""

    def chat(self, model, messages, *, seed=0, temperature=0.7, max_tokens=1024):
        model = validate_model_tag(model)
        if (type(seed) is not int or not isinstance(messages, list) or not messages
                or any(not isinstance(m, dict) or m.get("role") not in {"system", "user", "assistant"}
                       or not isinstance(m.get("content"), str) for m in messages)):
            raise ValueError("Invalid multi-agent messages or integer seed")
        if (type(max_tokens) is not int or max_tokens != FROZEN_PROTOCOL["max_tokens"]
                or type(temperature) not in (int, float) or temperature != FROZEN_PROTOCOL["temperature"]):
            raise ValueError("Generation settings must match the frozen multi-agent protocol")
        response = self._request("/api/chat", {
            "model": model, "messages": messages, "stream": False, "format": "json",
            "keep_alive": FROZEN_PROTOCOL["keep_alive"],
            "options": {"seed": seed, "temperature": temperature, "num_predict": max_tokens,
                        "num_ctx": FROZEN_PROTOCOL["context_tokens"]},
        })
        # The runner journals the returned object before validating its wrapper.
        return response
