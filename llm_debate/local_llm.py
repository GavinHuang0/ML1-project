"""Small standard-library client for the Ollama service on your own computer."""

import json
import math
import socket
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


BASE_URL = "http://127.0.0.1:11434"


class OllamaError(RuntimeError):
    """An actionable runtime, model, or response error."""


def validate_model_tag(model):
    """Accept model tags intended for downloaded local weights."""
    if (not isinstance(model, str) or not model or model.startswith("-")
            or any(character.isspace() for character in model)):
        raise ValueError("model must be a nonempty valid model tag")
    if model.lower().endswith((":cloud", "-cloud")):
        raise ValueError("Cloud model tags are unsupported; choose a downloaded local model.")
    return model


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _reject_constant(value):
    raise ValueError(f"Nonfinite JSON value: {value}")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Nonfinite JSON number: {value}")
    return number


def _decode_json(text):
    return json.loads(text, parse_constant=_reject_constant, parse_float=_finite_float)


class OllamaClient:
    def __init__(self, timeout=180):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive, finite number")
        self.timeout = timeout
        # Local requests must not pass through an inherited HTTP proxy.
        self._opener = build_opener(ProxyHandler({}), _NoRedirects())

    def _request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        request = Request(BASE_URL + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(request, timeout=self.timeout) as reply:
                response = _decode_json(reply.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404 and payload and "model" in payload:
                detail += f"\nInstall this model with: ollama pull {payload['model']}"
            raise OllamaError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, socket.timeout, ConnectionError) as exc:
            raise OllamaError(
                "Cannot reach local Ollama at " + BASE_URL
                + ". Install from https://ollama.com/download, open Ollama or run "
                "'ollama serve', then retry. Slow CPU runs may need a longer timeout."
            ) from exc
        except (UnicodeDecodeError, ValueError) as exc:
            raise OllamaError(f"Ollama returned invalid JSON: {exc}") from exc
        if not isinstance(response, dict):
            raise OllamaError("Ollama response must be a JSON object")
        if response.get("error"):
            raise OllamaError(f"Ollama error: {response['error']}")
        return response

    def health(self):
        """Return the service version and installed model metadata."""
        version = self._request("/api/version")
        tags = self._request("/api/tags")
        if not isinstance(version.get("version"), str) or not isinstance(tags.get("models"), list):
            raise OllamaError("Ollama returned invalid version or model metadata")
        if any(not isinstance(item, dict) or not isinstance(item.get("name"), str)
               for item in tags["models"]):
            raise OllamaError("Ollama model metadata is missing model names")
        return {"version": version["version"], "models": tags["models"]}

    def chat(self, model, messages, *, seed=0, temperature=0.7, max_tokens=256):
        """Generate one JSON answer, unloading the model after the request."""
        model = validate_model_tag(model)
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a nonempty list")
        for message in messages:
            if (not isinstance(message, dict)
                    or message.get("role") not in {"system", "user", "assistant"}
                    or not isinstance(message.get("content"), str)):
                raise ValueError("Each message needs a valid role and string content")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        if not math.isfinite(temperature) or temperature < 0:
            raise ValueError("temperature must be finite and nonnegative")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        response = self._request("/api/chat", {
            "model": model, "messages": messages, "stream": False,
            "format": "json", "keep_alive": 0,
            "options": {"seed": seed, "temperature": temperature,
                        "num_predict": max_tokens, "num_ctx": 4096},
        })
        message = response.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise OllamaError("Ollama chat response is missing message.content")
        return response


def parse_prediction(response):
    """Read the required final_answer and explanation from a chat response."""
    try:
        content = response["message"]["content"]
        prediction = _decode_json(content)
    except (KeyError, TypeError, ValueError) as exc:
        raise OllamaError(f"Model did not return valid prediction JSON: {exc}") from exc
    if not isinstance(prediction, dict):
        raise OllamaError("Prediction must be a JSON object")
    if not isinstance(prediction.get("final_answer"), str) or not prediction["final_answer"].strip():
        raise OllamaError("Prediction needs a nonempty string final_answer")
    if not isinstance(prediction.get("explanation"), str):
        raise OllamaError("Prediction needs a string explanation")
    return prediction
