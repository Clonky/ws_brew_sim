# Use an official Python runtime as a parent image
FROM python:3.14-slim

# Set the working directory in the container
WORKDIR /app

# Copy the project files
COPY pyproject.toml .
COPY src/ ./src
COPY xmls/ ./xmls
COPY examples/ ./examples
COPY static/ ./static
COPY templates/ ./templates

RUN apt update && apt install -y git && apt clean

# Install any needed packages specified in pyproject.toml
# The '.' installs the project itself as a package
RUN pip install .

# Make ports 8080 and 4840 available to the world outside this container
EXPOSE 8080
EXPOSE 4840

# Run server_bake.py when the container launches
CMD ["python", "examples/server_bake.py"]
