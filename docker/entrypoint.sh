#!/bin/bash

# This file is used to run the application inside the container on startup development server.
export PYTHONDONTWRITEBYTECODE=1
cd /home/app
uv sync
uv run uvicorn app.main.main:app --host=0.0.0.0 --port=80 --reload
