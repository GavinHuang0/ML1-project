"""Compatibility entry point; implementation lives in llm_debate.benchmark."""

import importlib
import sys

_impl = importlib.import_module("llm_debate.benchmark")

sys.modules[__name__] = _impl
