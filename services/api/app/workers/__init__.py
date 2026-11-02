"""Background Domain Workers Package

Imports and registers all message consumers for the 5 main platform queues:
1. Billing Worker (QUEUE_BILLING_JOBS)
2. Payment Worker (QUEUE_PAYMENT_EVENTS)
3. Reconciliation Worker (QUEUE_RECONCILIATION_JOBS)
4. Complaint AI Worker (QUEUE_COMPLAINT_AI_JOBS)
5. Notification Worker (QUEUE_NOTIFICATION_JOBS)
6. Platform Health Worker (Synthetic verification)
"""

import app.workers.billing_worker  # noqa: F401
import app.workers.complaint_worker  # noqa: F401
import app.workers.health_worker  # noqa: F401
import app.workers.notification_worker  # noqa: F401
import app.workers.payment_worker  # noqa: F401
import app.workers.reconciliation_worker  # noqa: F401
