# Use a lightweight Python base image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer outputs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set workspace directory
WORKDIR /workspace

# Install common system dependencies needed for code/tests
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install default testing and linting tools and ruff
RUN pip install --no-cache-dir \
    pytest \
    ruff \
    pytest-asyncio

# Default command if executed without arguments
CMD ["sh", "-c", "ruff check . ; pytest"]
