# Production Operations Guide

This guide covers operational aspects of the content operations agent in production, including monitoring, maintenance, and troubleshooting procedures for Phase 1 (Reliability & Recovery) and Phase 2 (Observability & Monitoring) features.

## Table of Contents

1. [Monitoring & Observability](#monitoring--observability)
2. [Maintenance Tasks](#maintenance-tasks)
3. [Reliability Features](#reliability-features)
4. [Troubleshooting](#troubleshooting)
5. [Performance Tuning](#performance-tuning)

---

## Monitoring & Observability

### Prometheus Metrics

**Endpoint**: `GET /api/metrics`

The application exposes Prometheus-compatible metrics for monitoring system health and performance.

#### Core Metrics

**Idempotency Tracking**:
- `idempotency_requests_total{scope, outcome}` — Counter for idempotent requests
  - `outcome`: `claimed`, `replay`, `conflict`, `failed`
  - `scope`: `content_create`, `content_refine`, `calendar_commit`, `publication_execute`, `memory_mutation`

**Job Reliability**:
- `job_retries_total{error_type}` — Counter for job retry attempts (`transient`, `permanent`)
- `job_retry_exhausted_total` — Counter for jobs that exhausted all retries
- `job_failures_total{error_type}` — Counter for job failures by error classification

**Capability System**:
- `capability_proposals_total` — Counter for proposed actions
- `capability_consumptions_total` — Counter for consumed capabilities
- `capability_expirations_total` — Counter for expired capabilities

**Publication Pipeline**:
- `publication_requests_total{status}` — Counter for publication requests (`success`, `failed`)
- `publication_request_duration_seconds{status}` — Histogram for publication duration

**HTTP Traffic**:
- `http_requests_total{method, endpoint, status}` — Counter for all HTTP requests
- `http_request_duration_seconds{method, endpoint}` — Histogram for request latency

#### Prometheus Server Setup

1. **Configure scrape target** in `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'content-ops-agent'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/api/metrics'
    scrape_interval: 15s
```

2. **Start Prometheus**:

```bash
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v /path/to/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus
```

3. **Verify**: Visit `http://localhost:9090/targets` to confirm the scrape target is UP.

### Grafana Dashboard

#### Recommended Panels

**System Health**:
- HTTP request rate and error rate (5xx responses)
- Request latency P50/P95/P99
- Job queue depth and processing rate

**Reliability Metrics**:
- Idempotency replay rate (should be low in steady state)
- Job retry rate by error type
- Retry exhaustion rate (critical alert threshold)

**Business Metrics**:
- Content creation/refinement throughput
- Publication success rate
- Capability consumption rate

#### Sample PromQL Queries

```promql
# HTTP error rate (last 5m)
rate(http_requests_total{status=~"5.."}[5m])

# Job retry rate by error type
rate(job_retries_total[5m])

# Idempotency replay percentage
rate(idempotency_requests_total{outcome="replay"}[5m]) 
  / rate(idempotency_requests_total[5m]) * 100

# P95 publication latency
histogram_quantile(0.95, 
  rate(publication_request_duration_seconds_bucket[5m]))
```

### Structured Logging

All critical events emit structured JSON logs with correlation IDs.

#### Log Event Types

**Idempotency Events**:
```json
{
  "event": "idempotency_claim",
  "scope": "content_create",
  "idempotency_key": "req_abc123",
  "outcome": "claimed",
  "timestamp": "2024-09-02T15:30:00Z"
}
```

**Job Retry Events**:
```json
{
  "event": "job_retry_scheduled",
  "job_id": "job_xyz789",
  "attempt": 2,
  "error_type": "transient",
  "next_retry_at": "2024-09-02T15:31:00Z",
  "backoff_seconds": 60
}
```

**Capability Events**:
```json
{
  "event": "capability_consumption",
  "capability_id": "cap_def456",
  "action_id": "act_ghi789",
  "thread_id": "thread_123"
}
```

#### Log Collection

Configure your log aggregator (e.g., Loki, Elasticsearch) to parse JSON logs:

```bash
# Docker Compose logs with jq
docker compose logs -f api worker | jq 'select(.event != null)'

# Filter by event type
docker compose logs -f api | jq 'select(.event == "job_retry_scheduled")'
```

### Dashboard Query Helpers

The application provides built-in query functions for operational dashboards.

**Python API**:

```python
from src.utils.dashboard_queries import (
    get_idempotency_stats,
    get_job_retry_stats,
    get_capability_stats
)

# Get statistics for last 7 days
idempotency_stats = await get_idempotency_stats(days=7)
# Returns: {"total_requests": 1234, "replays": 56, "conflicts": 2, ...}

job_stats = await get_job_retry_stats(days=7)
# Returns: {"total_retries": 45, "transient_errors": 40, "exhausted": 2, ...}

capability_stats = await get_capability_stats(days=7)
# Returns: {"proposals": 890, "consumptions": 850, "expirations": 40}
```

**REST API** (add custom endpoints as needed):

```python
# Example: src/api/routes/admin.py
@router.get("/stats/idempotency")
async def idempotency_stats(days: int = 7):
    return await get_idempotency_stats(days)
```

---

## Maintenance Tasks

### Job Cleanup

Old job records should be archived periodically to prevent unbounded table growth.

**Script**: `src/jobs/cleanup.py`

**Retention Policy**:
- Completed jobs: 30 days
- Permanently failed jobs: 7 days
- Jobs are soft-deleted (set `archived_at` timestamp) for audit trail

#### Manual Cleanup

**Dry run** (preview what would be deleted):

```bash
python3 -m src.jobs.cleanup --dry-run
```

Output:
```
DRY RUN - Job Cleanup Results
Completed jobs (>30 days): 145 jobs
Permanently failed jobs (>7 days): 12 jobs
Total to archive: 157 jobs
```

**Execute cleanup**:

```bash
python3 -m src.jobs.cleanup --execute
```

#### Automated Cleanup

Configure cron for daily cleanup:

```bash
# /etc/cron.d/content-ops-cleanup
0 2 * * * app cd /app && python3 -m src.jobs.cleanup --execute >> /var/log/job-cleanup.log 2>&1
```

Or use systemd timer:

```ini
# /etc/systemd/system/job-cleanup.timer
[Unit]
Description=Content Ops Job Cleanup Timer

[Timer]
OnCalendar=daily
OnCalendar=02:00

[Install]
WantedBy=timers.target
```

```ini
# /etc/systemd/system/job-cleanup.service
[Unit]
Description=Content Ops Job Cleanup

[Service]
Type=oneshot
User=app
WorkingDirectory=/app
Environment="DATABASE_URL=postgresql+psycopg://..."
ExecStart=/usr/bin/python3 -m src.jobs.cleanup --execute
```

### Capability Expiration

Expired capabilities are cleaned automatically by a background job.

**Job**: `src/jobs/capability_expiration.py`

**Default TTL**: 1 hour (configurable via `CAPABILITY_TTL_SECONDS`)

The capability expiration job runs via RQ at regular intervals. Monitor `capability_expirations_total` metric to track expired capabilities.

### Database Maintenance

#### Vacuum and Analyze

For PostgreSQL, schedule periodic maintenance:

```bash
# Weekly full vacuum (requires maintenance window)
docker compose exec postgres psql -U content_ops -c "VACUUM FULL ANALYZE;"

# Daily auto-vacuum monitoring
docker compose exec postgres psql -U content_ops -c \
  "SELECT schemaname, relname, last_vacuum, last_autovacuum 
   FROM pg_stat_user_tables 
   ORDER BY last_autovacuum DESC NULLS LAST;"
```

#### Index Monitoring

Check for missing or unused indexes:

```sql
-- Table sizes
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Index usage
SELECT 
  schemaname,
  tablename,
  indexname,
  idx_scan,
  pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan ASC;
```

---

## Reliability Features

### Idempotency

**Purpose**: Prevent duplicate actions when clients retry requests.

**Supported Operations**:
- Content creation (`POST /api/content`)
- Content refinement (`POST /api/content/{id}/refine`)
- Calendar commits (`POST /api/publishing/schedule/commit`)
- Publication execution (internal)
- Memory mutations (internal)

#### Client Usage

Send an `Idempotency-Key` header with your request:

```bash
curl -X POST http://localhost:8000/api/content \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Idempotency-Key: req_$(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"title": "My Content", "body": "..."}'
```

**Behavior**:
- First request with a key: processes normally, stores result
- Retry with same key: returns stored result immediately (no duplicate processing)
- Same key, different request body: returns `422 Unprocessable Entity`

**Key Lifecycle**:
- Keys are stored permanently for audit
- Completed operations can be replayed indefinitely
- Failed operations can be retried (key is reclaimed)
- In-progress operations return `409 Conflict`

### Automatic Job Retry

**Purpose**: Automatically retry transient failures without manual intervention.

**Strategy**: Exponential backoff with jitter
- 1st retry: 30 seconds
- 2nd retry: 60 seconds
- 3rd retry: 120 seconds
- 4th retry: 240 seconds
- 5th retry: 480 seconds (max delay)

**Configuration**:

```bash
# .env or environment
JOB_MAX_RETRIES=5
JOB_RETRY_INITIAL_DELAY_SECONDS=30
JOB_RETRY_MAX_DELAY_SECONDS=480
```

#### Error Classification

**Transient Errors** (will retry):
- Network timeouts and connection errors
- HTTP 429 (rate limit), 502/503/504 (gateway errors)
- Messages containing "rate limit exceeded", "quota exceeded", "service unavailable"
- Database connection errors
- Temporary LLM/MCP client failures

**Permanent Errors** (will not retry):
- Configuration errors (invalid API key, invalid model)
- Validation errors (bad input data)
- HTTP 4xx (except 429)
- Data integrity errors
- Authorization/authentication failures

#### Monitoring Retries

**Check retry status** for a specific job:

```sql
SELECT 
  id,
  job_type,
  status,
  attempts,
  max_retries,
  error_type,
  next_retry_at,
  created_at
FROM jobs
WHERE id = 'job_xyz789';
```

**Find jobs with multiple retries**:

```sql
SELECT 
  id,
  job_type,
  attempts,
  error_type,
  error_message
FROM jobs
WHERE attempts > 1
  AND status = 'failed'
  AND error_type = 'transient'
ORDER BY attempts DESC
LIMIT 20;
```

### Persistent Capabilities

**Purpose**: Ensure user-approved actions execute exactly once, even across crashes.

**Workflow**:
1. Agent proposes an action → stored in `proposed_actions` table
2. User confirms → capability issued with unique ID
3. Action executes → capability consumed atomically (cannot be reused)
4. Crash/retry → already-consumed capability prevents duplicate execution

**Database Tables**:
- `proposed_actions`: Stores action proposals with parameters and expiry
- Capabilities are one-time use tokens that prevent replay attacks

**Monitoring**:

```sql
-- Check capability consumption rate
SELECT 
  DATE_TRUNC('hour', created_at) as hour,
  COUNT(*) as proposals,
  SUM(CASE WHEN consumed_at IS NOT NULL THEN 1 ELSE 0 END) as consumed,
  SUM(CASE WHEN expires_at < NOW() THEN 1 ELSE 0 END) as expired
FROM proposed_actions
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

---

## Troubleshooting

### High Idempotency Replay Rate

**Symptom**: `idempotency_requests_total{outcome="replay"}` is high

**Possible Causes**:
- Client is aggressively retrying successful requests
- Load balancer health check or circuit breaker is triggering retries
- Frontend is not properly handling 200 OK responses

**Investigation**:

```bash
# Check logs for replay events
docker compose logs api | jq 'select(.event == "idempotency_claim" and .outcome == "replay")'

# Check which endpoints have high replay rate
# Query Prometheus:
rate(idempotency_requests_total{outcome="replay"}[5m]) by (scope)
```

**Resolution**:
- Review client retry logic
- Ensure clients store and check response status codes
- Consider adding client-side caching with short TTL

### Job Retry Exhaustion

**Symptom**: `job_retry_exhausted_total` is increasing

**Possible Causes**:
- Persistent external service outage
- Configuration error (bad API key, invalid endpoint)
- Resource exhaustion (rate limits, quotas)

**Investigation**:

```sql
-- Find exhausted jobs
SELECT 
  id,
  job_type,
  attempts,
  max_retries,
  error_type,
  error_message,
  created_at,
  updated_at
FROM jobs
WHERE status = 'failed'
  AND attempts >= max_retries
  AND error_type = 'transient'
ORDER BY updated_at DESC
LIMIT 10;
```

**Resolution**:
1. Check error messages for common patterns
2. Verify external service status
3. Confirm API keys and configurations are valid
4. Increase rate limit budgets if needed
5. Consider manual retry after fixing root cause:

```sql
-- Reset job for manual retry (after fixing issue)
UPDATE jobs
SET 
  status = 'pending',
  attempts = 0,
  next_retry_at = NULL,
  error_message = NULL,
  error_type = NULL
WHERE id = 'job_xyz789';
```

### Memory/Disk Growth

**Symptom**: Database or Redis growing unbounded

**Investigation**:

```sql
-- Check table sizes
SELECT 
  tablename,
  pg_size_pretty(pg_total_relation_size('public.' || tablename)) as total_size,
  pg_size_pretty(pg_relation_size('public.' || tablename)) as table_size,
  pg_size_pretty(pg_total_relation_size('public.' || tablename) - pg_relation_size('public.' || tablename)) as index_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size('public.' || tablename) DESC;

-- Check job counts
SELECT 
  status,
  error_type,
  COUNT(*),
  MIN(created_at) as oldest,
  MAX(created_at) as newest
FROM jobs
GROUP BY status, error_type;
```

**Resolution**:
1. Verify job cleanup cron is running: `python3 -m src.jobs.cleanup --dry-run`
2. Check cleanup configuration (30 days for completed, 7 days for failed)
3. Consider archiving old data to separate storage
4. Run manual cleanup if needed: `python3 -m src.jobs.cleanup --execute`

### High Database Connection Count

**Symptom**: PostgreSQL `max_connections` limit reached

**Investigation**:

```sql
-- Current connections
SELECT 
  datname,
  usename,
  application_name,
  state,
  COUNT(*)
FROM pg_stat_activity
WHERE datname = 'content_ops'
GROUP BY datname, usename, application_name, state;
```

**Resolution**:
1. Calculate required connections: `(WEB_CONCURRENCY × DB_POOL_SIZE) + DB_POOL_SIZE` (for worker)
2. Increase PostgreSQL `max_connections`: `POSTGRES_MAX_CONNECTIONS=200` in Docker Compose
3. Reduce `DB_POOL_SIZE` or `WEB_CONCURRENCY` if scaling is excessive
4. Enable connection pooling with PgBouncer for higher scale

---

## Performance Tuning

### API Workers

**Configuration**: `WEB_CONCURRENCY` environment variable (default: 3)

**Calculation**:
- CPU-bound: `WEB_CONCURRENCY = (2 × CPU_cores) + 1`
- I/O-bound: `WEB_CONCURRENCY = 4 × CPU_cores`
- Start with default (3) and scale based on metrics

**Database Connections**:
- Each API worker: `DB_POOL_SIZE` + `DB_MAX_OVERFLOW` connections
- Total: `WEB_CONCURRENCY × (DB_POOL_SIZE + DB_MAX_OVERFLOW)` + worker connections
- Ensure `max_connections` in PostgreSQL > total required connections

### RQ Workers

**Scaling**: Add more worker processes for increased throughput

```bash
# Docker Compose scaling
docker compose up -d --scale worker=3
```

**Configuration**:
- `MAX_PROVIDER_INFLIGHT_JOBS`: Concurrent LLM requests per worker (default: 8)
- Scale workers based on provider rate limits and job volume

### Database Optimization

**Connection Pooling**:

```python
# .env configuration
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
```

**Query Performance**:

```sql
-- Find slow queries
SELECT 
  query,
  calls,
  mean_exec_time,
  max_exec_time
FROM pg_stat_statements
WHERE mean_exec_time > 100  -- milliseconds
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### Redis Optimization

**Memory Policy**: Configure `maxmemory-policy` in production

```bash
# redis.conf or docker compose command
redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

---

## Alerting Rules

### Critical Alerts

**Job Retry Exhaustion**:
```yaml
- alert: JobRetryExhausted
  expr: rate(job_retry_exhausted_total[5m]) > 0.1
  for: 5m
  annotations:
    summary: "Jobs are exhausting retries"
    description: "{{ $value }} jobs/sec are failing after max retries"
```

**High Error Rate**:
```yaml
- alert: HighHTTPErrorRate
  expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
  for: 5m
  annotations:
    summary: "High HTTP 5xx error rate"
    description: "{{ $value | humanizePercentage }} of requests are failing"
```

### Warning Alerts

**High Retry Rate**:
```yaml
- alert: HighJobRetryRate
  expr: rate(job_retries_total[5m]) > 1
  for: 10m
  annotations:
    summary: "Elevated job retry rate"
    description: "{{ $value }} job retries/sec"
```

**Database Connection Pressure**:
```yaml
- alert: DatabaseConnectionPressure
  expr: pg_stat_activity_count / pg_settings_max_connections > 0.8
  for: 5m
  annotations:
    summary: "Database connection pool nearly exhausted"
```

---

## Support and Escalation

For issues not covered in this guide:

1. **Check structured logs** for detailed event traces with correlation IDs
2. **Review Prometheus metrics** for system-wide patterns
3. **Query the database** for job/capability state details
4. **Consult**:
   - `docs/PHASE0_SECURITY_AND_MIGRATIONS.md` for security and migration concerns
   - `docs/IMPROVEMENT_LOG.md` for implementation details and known limitations
   - `docs/WORKFLOW_CHECKPOINT.md` for current system state and roadmap
