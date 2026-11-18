#!/bin/bash
# Starts Axor Cloud (port 8080) and the Axor assistant (port 8765).
cd "$(dirname "$0")"
if [ -x venv/bin/python ]; then PY="venv/bin/python"; else PY="python3"; fi
if ! $PY -c "import flask" 2>/dev/null; then echo "Flask is missing. Run:  $PY -m pip install -r requirements.txt"; exit 1; fi
(cd axor-cloud && ../$PY cloud.py 2>/dev/null || $PY cloud.py) &
CLOUD=$!
trap "kill $CLOUD 2>/dev/null" EXIT
sleep 1
$PY server.py
