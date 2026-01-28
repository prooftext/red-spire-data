#!/bin/bash

# Start postgres container
docker-compose up -d postgres

# Wait for postgres to be ready
echo "Waiting for postgres to be ready..."
sleep 15

# Run tests
poetry run pytest

# Check if tests failed
if [ $? -ne 0 ]; then
    echo "Tests failed, showing docker logs:"
    docker-compose logs postgres
fi

# Stop postgres
docker-compose down