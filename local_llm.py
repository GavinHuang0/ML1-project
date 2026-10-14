"""Compatibility entry point; implementation lives in llm_debate.local_llm."""

import importlib
import sys

_impl = importlib.import_module("llm_debate.local_llm")

sys.modules[__name__] = _impl
