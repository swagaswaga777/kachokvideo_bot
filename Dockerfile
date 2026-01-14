FROM python:3.11-slim

# Install system dependencies (ffmpeg is required for yt-dlp)
# Clean up apt cache to reduce image size and attack surface
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Change ownership of the application directory
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

CMD ["python", "-m", "src.main"]
