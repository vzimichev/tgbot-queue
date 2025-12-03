FROM python:3.13-slim

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive \
    POETRY_VERSION=1.8.3 \
    POETRY_HOME="/opt/poetry" \
    PATH="/opt/poetry/bin:$PATH"

# Install system dependencies needed for building Python packages
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==$POETRY_VERSION

# Set the working directory inside the container
WORKDIR /app

# Copy only dependency definition file first (better Docker cache usage)
COPY pyproject.toml /app/

# Install dependencies (no virtualenv inside the container)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy the rest of the application code
COPY . /app

# Expose the port FastAPI will run on
EXPOSE 8000

# Start the API using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
