# CI job image: Python 3.13 for the test suite, Node 20 for JS actions.
#
# Gitea's self-hosted runner executes JS actions (actions/checkout@v4, ...)
# *inside* the job container — unlike GitHub-hosted runners, which ship Node
# in the runner itself. Plain python:3.13-slim therefore fails at checkout
# with `exec: "node": executable file not found in $PATH`.
#
# Build once on the runner host (lamai270):
#   docker build -t marginalia-ci:node20 ci/
FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*
