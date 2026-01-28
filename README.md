# Prooftext API
Server code for the Prooftext keystroke biometrics authentication system.

## Requirements
- Python 3.13+
- Poetry
- Docker (for running tests with postgres)

## Installation

```bash
poetry install
```

## Running Tests

To run the test suite with a local postgres database:

```bash
./run_tests.sh
```

This will:
1. Start a postgres container
2. Run database migrations
3. Execute all unit and functional tests
4. Stop the postgres container

## Manual Testing

If you want to run tests manually:

1. Start postgres:
```bash
docker-compose up -d postgres
```

2. Run tests:
```bash
poetry run pytest
```

3. Stop postgres:
```bash
docker-compose down
```

## API Endpoints

- `GET /` - Redirects to Swagger UI
- `GET /health` - Health check
- `POST /api/v1/keystroke/collect` - Collect keystroke data
- `POST /api/v1/keystroke/verify` - Verify text against stored sessions

## Development

Run the server locally:

```bash
poetry run uvicorn app.main:app --reload
```
