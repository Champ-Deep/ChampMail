# Backend Testing Configuration
# Run with: pytest

## Test Structure

### Unit Tests (tests/unit/)
- `test_domain_service.py` - Domain service business logic
- `test_sequence_service.py` - Sequence management
- `test_prospect_service.py` - Prospect CRUD operations
- `test_celery_tasks.py` - Celery task logic
- `test_models.py` - Data model validation

### Integration Tests (tests/integration/)
- `test_database.py` - Database operations
- `test_mail_engine_client.py` - Mail engine integration
- `test_namecheap_client.py` - Namecheap API integration
- `test_cloudflare_client.py` - Cloudflare API integration

### API Tests (tests/api/)
- `test_auth.py` - Authentication endpoints
- `test_domains.py` - Domain management endpoints
- `test_sending.py` - Email sending endpoints
- `test_prospects.py` - Prospect endpoints
- `test_sequences.py` - Sequence endpoints

## Running Tests

### All Tests
```bash
pytest
```

### Unit Tests Only
```bash
pytest tests/unit/
```

### Integration Tests Only
```bash
pytest tests/integration/
```

### API Tests Only
```bash
pytest tests/api/
```

### With Coverage
```bash
pytest --cov=app --cov-report=html
```

### Watch Mode
```bash
pytest-watch
```

## Environment Variables for Testing

```bash
export TEST_DATABASE_URL="postgresql://champmail:champmail_dev@localhost:5432/champmail_test"
export TEST_REDIS_URL="redis://localhost:6379/15"
export TEST_MAIL_ENGINE_URL="http://localhost:8025"
export TEST_FALKORDB_HOST="localhost"
export TEST_FALKORDB_PORT="6379"
```

## Test Fixtures

Common fixtures available in conftest.py:
- `test_session` - Async database session
- `test_client` - FastAPI test client
- `test_domain` - Sample domain data
- `test_prospect` - Sample prospect data
- `test_sequence` - Sample sequence data
- `test_user` - Sample user data

## CI/CD Pipeline

Tests run automatically on:
1. Pull request creation
2. Push to main branch
3. Release creation

Required test pass rate: 90%