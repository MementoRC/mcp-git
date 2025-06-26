FROM python:3.12-slim-bookworm

# Install git and essential build tools, which are runtime and build dependencies for the server
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy all project files into the image
# This includes pyproject.toml, src/, tests/, etc.
COPY . /app

# Install the project and its dependencies
# pip will read pyproject.toml to determine dependencies and the project itself
RUN pip install .

# Set the entrypoint for the container
# This uses the script defined in pyproject.toml under [project.scripts]
ENTRYPOINT ["mcp-server-git"]
