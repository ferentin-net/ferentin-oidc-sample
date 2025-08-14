#!/bin/bash

# Start the FastAPI BFF server
echo "Starting Ferentin OIDC BFF..."
echo "Make sure you have:"
echo "1. Created and activated a virtual environment"
echo "2. Installed dependencies: pip install -r requirements.txt"
echo "3. Configured .env file with your OIDC provider settings"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Warning: .env file not found!"
    echo "Copy env.example to .env and configure your OIDC provider settings:"
    echo "  cp env.example .env"
    echo ""
fi

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
