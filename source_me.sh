set | grep -q '^BASH_VERSION=' || echo "use bash for your shell"
set | grep -q '^BASH_VERSION=' || exit 1

# Only source ~/.bashrc if it has not already been loaded in this shell.
if [[ -z "${BASHRC_COMMON_LOADED:-}" ]]; then
	source "$HOME/.bashrc"
fi

# Set Python environment optimizations
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Set repo-local Python import paths
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Add packages to PYTHONPATH
unset PYTHONPATH
export PYTHONPATH="${REPO_ROOT}/pipeline:${REPO_ROOT}/local-llm-wrapper"

echo "Environment configured:"
echo "  REPO_ROOT=${REPO_ROOT}"
echo "  PYTHONPATH=${PYTHONPATH}"
echo ""
echo "Agents run with :"
echo "  source source_me.sh && python3 script.py"
echo "  source source_me.sh && pytest tests/"
