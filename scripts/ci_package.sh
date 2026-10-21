#!/usr/bin/env bash
set -euo pipefail
# Candidate metadata must describe the tool that actually performs the build.
case "$(uv --version)" in
  "uv 0.13.4"|"uv 0.13.4 "*) ;;
  *) echo "Candidate build requires uv 0.13.4" >&2; exit 1 ;;
esac
root="$(pwd)"
candidate="$RUNNER_TEMP/rewind-candidate"
runtime="$RUNNER_TEMP/rewind-runtime"
# A preexisting output must never be silently mixed into this candidate.
mkdir "$candidate"
uv build --offline --no-sources --no-build-isolation --no-create-gitignore --out-dir "$candidate"
python scripts/ci_artifacts.py "$candidate"
uv export --frozen --no-default-groups --no-emit-project --format requirements.txt --output-file "$RUNNER_TEMP/runtime-requirements.txt"
uv venv --no-project --no-python-downloads "$runtime"
uv pip install --python "$runtime/bin/python" --require-hashes --no-deps --only-binary :all: -r "$RUNNER_TEMP/runtime-requirements.txt"
uv pip install --python "$runtime/bin/python" --no-deps "$candidate/agent_rewind-0.1.0-py3-none-any.whl"
cd "$RUNNER_TEMP"
PYTHONPATH='' "$runtime/bin/python" -I "$root/scripts/ci_smoke.py"
PYTHONPATH='' "$runtime/bin/rewind" --help
cd "$root"
python scripts/ci_artifacts.py "$candidate" --commit "$GITHUB_SHA"
