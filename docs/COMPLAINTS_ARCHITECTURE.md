# Complaints Management, Helpdesk Operations & AI-Assisted Triage

See the comprehensive architecture specification in [services/api/docs/COMPLAINTS_ARCHITECTURE.md](../services/api/docs/COMPLAINTS_ARCHITECTURE.md).

## Highlights
- **Deterministic Multilingual Safety Escalation**: English, Hindi, and Marathi keyword detection forces priority to `CRITICAL` before AI classification.
- **AI-Assisted Advisory Triage**: Offline deterministic triage classifying issues and scoring confidence without paid LLM keys.
- **Configurable SLA Policies**: Real-time breach detection with 5-minute first response for critical hazards.
- **Workload-Based Staff Assignment**: Automatically load balances tickets across active helpdesk staff in the society.
- **Privacy Model**: Internal helpdesk notes are strictly excluded from resident responses.
- **Presigned Attachment Storage**: Secure S3/Mock storage supporting JPEG, PNG, and WebP up to 5MB.
- **Transactional Outbox & Audit Logging**: Guaranteed event publishing and complete action auditability.
