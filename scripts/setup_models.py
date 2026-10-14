"""Download the experiment's models to this computer, then optionally test them."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from llm_debate.local_llm import BASE_URL, OllamaClient, OllamaError, parse_prediction, validate_model_tag


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "models.json"


def load_models(path=DEFAULT_CONFIG):
    with Path(path).open(encoding="utf-8") as handle:
        models = json.load(handle)["models"]
    return validate_models(models)


def validate_models(models):
    if not isinstance(models, list) or not models:
        raise ValueError("models must be a nonempty list of valid model tags")
    return list(dict.fromkeys(validate_model_tag(model) for model in models))


def smoke(client, model):
    response = client.chat(model, [{
        "role": "user",
        "content": 'What is 2 + 2? Return JSON with string fields "final_answer" and "explanation".',
    }], seed=0, temperature=0, max_tokens=128)
    prediction = parse_prediction(response)
    print(f"{model}: {json.dumps(prediction, ensure_ascii=False)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", help="Override config/models.json model tags")
    parser.add_argument("--check", action="store_true", help="Check existing models without downloading")
    parser.add_argument("--smoke", action="store_true", help="Ask each installed model a small test question")
    args = parser.parse_args(argv)
    try:
        models = validate_models(args.models) if args.models is not None else load_models()
        if not args.check:
            executable = shutil.which("ollama")
            if not executable:
                raise OllamaError(
                    "Ollama is not installed or is absent from PATH. Install it for your OS "
                    "from https://ollama.com/download, then open a new terminal and retry."
                )
        client = OllamaClient()
        status = client.health()
        print(f"Local Ollama {status['version']} at {BASE_URL}")
        if not args.check:
            env = dict(os.environ, OLLAMA_HOST=BASE_URL)
            for model in models:
                print(f"Downloading {model} to this computer...", flush=True)
                subprocess.run([executable, "pull", model], check=True, env=env)
            status = client.health()
        installed = {item["name"] for item in status["models"]}
        missing = [model for model in models if model not in installed
                   and (":" in model.rsplit("/", 1)[-1] or model + ":latest" not in installed)]
        if missing:
            raise OllamaError("Missing models: " + ", ".join(missing)
                              + ". Run python setup_models.py to download the defaults, "
                              "or ollama pull <model> for each custom tag.")
        print("All requested models are installed locally: " + ", ".join(models))
        if args.smoke:
            for model in models:
                smoke(client, model)
        return 0
    except (OllamaError, OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Setup interrupted; rerun to resume model downloads.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
