# Complaints Management, Helpdesk Operations & AI-Assisted Triage

See the comprehensive architecture specification in [services/api/docs/COMPLAINTS_ARCHITECTURE.md](../services/api/docs/COMPLAINTS_ARCHITECTURE.md).

## Highlights
- **Deterministic Multilingual Safety Escalation**: English, Hindi, and Marathi keyword detection forces priority to `CRITICAL` before AI classification.
- **Safety Priority Lock**: Deterministic safety escalations strictly enforce `CRITICAL` priority; priority downgrades below `CRITICAL` are rejected by the API.
- **Asynchronous AI Triage (Google Gemini)**: Server-authoritative background triage with `gemini-2.5-flash`, prompt injection defenses, structured Pydantic schema validation, and deterministic offline fallback.
- **Two-Phase Attachment Verification**: S3 presigned PUT URLs with `PENDING`, `UPLOADED`, `FAILED` lifecycle; completion verification ensures unverified objects are never exposed.
- **Configurable SLA Policies**: Real-time breach detection with 5-minute first response for critical hazards and dynamic SLA recalculation.
- **Workload-Based Staff Assignment**: Automatically load balances tickets across active helpdesk staff in the society based on total active tickets.
- **Privacy Model**: Internal helpdesk notes and staff-only timeline transitions are strictly excluded from resident responses.
- **Transactional Outbox & Worker Routing**: Discrete routing between `QUEUE_COMPLAINT_AI_JOBS` and `QUEUE_NOTIFICATION_JOBS`.
