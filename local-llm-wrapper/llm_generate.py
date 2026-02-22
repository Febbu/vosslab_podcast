#!/usr/bin/env python3
"""
CLI helper for quick local_llm_wrapper prompts.
"""

from __future__ import annotations

# Standard Library
import sys
import argparse

# local repo modules
import local_llm_wrapper.llm_client
import local_llm_wrapper.llm_utils
import local_llm_wrapper.transports

#============================================


DEFAULT_PROMPT = "Say hello in one sentence."
DEFAULT_MAX_TOKENS = 80


#============================================


def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.

	Returns:
		Namespace: Parsed CLI arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Run a quick prompt against the local LLM wrapper."
	)
	parser.add_argument(
		"-p",
		"--prompt",
		dest="prompt",
		type=str,
		default=DEFAULT_PROMPT,
		help="Prompt text to send to the model.",
	)
	parser.add_argument(
		"-m",
		"--model",
		dest="model",
		type=str,
		default="",
		help="Model override (default: auto-select).",
	)
	parser.add_argument(
		"-t",
		"--max-tokens",
		dest="max_tokens",
		type=int,
		default=DEFAULT_MAX_TOKENS,
		help="Maximum tokens to generate.",
	)
	parser.add_argument(
		"-q",
		"--quiet",
		dest="quiet",
		action="store_true",
		help="Suppress LLM progress output.",
	)
	parser.add_argument(
		"-v",
		"--verbose",
		dest="quiet",
		action="store_false",
		help="Show LLM progress output.",
	)
	parser.set_defaults(quiet=True)
	args = parser.parse_args()
	return args


#============================================


def main() -> None:
	"""
	Run a local prompt through the Ollama transport.
	"""
	args = parse_args()
	model_override = args.model.strip()
	if model_override:
		selected_model = local_llm_wrapper.llm_utils.choose_model(model_override)
	else:
		selected_model = local_llm_wrapper.llm_utils.choose_model(None)
	transports = [
		local_llm_wrapper.transports.OllamaTransport(model=selected_model),
	]
	client = local_llm_wrapper.llm_client.LLMClient(
		transports=transports,
		quiet=args.quiet,
	)
	response = client.generate(args.prompt, max_tokens=args.max_tokens)
	sys.stdout.write(response)
	if not response.endswith("\n"):
		sys.stdout.write("\n")


if __name__ == "__main__":
	main()
