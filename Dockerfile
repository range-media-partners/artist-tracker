# Start from an official, slim Python 3.12 image.
# "slim" = minimal Debian Linux with Python, no extra bloat.
FROM python:3.12-slim

# Set the working directory inside the container. Everything after this
# happens relative to /app. This becomes our project root in the container.
WORKDIR /app

# Copy requirements FIRST, before the rest of the code, and install.
# This ordering is a deliberate optimization (explained below).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the project into the container, preserving layout.
# .dockerignore controls what's excluded (config.env, venv, caches, etc.)
COPY . .

# Recreate the writable runtime directories (their contents were ignored,
# but the scripts expect the folders to exist).
RUN mkdir -p logs reports data/uploads

# Default command. This is a placeholder — each Cloud Run Job or Service
# overrides it with the specific script to run. We set a harmless default.
CMD ["python", "scripts/daily_collect.py"]