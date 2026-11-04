# Complaints Management, Helpdesk Operations & AI-Assisted Triage

See the comprehensive architecture specification in [services/api/docs/COMPLAINTS_ARCHITECTURE.md](../services/api/docs/COMPLAINTS_ARCHITECTURE.md).

## Highlights
- **Deterministic Multilingual Safety Escalation**: English, Hindi, and Marathi keyword detection forces priority to `CRITICAL` before AI classification.
- **Safety Priority Lock**: Deterministic safety escalations strictly enforce `CRITICAL` priority; priority downgrades below `CRITICAL` are rejected by the API.
- **Asynchronous AI Triage (Google Gemini)**: Complaint creation never waits on LLM responses and returns immediately with `ai_status=PENDING`. Background worker processes jobs via `QUEUE_COMPLAINT_AI_JOBS` using `gemini-2.5-flash` with structured Pydantic schema validation (`responseSchema`), prompt injection defense, and deterministic offline fallback.
- **Worker Reliability & Lock Freedom**: Atomic job claiming marks `PROCESSING` and releases DB locks before invoking external LLM APIs. Transient failures re-raise `RetryableWorkerError` to prevent message loss in SQS, while permanent errors acknowledge poison pills without re-raising. Bounded retries (3 attempts) and 300s lease timeout ensure safe crash recovery.
- **Resident Privacy & Data Minimization**: Best-effort heuristic sanitization (`minimize_resident_data()`) redacts phone numbers (including Devnagari digits), email addresses, flat coordinates, PIN codes, resident names in English, Hindi, and Marathi, and credentials before dispatch.
- **Strict Storage Verification**: Presigned S3 uploads require exact declared-vs-actual size equality, reject missing or mismatched ContentType headers, and enforce 5MB limits.
- **Configurable SLA Policies**: Real-time breach detection with 5-minute first response for critical hazards and dynamic SLA recalculation.
- **Workload-Based Staff Assignment**: Automatically load balances tickets across active helpdesk staff in the society based on total active tickets.
- **Privacy Model**: Internal helpdesk notes and staff-only timeline transitions are strictly excluded from resident responses.
- **Transactional Outbox & Worker Routing**: Discrete routing between `QUEUE_COMPLAINT_AI_JOBS` and `QUEUE_NOTIFICATION_JOBS`.
