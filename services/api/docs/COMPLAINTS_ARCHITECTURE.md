# Complaints Management, Helpdesk Operations & AI-Assisted Triage

## Overview

Phase 3 introduces an enterprise-grade complaints and facility operations module tailored for high-density gated townships (2,400 apartments across 28 towers, maintained by 180 facility staff).

The architecture enforces:
- **Server-Authoritative Lifecycle**: Strict state machine transitions preventing invalid operational bypasses.
- **Deterministic Multilingual Safety Escalation**: Immediate physical safety hazard recognition (English, Hindi, Marathi) executing *before* AI classification.
- **Safety Priority Lock**: Deterministic safety escalations strictly enforce `CRITICAL` priority; priority downgrades below `CRITICAL` are rejected by the API.
- **AI-Assisted Advisory Triage**: Asynchronous Google Gemini (`gemini-2.5-flash`) classification with structured Pydantic schema validation, prompt injection defense, and offline deterministic fallback.
- **Two-Phase Attachment Lifecycle**: Secure presigned upload URLs with `PENDING`, `UPLOADED`, `FAILED` states, fail-closed production storage, and verification completion endpoints.
- **Workload-Based Auto-Assignment**: Automatic load-balanced ticket routing to active helpdesk staff counting open tickets (`ASSIGNED`, `IN_PROGRESS`, `AWAITING_RESIDENT`, `REOPENED`).
- **Public vs. Internal Note Separation**: Strict privacy boundary ensuring resident views never leak internal staff discussions or private transition metadata.
- **Transactional Outbox & Asynchronous Workers**: Guaranteed event publishing with discrete routing to `QUEUE_COMPLAINT_AI_JOBS` and `QUEUE_NOTIFICATION_JOBS`.

---

## 1. System Scale & Security Model

The township operations platform strictly implements a two-role security boundary:
- `RESIDENT`: Scoped strictly to flats where the user holds an active approved membership. Can submit tickets, post public comments, attach photos, rate resolved tickets, and reopen within 7 days. Residents can NEVER submit internal helpdesk notes.
- `HELPDESK`: Scoped to the staff member's authorized society. Can triage, assign, update priority/status, post internal notes, and monitor operational SLA KPI dashboards.

Cross-tenant access (cross-society and cross-flat) is denied at the database and API layer with `403 Forbidden` (`TenantIsolationError`).

---

## 2. Complaint Lifecycle State Machine

```
                 ┌────────────────────────────────────────────────┐
                 │                                                │
[SUBMITTED] ───► [TRIAGED] ───► [ASSIGNED] ───► [IN_PROGRESS]    │
     │              │               │                 │           ▼
     │              │               │                 ├────► [CANCELLED]
     │              │               ▼                 ▼
     │              │       [AWAITING_RESIDENT] ──► [RESOLVED]
     │              │                                 │
     │              └─────────────────────────────────┤
     │                                                ▼
     └──────────────────────────────────────────► [CLOSED]
                                                      │ (Within 7 Days)
                                                      ▼
                                                 [REOPENED] ──► [IN_PROGRESS]
```

### Permitted Transitions

| From Status | Permitted Target Statuses | Notes |
|---|---|---|
| `SUBMITTED` | `TRIAGED`, `ASSIGNED`, `IN_PROGRESS`, `CANCELLED` | Initial state upon submission |
| `TRIAGED` | `ASSIGNED`, `IN_PROGRESS`, `CANCELLED` | Categorized and prioritized |
| `ASSIGNED` | `IN_PROGRESS`, `AWAITING_RESIDENT`, `CANCELLED` | Assigned to staff member |
| `IN_PROGRESS` | `AWAITING_RESIDENT`, `RESOLVED`, `CANCELLED` | Active work underway; sets `first_response_at` |
| `AWAITING_RESIDENT` | `IN_PROGRESS`, `RESOLVED`, `CANCELLED` | Awaiting resident clarification/access |
| `RESOLVED` | `CLOSED`, `REOPENED` | Work completed; sets `resolved_at` |
| `CLOSED` | `REOPENED` (within 7 days) | Ticket verified closed; sets `closed_at` |
| `REOPENED` | `ASSIGNED`, `IN_PROGRESS`, `CANCELLED` | Reopened by resident; resets `resolved_at` |
| `CANCELLED` | *None* | Terminal state |

