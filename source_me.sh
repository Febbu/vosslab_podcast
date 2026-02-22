set | grep -q '^BASH_VERSION=' || echo "use bash for your shell"
set | grep -q '^BASH_VERSION=' || exit 1

source ~/.bashrc

# Set Python environment optimizations
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Set repo-local Python import paths
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONPATH_PATHS=(
	"${REPO_ROOT}"
	"${REPO_ROOT}/pipeline"
	"${REPO_ROOT}/local-llm-wrapper"
)
for path in "${PYTHONPATH_PATHS[@]}"; do
	case ":${PYTHONPATH:-}:" in
		*":${path}:"*) ;;
		*)
			if [ -n "${PYTHONPATH:-}" ]; then
				export PYTHONPATH="${path}:${PYTHONPATH}"
			else
				export PYTHONPATH="${path}"
			fi
			;;
	esac
done
