import math
import os
import sys


#============================================
def add_local_llm_wrapper_to_path(script_file: str) -> None:
	"""
	Add local-llm-wrapper path to sys.path when present.
	"""
	script_dir = os.path.dirname(os.path.abspath(script_file))
	repo_root = os.path.dirname(script_dir)
	candidates = [
		os.path.join(repo_root, "local-llm-wrapper"),
		os.path.join(repo_root, "pipeline", "local-llm-wrapper"),
	]
	for wrapper_repo in candidates:
		if not os.path.isdir(wrapper_repo):
			continue
		if wrapper_repo not in sys.path:
			sys.path.insert(0, wrapper_repo)
		return


#============================================
def describe_llm_execution_path(transport_name: str, model_override: str) -> str:
	"""
	Describe configured LLM transport execution order.
	"""
	model_label = model_override or "auto"
	if transport_name == "ollama":
		return f"ollama(model={model_label})"
	if transport_name == "apple":
		return "apple(local foundation models)"
	if transport_name == "auto":
		return f"apple(local foundation models) -> ollama(model={model_label})"
	return transport_name


#============================================
def create_llm_client(
	script_file: str,
	transport_name: str,
	model_override: str,
	quiet: bool,
) -> object:
	"""
	Create local-llm-wrapper LLMClient for one pipeline script.
	"""
	add_local_llm_wrapper_to_path(script_file)
	import local_llm_wrapper.llm as llm

	model_choice = llm.choose_model(model_override or None)
	transports = []
	if transport_name == "ollama":
		transports.append(llm.OllamaTransport(model=model_choice))
	elif transport_name == "apple":
		transports.append(llm.AppleTransport())
	elif transport_name == "auto":
		transports.append(llm.AppleTransport())
		transports.append(llm.OllamaTransport(model=model_choice))
	else:
		raise RuntimeError(f"Unsupported llm transport: {transport_name}")
	return llm.LLMClient(transports=transports, quiet=quiet)


#============================================
def compute_incremental_target(item_count: int, final_target: int, minimum_target: int) -> int:
	"""
	Compute per-item target using max(minimum, ceil((2*final)/(N-1))).
	"""
	if item_count <= 1:
		return final_target
	raw_target = math.ceil((2 * final_target) / (item_count - 1))
	return max(minimum_target, raw_target)