---

## 3. Deterministic Safety Escalation & Priority Lock

To protect resident life and physical property, safety hazard detection executes **before** and **independently of** any AI classification.

### Safety Invariants
1. Evaluates ticket title and description against multilingual hazard patterns (English, Hindi, Marathi).
2. If any hazard is detected, `safety_escalated` is set to `True`, and priority is **forced to `CRITICAL`**.
3. **AI cannot downgrade or override a safety escalation.** The safety flag is server-authoritative.
4. **Backend Priority Lock**: Any API attempt to change a safety-escalated ticket's priority below `CRITICAL` is rejected with `400 Bad Request`.
5. Operates completely offline with zero external network or model dependency.

### Covered Multilingual Hazard Patterns

| Hazard Category | English Triggers | Hindi Triggers | Marathi Triggers |
|---|---|---|---|
| **Fire & Smoke** | `fire`, `smoke`, `flames`, `burning`, `explosion` | `आग`, `धुआं`, `जल रहा`, `विस्फोट` | `आगीची`, `धूर`, `स्फोट` |
| **Gas Leak** | `gas leak`, `lpg leak`, `gas smell`, `cylinder leak` | `गैस लीक`, `गैस की बदबू`, `सिलेंडर लीक` | `गॅस गळती`, `गॅसचा वास` |
| **Lift Entrapment** | `trapped in lift`, `elevator stuck`, `person stuck` | `लिफ्ट में फंसा`, `लिफ्ट अटक` | `लिफ्ट अडकली`, `लिफ्टमध्ये अडकले` |
| **Electrical Shock** | `short circuit`, `sparking`, `electric shock`, `live wire` | `शॉर्ट सर्किट`, `स्पार्किंग`, `करेंट`, `खुला तार` | `विजेचा धक्का`, `विजेची तार`, `शॉक` |
| **Structural Collapse** | `ceiling collapse`, `wall collapse`, `debris falling` | `छत गिर`, `दीवार गिर`, `मलबा गिर` | `पडझड`, `छत कौसळली`, `भिंत पडली` |
| **Severe Flooding** | `severe flooding`, `water in meter room` | `मीटर रूम में पानी`, `लिफ्ट में पानी` | `पाणी मीटर रूम` |

---

## 4. AI-Assisted Advisory Triage Engine (Google Gemini)

AI classification assists township staff by predicting issue categories, operational priorities, and summarizations.

### Key Rules
- **Asynchronous Architecture**: Complaint creation returns immediately with `ai_status = PENDING`. An outbox event `complaint.classify` is emitted to `QUEUE_COMPLAINT_AI_JOBS`. Complaint creation never makes synchronous external API or LLM calls.
- **Worker Execution & Idempotency**: `ComplaintAIHandler` queries the complaint with row-locking (`with_for_update()`). If the complaint is already in `COMPLETED` or `FALLBACK` state, duplicate events are skipped immediately without repeated model invocations.
- **Resident Privacy & Data Minimization**: Prior to calling external LLM providers, `minimize_resident_data()` redacts resident phone numbers (`[PHONE_REDACTED]`), email addresses (`[EMAIL_REDACTED]`), apartment/flat/tower identifiers (`[UNIT_REDACTED]`), resident self-intro names (`[NAME_REDACTED]`), and credentials. Internal database UUIDs (user IDs, flat IDs, society IDs) are never transmitted to external AI models.
- **Structured Schema & Generation Config**: Gemini API invocations supply `responseSchema` (matching `AIClassificationOutput` properties and enum values) with `responseMimeType: "application/json"`.
- **Pydantic Validation**: Responses strictly conform to `AIClassificationOutput` schema:
  - `suggested_category`: ComplaintCategory
  - `suggested_priority`: ComplaintPriority
  - `confidence_score`: float (0.0 - 1.0)
  - `summary`: string (max 120 chars)
  - `urgency_reason`: string
  - `reasoning`: string (step-by-step rationale)
  - `requires_human_review`: boolean
