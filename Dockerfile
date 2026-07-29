FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including gcc/build tools if needed by python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose port
EXPOSE 8085

# Start Uvicorn directly
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8085"]
