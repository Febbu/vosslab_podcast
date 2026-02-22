#!/usr/bin/env python3
"""
Demo script for XML tag parsing with local_llm_wrapper.
"""

from __future__ import annotations

# Standard Library
import sys
import argparse

# local repo modules
import local_llm_wrapper.llm_client
import local_llm_wrapper.llm_parsers
import local_llm_wrapper.llm_utils
import local_llm_wrapper.transports

#============================================


DEFAULT_QUESTION = "Say hello in one sentence."
DEFAULT_MAX_TOKENS = 120


#============================================


def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.

	Returns:
		Namespace: Parsed CLI arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Demo: request XML tags and extract a single tag from the response."
	)
	parser.add_argument(
		"-p",
		"--prompt",
		dest="prompt",
		type=str,
		default=DEFAULT_QUESTION,
		help="Prompt text to answer.",
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


def build_prompt(question: str) -> str:
	lines = [
		"Answer the question in one sentence.",
		"Return only the tag shown below.",
		"<answer>...</answer>",
		f"Question: {question}",
	]
	return "\n".join(lines)


def main() -> None:
	"""
	Run the XML tag demo prompt and extract <answer>.
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
	prompt = build_prompt(args.prompt)
	response = client.generate(prompt, max_tokens=args.max_tokens)
	answer = local_llm_wrapper.llm_parsers.parse_tag_response(response, "answer")
	sys.stdout.write(answer)
	if not answer.endswith("\n"):
		sys.stdout.write("\n")


if __name__ == "__main__":
	main()
