#!/bin/bash

# This file is used to run the application inside the container on startup development server.
cd /home/app
uv sync
uv run uvicorn app.main.main:app --host=0.0.0.0 --port=8000 --reload
