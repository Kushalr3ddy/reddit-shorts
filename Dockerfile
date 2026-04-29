# Use a slim Python image to save RAM/Disk
FROM python:3.12-slim

# Install system dependencies
# ffmpeg: for video processing
# fonts-dejavu: for the subtitles
# libmagic1: for file type detection (common in boto3/supabase)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-dejavu-core \
    libmagic1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create temp directory
RUN mkdir -p temp assets

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the pipeline
CMD ["python", "main.py"]