- **AI_ENABLED Control**: If `settings.AI_ENABLED` is `False`, all calls deterministically use `DeterministicAIClassifierProvider` with zero network or external API traffic.
- **Prompt Injection Defense**: Sanitizes inputs (strips control characters, redacts sensitive tokens) and instructs the model that complaint text is untrusted data that must never be executed as instructions.
- **Deterministic Offline Fallback**: If `GEMINI_API_KEY` is absent, or on network timeout / quota 429, the system gracefully falls back to `DeterministicAIClassifierProvider`, ensuring 100% CI reproducibility and zero paid API requirement.
- **Advisory Isolation**: AI suggestions are stored in distinct advisory columns (`ai_suggested_*`, `ai_status`, `ai_reasoning`, `ai_provider`, `ai_model`, `ai_processed_at`) and never override human decisions. Authoritative priority and category are server-authoritative and never overwritten by the AI worker.

---

## 5. Service Level Agreement (SLA) Matrix

All deadlines are calculated in UTC and displayed in `Asia/Kolkata` local time:

| Priority | First Response SLA | Resolution SLA | Typical Triggers |
|---|---|---|---|
| **CRITICAL** | 5 Minutes | 2 Hours | Safety hazards, gas leaks, lift entrapment, fire |
| **HIGH** | 30 Minutes | 8 Hours | Total flat power loss, major plumbing burst |
| **MEDIUM** | 4 Hours | 48 Hours | Standard plumbing/electrical repairs, seepage |
| **LOW** | 12 Hours | 5 Days (120h) | Minor squeaks, cosmetic touch-ups, aesthetic issues |

### Priority SLA Recalculation
When staff updates a ticket's priority via `/api/v1/complaints/helpdesk/{id}/priority`:
- The resolution deadline is recalculated starting from the current UTC time (`utc_now()`).
- If `first_response_at` has already been recorded, `first_response_deadline` is preserved.

---

## 6. Workload-Based Auto-Assignment Algorithm

When a ticket is created:
1. Query active users holding `RoleType.HELPDESK` in the complaint's `society_id`.
2. Count open tickets (`ASSIGNED`, `IN_PROGRESS`, `AWAITING_RESIDENT`, `REOPENED`) assigned to each staff member.
3. Select the staff member with the lowest open ticket count.
4. Deterministic tie-breaker: sort by `User.id`.
5. If no active helpdesk staff exists, ticket is set to `TRIAGED` (unassigned).

---

## 7. Two-Phase Attachment Lifecycle & Storage Contract

Attachment metadata is managed via `complaint_attachments`:
- **State Machine**: `PENDING` ──► `UPLOADED` (or `FAILED`).
- **Initiation**: `POST /attachments` registers a `PENDING` record and returns a presigned S3 PUT URL (1-hour validity).
- **Completion Verification**: `POST /attachments/{id}/complete` verifies object existence, declared file size (<= 5MB, non-empty, matching declared size within tolerance), and MIME type via `verify_object_metadata()`. If verification fails, the attachment is transitioned to `FAILED`, a 400 error is returned, and unverified files are never made accessible. On success, transitions status to `UPLOADED` and logs an audit activity.
- **Unverified Attachment Shield**: Unverified (`PENDING` or `FAILED`) attachments are strictly omitted from complaint detail views, and download URLs are never generated for them.
- **Frontend Safe Upload**: The web client verifies the direct presigned PUT HTTP status (`uploadRes.ok`). If the direct upload fails, the completion endpoint is never called and an explicit error is raised.
- **Fail-Closed Security**: In production and staging, `S3_ATTACHMENTS_BUCKET_NAME` must be configured; silent fallback to mock storage is strictly blocked.

---

## 8. Running Automated Tests Locally

```bash
# Run complaints domain unit & integration tests
cd services/api
python -m pytest tests/test_complaints_endpoints.py -v

# Run entire backend test suite
python -m pytest tests/ -v

# Run frontend tests
cd ../../apps/web
npm test -- --run

# Run web production build
npm run build
```
