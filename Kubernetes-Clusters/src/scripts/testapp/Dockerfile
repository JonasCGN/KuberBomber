# Use official Python image from the Docker Hub
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy the Python script to the container
COPY server.py .

# Install Flask
RUN pip install Flask

# Expose port 9898
EXPOSE 9898

# Environment variables for mean processing time and load
ENV MEAN=1.0 \
    LOAD=0.5 \
    ROUTE_PATH=""

# Run the application
CMD ["python", "server.py"]