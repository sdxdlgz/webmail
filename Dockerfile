FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY start.py .

# Create data directory
RUN mkdir -p backend/data

# Expose port
EXPOSE 8000

# Run
CMD ["python", "start.py"]
