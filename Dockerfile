# Use an official Python runtime as a parent image
# We choose a slim-bookworm image which is smaller and based on Debian, supporting apt-get
FROM python:3.11-slim-bookworm

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (like ffmpeg)
# apt-get update is necessary inside Dockerfile for fresh package lists
# -y flag for non-interactive installation
RUN apt-get update && apt-get install -y ffmpeg

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code (app.py, index.html, etc.)
COPY . .

# Expose the port your Flask app runs on
EXPOSE 5000

# Define the command to run your application using Gunicorn
# This replaces the Procfile for Docker-based services
CMD gunicorn app:app --bind 0.0.0.0:$PORT