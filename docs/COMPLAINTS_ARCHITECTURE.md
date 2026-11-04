# Complaints Management, Helpdesk Operations & AI-Assisted Triage

See the comprehensive architecture specification in [services/api/docs/COMPLAINTS_ARCHITECTURE.md](../services/api/docs/COMPLAINTS_ARCHITECTURE.md).

## Highlights
- **Deterministic Multilingual Safety Escalation**: English, Hindi, and Marathi keyword detection forces priority to `CRITICAL` before AI classification.
- **Safety Priority Lock**: Deterministic safety escalations strictly enforce `CRITICAL` priority; priority downgrades below `CRITICAL` are rejected by the API.
- **Asynchronous AI Triage (Google Gemini)**: Complaint creation never waits on LLM responses and returns immediately with `ai_status=PENDING`. Background worker processes jobs via `QUEUE_COMPLAINT_AI_JOBS` using `gemini-2.5-flash` with structured Pydantic schema validation (`responseSchema`), prompt injection defense, and deterministic offline fallback.
- **Resident Privacy & Data Minimization**: PII redaction (`minimize_resident_data()`) automatically strips phone numbers, email addresses, flat numbers, resident names, and secrets before dispatch to Gemini.
- **Worker Idempotency**: Row-locked processing (`with_for_update()`) skips duplicate events if AI triage has already completed or used fallback.
- **Two-Phase Attachment Verification**: S3 presigned PUT URLs with `PENDING`, `UPLOADED`, `FAILED` lifecycle; completion verification validates existence, file size, and MIME type before exposing files. Frontend verifies upload status before completing.
- **Configurable SLA Policies**: Real-time breach detection with 5-minute first response for critical hazards and dynamic SLA recalculation.
- **Workload-Based Staff Assignment**: Automatically load balances tickets across active helpdesk staff in the society based on total active tickets.
- **Privacy Model**: Internal helpdesk notes and staff-only timeline transitions are strictly excluded from resident responses.
- **Transactional Outbox & Worker Routing**: Discrete routing between `QUEUE_COMPLAINT_AI_JOBS` and `QUEUE_NOTIFICATION_JOBS`.
