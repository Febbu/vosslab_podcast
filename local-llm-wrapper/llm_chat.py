#!/usr/bin/env python3
"""
Interactive chat CLI for local_llm_wrapper.
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


DEFAULT_MAX_TOKENS = 240
EXIT_WORDS = {"exit", "quit", "q"}


#============================================


def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.

	Returns:
		Namespace: Parsed CLI arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Interactive chat session using the local LLM wrapper."
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
		"-s",
		"--system",
		dest="system",
		type=str,
		default="",
		help="Optional system message to start the chat.",
	)
	parser.add_argument(
		"-t",
		"--max-tokens",
		dest="max_tokens",
		type=int,
		default=DEFAULT_MAX_TOKENS,
		help="Maximum tokens to generate per response.",
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


def _prompt_user() -> str:
	sys.stdout.write("You: ")
	sys.stdout.flush()
	line = sys.stdin.readline()
	if line == "":
		return ""
	return line.strip()


def main() -> None:
	"""
	Run an interactive chat loop.
	"""
	args = parse_args()
	model_override = args.model.strip()
	if model_override:
		selected_model = local_llm_wrapper.llm_utils.choose_model(model_override)
	else:
		selected_model = local_llm_wrapper.llm_utils.choose_model(None)
	client = local_llm_wrapper.llm_client.LLMClient(
		transports=[
			local_llm_wrapper.transports.OllamaTransport(model=selected_model),
		],
		quiet=args.quiet,
	)
	messages: list[dict[str, str]] = []
	system_message = args.system.strip()
	if system_message:
		messages.append({"role": "system", "content": system_message})
	sys.stdout.write("Chat ready. Type 'exit' to quit.\n")
	while True:
		user_text = _prompt_user()
		if user_text == "":
			sys.stdout.write("\n")
			break
		if user_text.lower() in EXIT_WORDS:
			break
		messages.append({"role": "user", "content": user_text})
		response = client.generate(messages=messages, max_tokens=args.max_tokens)
		messages.append({"role": "assistant", "content": response})
		sys.stdout.write(f"Assistant: {response}")
		if not response.endswith("\n"):
			sys.stdout.write("\n")


if __name__ == "__main__":
	main()
