set | grep -q '^BASH_VERSION=' || echo "use bash for your shell"
set | grep -q '^BASH_VERSION=' || exit 1

source ~/.bashrc

# Set Python environment optimizations
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Set repo-local Python import paths
REPO_ROOT="$(git rev-parse --show-toplevel)"

export PYTHONPATH="${REPO_ROOT}/pipeline:${REPO_ROOT}/local-llm-wrapper"
