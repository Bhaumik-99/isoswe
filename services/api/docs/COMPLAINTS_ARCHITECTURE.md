# Complaints Management, Helpdesk Operations & AI-Assisted Triage

## Overview

Phase 3 introduces an enterprise-grade complaints and facility operations module tailored for high-density gated townships (2,400 apartments across 28 towers, maintained by 180 facility staff).

The architecture enforces:
- **Server-Authoritative Lifecycle**: Strict state machine transitions preventing invalid operational bypasses.
- **Deterministic Multilingual Safety Escalation**: Immediate physical safety hazard recognition (English, Hindi, Marathi) executing *before* AI classification.
- **AI-Assisted Advisory Triage**: Automated category and priority suggestions with confidence scores and offline deterministic fallback.
- **Workload-Based Auto-Assignment**: Automatic load-balanced ticket routing to active helpdesk staff within the society.
- **Public vs. Internal Note Separation**: Strict privacy boundary ensuring resident views never leak internal staff discussions.
- **Private Presigned Object Storage**: S3/mock attachment storage with 5MB limits and MIME type enforcement.
- **Immutable Audit Trail & Outbox**: Full operational traceability and event-driven integration.

---

## 1. System Scale & Security Model

The township operations platform strictly implements a two-role security boundary:
- `RESIDENT`: Scoped strictly to flats where the user holds an active approved membership. Can submit tickets, post public comments, attach photos, rate resolved tickets, and reopen within 7 days.
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

## 3. Deterministic Safety Escalation Engine

To protect resident life and physical property, safety hazard detection executes **before** and **independently of** any AI classification.

### Safety Invariants
1. Evaluates ticket title and description against multilingual hazard patterns (English, Hindi, Marathi).
2. If any hazard is detected, `safety_escalated` is set to `True`, and priority is **forced to `CRITICAL`**.
3. **AI cannot downgrade or override a safety escalation.** The safety flag is server-authoritative.
4. Operates completely offline with zero external network or model dependency.

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

## 4. AI-Assisted Advisory Triage Engine

AI classification assists township staff by predicting issue categories, operational priorities, and summarizations.

### Key Rules
- AI suggestions are stored in distinct advisory columns (`ai_suggested_category`, `ai_suggested_priority`, `ai_confidence_score`, `ai_summary`, `ai_urgency_reason`).
- AI recommendations never overwrite human or safety decisions.
- Completely deterministic offline fallback (`DeterministicAIClassifierProvider`) ensures 100% CI reproducibility without paid API keys.
- Evaluates token-based lexical similarity to identify duplicate candidates across the society.

---

## 5. Service Level Agreement (SLA) Matrix

All deadlines are calculated from `created_at` (or `reopened_at`) in UTC and displayed in `Asia/Kolkata` local time:

| Priority | First Response SLA | Resolution SLA | Typical Triggers |
|---|---|---|---|
| **CRITICAL** | 5 Minutes | 2 Hours | Safety hazards, gas leaks, lift entrapment, fire |
| **HIGH** | 30 Minutes | 8 Hours | Total flat power loss, major plumbing burst |
| **MEDIUM** | 4 Hours | 48 Hours | Standard plumbing/electrical repairs, seepage |
| **LOW** | 12 Hours | 5 Days (120h) | Minor squeaks, cosmetic touch-ups, aesthetic issues |

### First Response Tracking
`first_response_at` is automatically recorded when:
1. Helpdesk staff posts the first comment/reply on the ticket, OR
2. Ticket status is updated to `IN_PROGRESS` or `RESOLVED`.

---

## 6. Workload-Based Auto-Assignment Algorithm

When a ticket is created:
1. Query active users holding `RoleType.HELPDESK` in the complaint's `society_id`.
2. Count open tickets (`ASSIGNED` or `IN_PROGRESS`) assigned to each staff member.
3. Select the staff member with the lowest open ticket count.
4. Deterministic tie-breaker: sort by `User.id`.
5. If no active helpdesk staff exists, ticket is set to `TRIAGED` (unassigned).

---

## 7. Privacy & Communication Model

Complaints support two communication channels in `complaint_comments`:
- **Public Comments (`is_internal = False`)**: Visible to both resident and helpdesk staff.
- **Internal Helpdesk Notes (`is_internal = True`)**: Strictly confidential to facility staff. Residents querying `/complaints/me/{id}` receive responses where internal notes are completely stripped.

---

## 8. Secure Attachment Storage Contract

Attachment metadata is managed via `complaint_attachments`:
- **File Constraints**: Maximum size **5 MB**; allowed MIME types: `image/jpeg`, `image/png`, `image/webp`.
- **Private S3 / Mock Storage**: Files are never publicly readable. Uploads and downloads use expiring presigned URLs (1 hour validity).
- **IDOR Protection**: Storage keys use randomized UUIDs (`complaints/{society_id}/{complaint_id}/{uuid}.{ext}`).

---

## 9. Running Automated Tests Locally

```bash
# Run complaints domain unit & integration tests
cd services/api
python -m pytest tests/test_complaints_endpoints.py -v

# Run entire backend test suite
python -m pytest tests/ -v

# Run frontend tests
cd ../../apps/web
npm test -- --run
```
