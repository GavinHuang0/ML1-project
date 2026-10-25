"""Offline client and installer tests; no installed Ollama or model is needed."""

from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError

from experiment_config import MAX_TOKENS, MODEL
from local_llm import OllamaClient, OllamaError, parse_prediction
import setup_models


class FakeOllama(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond()

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.requests.append((self.path, json.loads(body)))
        self.respond()

    def respond(self):
        status, body = self.server.responses.get(self.path, (404, '{"error":"missing"}'))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 302:
            self.send_header("Location", "/api/version")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):
        pass


class LocalClientTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        self.server.responses = {
            "/api/version": (200, '{"version":"0.test"}'),
            "/api/tags": (200, json.dumps({"models": [{"name": MODEL, "digest": "abc"}]})),
            "/api/chat": (200, json.dumps({
                "message": {"role": "assistant", "content": json.dumps({
                    "final_answer": "4", "explanation": "Addition."})},
                "eval_count": 14, "done": True,
            })),
        }
        self.server.requests = []
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.endpoint = patch("local_llm.BASE_URL", f"http://127.0.0.1:{self.server.server_port}")
        self.endpoint.start()
        self.client = OllamaClient(timeout=1)

    def tearDown(self):
        self.endpoint.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_health_returns_version_and_model_metadata(self):
        self.assertEqual(self.client.health(), {
            "version": "0.test", "models": [{"name": MODEL, "digest": "abc"}],
        })

    def test_chat_preserves_metadata_and_serializes_local_options(self):
        messages = [{"role": "user", "content": "2 + 2?"}]
        response = self.client.chat(MODEL, messages, seed=42, temperature=0.2, max_tokens=MAX_TOKENS)
        self.assertEqual(response["eval_count"], 14)
        self.assertEqual(parse_prediction(response)["final_answer"], "4")
        self.assertEqual(self.server.requests, [("/api/chat", {
            "model": MODEL, "messages": messages, "stream": False,
            "format": "json", "keep_alive": 0,
            "options": {"seed": 42, "temperature": 0.2, "num_predict": MAX_TOKENS, "num_ctx": 4096},
        })])

    def test_default_chat_uses_fixed_1024_token_cap(self):
        self.client.chat(MODEL, [{"role": "user", "content": "Hello"}])
        self.assertEqual(self.server.requests[0][1]["options"]["num_predict"], 1024)

    def test_other_models_and_token_caps_are_rejected_before_network(self):
        messages = [{"role": "user", "content": "Hello"}]
        for model in ["qwen2.5:3b", "llama3.2", "llama3.2:1b", "llama3.2:latest"]:
            with self.subTest(model=model), self.assertRaisesRegex(ValueError, MODEL):
                self.client.chat(model, messages)
        for tokens in [128, 256, 512, 2048, True, 1024.0, None]:
            with self.subTest(max_tokens=tokens), self.assertRaisesRegex(ValueError, "1024"):
                self.client.chat(MODEL, messages, max_tokens=tokens)
        self.assertEqual(self.server.requests, [])

    def test_missing_model_includes_install_command(self):
        self.server.responses["/api/chat"] = (404, '{"error":"model not found"}')
        with self.assertRaisesRegex(OllamaError, "ollama pull " + MODEL):
            self.client.chat(MODEL, [{"role": "user", "content": "Hello"}])

    def test_invalid_server_responses_fail(self):
        for body in ["not-json", "[]", '{"error":"failed"}', '{"message":{}}',
                     '{"message":{"content":"{}"},"duration":NaN}',
                     '{"message":{"content":"{}"},"duration":1e999}']:
            with self.subTest(body=body):
                self.server.responses["/api/chat"] = (200, body)
                with self.assertRaises(OllamaError):
                    self.client.chat(MODEL, [{"role": "user", "content": "Hello"}])

    def test_absent_runtime_error_is_actionable(self):
        with patch.object(self.client._opener, "open", side_effect=URLError("connection refused")):
            with self.assertRaisesRegex(OllamaError, "ollama serve"):
                self.client.health()

    def test_redirect_is_rejected_instead_of_followed(self):
        self.server.responses["/api/chat"] = (302, "redirect")
        with self.assertRaisesRegex(OllamaError, "HTTP 302"):
            self.client.chat(MODEL, [{"role": "user", "content": "Hello"}])

    def test_rejects_nonfinite_request_before_network(self):
        with self.assertRaises(ValueError):
            self.client.chat(MODEL, [{"role": "user", "content": "Hello"}], temperature=float("nan"))
        self.assertEqual(self.server.requests, [])

    def test_cloud_tags_are_rejected_before_network(self):
        for model in ["gpt-oss:120b-cloud", "glm-5:cloud", "model:Cloud", "model:3b-CLOUD"]:
            with self.subTest(model=model), self.assertRaisesRegex(ValueError, "downloaded local model"):
                self.client.chat(model, [{"role": "user", "content": "Hello"}])
        self.assertEqual(self.server.requests, [])


