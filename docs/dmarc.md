# DMARC aggregate ingestion

`backend/app/services/dmarc_ingest.py` reads the rua mailbox over IMAP with `parsedmarc` (offline mode: no DNS or GeoIP lookups) and stores one row per report in `dmarc_reports`, unique on (org_name, report_id, domain_id), so re-reading a report never double counts. Reports for domains we do not own are dropped. A message parsedmarc cannot parse is logged by parsedmarc and left out of the batch; an unreadable parsed report is logged by `store` and skipped.

Per domain per day: `get_fail_count(Session, domain, day)` (None when no report covers that day, so "no data" differs from "zero failures") and `top_failing_ips(Session, domain, day, n=5)` as (ip, count) pairs. The daily health job writes the sums into `domain_health_daily`.

Env (see `.env.example`): `DMARC_IMAP_HOST` (blank skips ingestion), `DMARC_IMAP_PORT`, `DMARC_IMAP_SSL`, `DMARC_IMAP_USER`, `DMARC_IMAP_PASSWORD`, `DMARC_IMAP_FOLDER`, and `DMARC_RUA_ADDRESS` (`{brand}` becomes the brand id) for the rua tag.

Tests: `tests/test_dmarc_mailbox.py` (mocked IMAP, fixture XML) and `tests/test_dmarc_ingest.py`.

## Licence evidence

`parsedmarc` is Apache-2.0. Read on 2026-10-23 from https://api.github.com/repos/domainaware/parsedmarc : `license.spdx_id` = `Apache-2.0`, `license.name` = `Apache License 2.0`, `archived` = false, `pushed_at` 2026-10-22. Pinned `parsedmarc==11.0.5`.
