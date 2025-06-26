FROM python:3.12-slim-bookworm

# Install git and essential build tools, which are runtime and build dependencies for the server
# Also install curl for downloading uv
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential pkg-config libssl-dev curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy all project files into the image
# This includes pyproject.toml, src/, tests/, etc.
COPY . /app

# Install uv
# Pin a specific uv version for reproducibility.
ENV UV_VERSION=0.1.37
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && . $HOME/.local/bin/env \
    && mv $HOME/.local/bin/uv /usr/local/bin/uv \
    && rm -rf $HOME/.local

# Install the project and its dependencies using uv
# uv pip install . will install the local project and its dependencies,
# respecting uv.lock if present, similar to pip install .
RUN uv pip install .

# Set the entrypoint for the container
# This uses the script defined in pyproject.toml under [project.scripts]
ENTRYPOINT ["mcp-server-git"]