class PredictionTests(unittest.TestCase):
    def test_rejects_unstructured_missing_or_nonfinite_answers(self):
        for content in ["```json\n{}\n```", "[]", "{}",
                        '{"final_answer":4,"explanation":"addition"}',
                        '{"final_answer":" ","explanation":""}',
                        '{"final_answer":"4","explanation":null}',
                        '{"final_answer":"4","explanation":"ok","score":NaN}',
                        '{"final_answer":"4","explanation":"ok","score":1e999}']:
            with self.subTest(content=content), self.assertRaises(OllamaError):
                parse_prediction({"message": {"content": content}})


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.error = io.StringIO()
        self.stdout = redirect_stdout(self.output)
        self.stderr = redirect_stderr(self.error)
        self.stdout.__enter__()
        self.stderr.__enter__()

    def tearDown(self):
        self.stderr.__exit__(None, None, None)
        self.stdout.__exit__(None, None, None)

    def test_load_models_deduplicates_and_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "models.json"
            config.write_text(json.dumps({"models": [MODEL, MODEL]}), encoding="utf-8")
            self.assertEqual(setup_models.load_models(config), [MODEL])
        self.assertEqual(setup_models.load_models(), [MODEL])
        for models in [[], MODEL, [None], [""], ["-x"], [" a"], ["qwen2.5:3b"], [MODEL, "llama3.2:1b"]]:
            with self.subTest(models=models), self.assertRaises(ValueError):
                setup_models.validate_models(models)

    def test_missing_binary_gives_official_install_url(self):
        with patch("setup_models.shutil.which", return_value=None):
            self.assertEqual(setup_models.main([]), 1)
        self.assertIn("https://ollama.com/download", self.error.getvalue())

    def test_other_models_are_rejected_before_runtime_or_download(self):
        with patch("setup_models.OllamaClient") as client, patch("setup_models.subprocess.run") as run:
            self.assertEqual(setup_models.main(["--models", "qwen2.5:3b"]), 1)
            self.assertEqual(setup_models.main(["--models", MODEL, "llama3.2:1b"]), 1)
            client.assert_not_called()
            run.assert_not_called()
        self.assertIn(MODEL, self.error.getvalue())

    def test_cloud_tags_cannot_be_pulled(self):
        with patch("setup_models.subprocess.run") as run:
            self.assertEqual(setup_models.main(["--models", "model:3b-cloud"]), 1)
            run.assert_not_called()
        self.assertIn("choose a downloaded local model", self.error.getvalue())

    def test_check_only_does_not_pull(self):
        with patch("setup_models.OllamaClient") as client, patch("setup_models.subprocess.run") as run:
            client.return_value.health.return_value = {
                "version": "test", "models": [{"name": MODEL}],
            }
            self.assertEqual(setup_models.main(["--check"]), 0)
            run.assert_not_called()

    def test_default_and_duplicate_models_pull_only_llama_with_local_host(self):
        for arguments in [[], ["--models", MODEL, MODEL]]:
            with self.subTest(arguments=arguments), \
                    patch("setup_models.OllamaClient") as client, \
                    patch("setup_models.shutil.which", return_value="/test/ollama"), \
                    patch("setup_models.subprocess.run") as run:
                client.return_value.health.return_value = {
                    "version": "test", "models": [{"name": MODEL}],
                }
                self.assertEqual(setup_models.main(arguments), 0)
                run.assert_called_once()
                call = run.call_args
                self.assertEqual(call.args[0], ["/test/ollama", "pull", MODEL])
                self.assertTrue(call.kwargs["check"])
                self.assertEqual(call.kwargs["env"]["OLLAMA_HOST"], "http://127.0.0.1:11434")

    def test_smoke_accepts_structured_response_without_checking_accuracy(self):
        with patch("setup_models.OllamaClient") as client:
            client.return_value.health.return_value = {
                "version": "test", "models": [{"name": MODEL}],
            }
            client.return_value.chat.return_value = {
                "message": {"content": '{"final_answer":"five","explanation":"test"}'},
            }
            self.assertEqual(setup_models.main(["--check", "--smoke"]), 0)
            self.assertEqual(client.return_value.chat.call_args.args[0], MODEL)
            self.assertEqual(client.return_value.chat.call_args.kwargs["max_tokens"], 1024)
        self.assertIn("five", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
