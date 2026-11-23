#!/usr/bin/env bash
set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${BLUE}==>${NC} $1"; }
ok()    { echo -e "${GREEN} ok ${NC} $1"; }
warn()  { echo -e "${YELLOW}warn${NC} $1"; }
fail()  { echo -e "${RED}fail${NC} $1"; exit 1; }

info "Checking Python"
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 was not found. Install it first:"
    echo "  macOS:         brew install python@3.12"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "  RHEL/Fedora:   sudo dnf install python3"
    fail "python3 missing"
fi

PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 10) else 0)')
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$PY_OK" != "1" ]; then
    echo "Python 3.10 or newer is required. Found $PY_VER."
    echo "  macOS:         brew install python@3.12"
    echo "  Ubuntu/Debian: sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12 python3.12-venv"
    fail "python $PY_VER too old"
fi
ok "Python $PY_VER"

info "Checking Chrome (required for Selenium)"
if command -v google-chrome >/dev/null 2>&1; then
    ok "Chrome found (google-chrome)"
elif command -v chromium >/dev/null 2>&1; then
    ok "Chromium found"
elif command -v "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" >/dev/null 2>&1; then
    ok "Chrome found (macOS)"
else
    warn "Chrome not found. Install from https://www.google.com/chrome/"
    warn "  macOS: brew install --cask google-chrome"
    warn "  Ubuntu/Debian: sudo apt install google-chrome-stable"
    warn "  Or continue anyway — ChromeDriver will auto-download if Chrome is found at runtime"
fi

info "Creating virtual environment"
if [ ! -d .venv ]; then
    python3 -m venv .venv || fail "could not create .venv (on Debian/Ubuntu you may need: sudo apt install python3-venv)"
fi
ok ".venv ready"

info "Installing dependencies"
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e ".[dev]" || fail "pip install failed"
ok "dependencies installed"

info "Verifying imports"
.venv/bin/python - <<'PYCHECK' || fail "core imports failed"
import boto3, flask, selenium, tiktoken  # noqa: F401
from agents import review_fetcher, review_analyzer  # noqa: F401
from monitoring import logger, token_tracker, daily_cache  # noqa: F401
print("All imports resolve")
PYCHECK
ok "imports resolve"

info "Checking AWS credentials"
if .venv/bin/python -c "import boto3; boto3.client('sts').get_caller_identity()" >/dev/null 2>&1; then
    ok "AWS credentials found"
else
    warn "AWS credentials not configured or invalid."
    warn "  Configure with: aws configure --profile vista"
    warn "  Or set: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION"
    warn "  The app will not work without valid credentials for Bedrock access."
fi

info "Checking Bedrock model access (optional verification)"
if .venv/bin/python - <<'PYCHECK' 2>/dev/null; then
import boto3, os
os.environ.setdefault("AWS_REGION", "us-east-1")
bedrock = boto3.client("bedrock", region_name=os.getenv("AWS_REGION"))
response = bedrock.list_foundation_models()
models = {m["modelId"] for m in response.get("modelSummaries", [])}
required = {"amazon.nova-micro-v1:0"}
if required.issubset(models):
    print("Bedrock models accessible")
else:
    print("Warning: some required models may not be enabled")
PYCHECK
    ok "Bedrock models checked"
else
    warn "Could not verify Bedrock model access (permissions may be insufficient)"
    warn "  Enable models at: AWS Console → Bedrock → Model Access"
    warn "  Required: amazon.nova-micro-v1:0, us.anthropic.claude-haiku-4-5-20251001-v1:0"
fi

cat <<'DONE'

Setup complete.

  source .venv/bin/activate

  # Set environment variables
  export AWS_PROFILE=vista
  export SNS_TOPIC_ARN=arn:aws:sns:us-east-1:YOUR_ACCOUNT:bedrock-processor-alerts

  # Deploy infrastructure (first time only)
  aws cloudformation create-stack \
    --stack-name review-intel-infra \
    --template-body file://infra/cloudformation.yaml \
    --parameters ParameterKey=AlertEmailList,ParameterValue="you@example.com" \
    --capabilities CAPABILITY_IAM \
    --profile vista

  # Start the server
  python app.py

  # Open browser: http://localhost:5000

DONE
