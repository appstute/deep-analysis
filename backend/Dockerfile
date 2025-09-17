FROM python:3.11.1-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_APP=execution_layer/execution_api.py
ENV FLASK_DEBUG=1
# Pass OpenAI API key at build time (e.g. `docker build --build-arg OPENAI_API_KEY=my_key .`)
ARG OPENAI_API_KEY="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"
ENV OPENAI_API_KEY=${OPENAI_API_KEY}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    procps \
    net-tools \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install -r requirements.txt

# Copy application code - only the execution layer and dependencies
COPY logger.py .
COPY execution_layer/ execution_layer/

# Create base output directory structure
RUN mkdir -p execution_layer/output_data && \
    chmod -R 777 execution_layer/output_data


# Expose port for API
EXPOSE 5001

# Run the execution API
CMD ["python", "execution_layer/run_execution_api.py"]
