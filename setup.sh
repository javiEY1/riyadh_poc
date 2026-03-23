#!/bin/bash
set -e

echo "Installing Tesseract OCR..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa
elif command -v brew &>/dev/null; then
    brew install tesseract
elif command -v yum &>/dev/null; then
    sudo yum install -y tesseract
else
    echo "ERROR: Could not detect package manager. Install Tesseract OCR manually."
    echo "  Ubuntu/Debian: sudo apt install tesseract-ocr"
    echo "  macOS:         brew install tesseract"
    echo "  Windows:       https://github.com/UB-Mannheim/tesseract/wiki"
    exit 1
fi

echo "Installing Python dependencies..."
pip install -e ".[dev]"

echo "Setup complete. Run: uvicorn app.main:app --reload"
