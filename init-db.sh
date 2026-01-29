#!/bin/bash
# Create test_user for testing
psql -U postgres -d postgres <<EOF
CREATE USER test_user WITH PASSWORD 'test_password';
ALTER USER test_user CREATEDB;
GRANT CREATE ON DATABASE test_prooftext TO test_user;
EOF
