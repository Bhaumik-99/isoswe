"""Technical Design Deliverables Generator

Generates:
1. docs/Technical_Design_Document.docx (Microsoft Word deliverable)
2. docs/Technical_Design_Document.pdf (Adobe PDF deliverable)
3. docs/technical_design_document.md (Markdown deliverable)
4. submission_package.zip (Single submission package containing deployment.md & TDD)
"""

import os
import zipfile
from datetime import datetime


def get_tdd_markdown(docs_dir: str) -> str:
    """Reads existing technical_design_document.md if available, otherwise returns fallback."""
    md_path = os.path.join(docs_dir, "technical_design_document.md")
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def generate_docx(output_path: str) -> None:
    """Generates the Technical Design Document in Microsoft Word (.docx) format."""
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    doc = Document()

    # Page Margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Document Title
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = p_title.add_run(
        "TECHNICAL DESIGN DOCUMENT\nTownship Operations Platform"
    )
    run_title.font.name = "Arial"
    run_title.font.size = Pt(22)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(30, 58, 138)  # Deep Navy

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = p_sub.add_run(
        "Pune Gated Township (2,400 Flats · 28 Towers · 180 Staff)\nPhase 8: Complete Operations, Facility Booking, Communications & Security"
    )
    run_sub.font.name = "Arial"
    run_sub.font.size = Pt(12)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(100, 116, 139)

    doc.add_paragraph()  # Spacing

    # Metadata Table
    table = doc.add_table(rows=6, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    metadata = [
        ("Platform Name", "Township Operations Platform (township-ops)"),
        ("Architecture Version", "Phase 8 Complete (Official Notices & Hardening)"),
        ("Date", datetime.now().strftime("%B %d, %Y")),
        (
            "Security Compliance",
            "SOC 2 Type II Invariants, OWASP Top 10, CWE-1236 Shield, Row-Level Security",
        ),
        (
            "Target Deployment",
            "Supabase Cloud (ap-south-1 Mumbai) + AWS Serverless Lambda (Option B)",
        ),
        (
            "Core Architectural Decisions",
            "ADRs 001-010: PgBouncer pool_size=1, Transactional Outbox, Integer Paise Arithmetic",
        ),
    ]
    for idx, (k, v) in enumerate(metadata):
        cell_k = table.cell(idx, 0)
        cell_v = table.cell(idx, 1)
        cell_k.text = k
        cell_v.text = v
        cell_k.paragraphs[0].runs[0].font.bold = True
        cell_k.paragraphs[0].runs[0].font.size = Pt(10)
        cell_v.paragraphs[0].runs[0].font.size = Pt(10)

    doc.add_page_break()

    # Section 1
    doc.add_heading("1. Executive Summary & Problem Context", level=1)
    doc.add_paragraph(
        "The platform serves a premier gated township in Pune, Maharashtra comprising 2,400 residential apartments "
        "across 28 towers, managed by 180 on-site facility personnel. Maintenance is assessed at ₹6.50 per sq. ft. per month "
        "(yielding ₹7,475/mo for standard 1,150 sq. ft. apartments). Residents execute transactions across UPI, NEFT/RTGS, "
        "and physical cheques. This technical design document formalizes the production-grade architecture that resolves "
        "high-volume financial reconciliation, automated SLA service desk management, tenant registry lifecycle tracking, "
        "gate security operations with offline tablet sync, multi-channel resident alerts, official township circulars, and "
        "race-condition-free amenity slot reservations."
    )

    # Section 2
    doc.add_heading("2. Multi-Tenant Architecture & Security Model", level=1)
    doc.add_paragraph(
        "The system enforces strictly two application roles (RESIDENT and HELPDESK) across all APIs. "
        "Fine-grained operational permissions govern specific staff actions: COMPLAINT_MANAGE, BANK_IMPORT, "
        "RECONCILIATION_REVIEW, BILLING_MANAGE, COMMITTEE_REPORT_READ, and GATE_OPERATIONS. Database isolation is guaranteed via "
        "PostgreSQL FORCE ROW LEVEL SECURITY (RLS) on all financial, tenant, visitor, notice, and amenity tables, ensuring "
        "cross-society tenant isolation is enforced at the database engine level."
    )

    # Section 3
    doc.add_heading("3. Core Subsystem Implementations", level=1)

    doc.add_heading("3.1 Identity & Resident Registry", level=2)
    doc.add_paragraph(
        "Manages owner, tenant, and family member flat allotments. Tenant leases enforce strict lease duration "
        "boundaries (valid_until >= valid_from). All phone numbers are validated to E.164 (+91XXXXXXXXXX) format. "
        "Every onboarding and status transition generates an immutable audit record."
    )

    doc.add_heading("3.2 Maintenance Billing & Immutable Financial Ledger", level=2)
    doc.add_paragraph(
        "Financial computations are conducted entirely in 64-bit integer paise (₹1.00 = 100 paise) preventing precision "
        "loss. Invoices snapshot historical unit rates. An append-only double-entry financial ledger records all invoice debits, "
        "payment credits, and late fee assessments. The late-fee engine supports Flat Fee, Monthly Percentage, and Daily "
        "Simple Interest calculated as (unpaid * amount_or_rate_bps * days + 1825000) // 3650000. Concurrent payment allocation "
        "enforces row-level locking (SELECT ... FOR UPDATE) and mandatory Idempotency-Key headers."
    )

    doc.add_heading("3.3 Automated Bank Statement Reconciliation", level=2)
    doc.add_paragraph(
        "Bank statement imports undergo concurrent SHA-256 deduplication. An intelligent narration normalizer extracts UPI VPAs "
        "and fuzzy matches apartment identifiers (Tower + Flat). Confident matches (>= 90%) are promoted to reconciliation matches. "
        "Settlement enforces two-person maker-checker governance before posting financial allocations."
    )

    doc.add_heading("3.4 Service Desk Governance & Safety Alerts", level=2)
    doc.add_paragraph(
        "Complaints are auto-assigned to active staff via round-robin workload leveling. Emergency tickets feature a persistent "
        "duty-manager queue with 15-minute response SLA. Staff can correct miscategorized tickets and link duplicates while "
        "preserving the complete audit trail."
    )

    doc.add_heading("3.5 Committee Governance Dashboard", level=2)
    doc.add_paragraph(
        "Provides real-time SQL aggregation across all 2,400 flats without memory limit constraints. Generates arrears "
        "ageing buckets (0-30, 31-60, 61-90, 90+ days), tower collection performance metrics, and CSV exports protected "
        "against formula injection (CWE-1236)."
    )

    doc.add_heading("3.6 Gate & Visitor Management with Offline Sync", level=2)
    doc.add_paragraph(
        "Decoupled approval and entry state machines. Pre-approved guest passes (GP-XXXX) are generated using CSPRNG salt/hash storage. "
        "Offline-first tablet architecture captures walk-in visitors into IndexedDB and synchronizes reconnection batches using nested "
        "database savepoints. Visitor photos are stored in private KMS S3 with short-lived presigned URLs and enforced 90-day retention."
    )

    doc.add_heading("3.7 Multi-Channel Communications & Official Notices", level=2)
    doc.add_paragraph(
        "Outbox-driven notification engine evaluates user channel preferences (In-App, Email, SMS) with exponential backoff and PII masking. "
        "Official township circulars and maintenance advisories support granular targeting by society, tower, and flat, scheduled publishing, "
        "resident read tracking, and emergency broadcast outbox escalation."
    )

    doc.add_heading("3.8 Amenity & Facility Booking Management", level=2)
    doc.add_paragraph(
        "Discrete time-slot booking engine with Asia/Kolkata facility timezone awareness, PostgreSQL row locking (SELECT ... FOR UPDATE) "
        "for concurrency protection, 15-minute payment expiration locks, fee immutability, staff maintenance blocking, and transparent "
        "cancellation policies."
    )

    # Section 4
    doc.add_heading("4. Cloud Infrastructure & DevOps Pipeline (Option B)", level=1)
    doc.add_paragraph(
        "The infrastructure is codified using AWS CDK v2 in Python, pairing Supabase Cloud (PostgreSQL 16 Multi-AZ, Row-Level Security, "
        "and PgBouncer shared transaction pooler on port 6543) with AWS Serverless (FastAPI Lambda via Mangum, Amazon API Gateway, "
        "Amazon SQS with DLQs, Amazon S3 KMS, and CloudFront CDN). This architecture eliminates costly VPC NAT Gateways while "
        "ensuring predictable cloud expenditure and zero lost messages. Automated CI/CD pipelines in GitHub Actions enforce Ruff, "
        "Mypy strict typing, Pytest unit/integration/concurrency tests, Vitest, Gitleaks, and CodeQL SAST."
    )

    doc.save(output_path)
    print(f"Generated DOCX: {output_path}")


def generate_pdf(output_path: str) -> None:
    """Generates the Technical Design Document in Adobe PDF (.pdf) format."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    pdf = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54,
    )
    styles = getSampleStyleSheet()

    # Custom Styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1E3A8A"),
        alignment=1,  # Center
    )
    subtitle_style = ParagraphStyle(
        "DocSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#475569"),
        alignment=1,
    )
    h1_style = ParagraphStyle(
        "DocH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "DocH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "DocBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=6,
    )

    story = []

    # Title & Subtitle
    story.append(Spacer(1, 15))
    story.append(Paragraph("TECHNICAL DESIGN DOCUMENT", title_style))
    story.append(
        Paragraph(
            "Township Operations Platform — Phase 8 Complete Release", title_style
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "Pune Gated Township (2,400 Apartments · 28 Towers · 180 Facility Staff)",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 15))

    # Summary Table
    meta_data = [
        [
            Paragraph("<b>Target System:</b>", body_style),
            Paragraph("Pune Gated Township (2,400 Flats, 28 Towers, 180 Staff)", body_style),
        ],
        [
            Paragraph("<b>Architecture Model:</b>", body_style),
            Paragraph("Option B: Supabase PostgreSQL 16 (RLS) + AWS Serverless Lambda", body_style),
        ],
        [
            Paragraph("<b>Security & Roles:</b>", body_style),
            Paragraph(
                "Strict 2-Role RBAC (RESIDENT, HELPDESK) + Granular Permissions + Force RLS",
                body_style,
            ),
        ],
        [
            Paragraph("<b>Financial Ledger:</b>", body_style),
            Paragraph(
                "64-bit Integer Paise + Append-Only Double-Entry Engine + Trigger Immutability",
                body_style,
            ),
        ],
        [
            Paragraph("<b>Gate & Communications:</b>", body_style),
            Paragraph(
                "Offline IndexedDB Tablet Sync + 90-Day S3 Photo Retention + Targeted Circulars",
                body_style,
            ),
        ],
        [
            Paragraph("<b>Amenity Reservations:</b>", body_style),
            Paragraph(
                "Asia/Kolkata Timezone + Row-Locking Concurrency Safety + 15m Expiration Lock",
                body_style,
            ),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[150, 350])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 15))

    # Section 1
    story.append(Paragraph("1. System Overview & Problem Statement", h1_style))
    story.append(
        Paragraph(
            "The platform coordinates township management across 2,400 apartments in Pune, Maharashtra. "
            "It features automated maintenance billing, multi-channel payment reconciliation (UPI/NEFT/Cheque), "
            "resident registry management, SLA-driven complaint ticketing, committee executive reporting, "
            "offline-first gate security tablet synchronization, multi-channel notification dispatch, official township notices, "
            "and race-condition-free amenity slot reservations. All financial operations utilize strict integer paise arithmetic.",
            body_style,
        )
    )

    # Section 2
    story.append(Paragraph("2. Identity, RBAC & Multi-Tenant Security", h1_style))
    story.append(
        Paragraph(
            "The platform maintains strictly two application roles: RESIDENT and HELPDESK. Fine-grained permissions "
            "(COMPLAINT_MANAGE, BANK_IMPORT, RECONCILIATION_REVIEW, BILLING_MANAGE, COMMITTEE_REPORT_READ, GATE_OPERATIONS) "
            "govern operational capabilities. Multi-tenant isolation is enforced at the database engine level via PostgreSQL "
            "FORCE ROW LEVEL SECURITY across all application tables.",
            body_style,
        )
    )

    # Section 3
    story.append(Paragraph("3. Core Subsystem Architectural Specifications", h1_style))

    story.append(Paragraph("3.1 Resident Registry & Flat Allotments", h2_style))
    story.append(
        Paragraph(
            "Tracks Owner, Tenant, and Family Member memberships. Tenant leases enforce date validation (valid_until >= valid_from). "
            "Expired tenant leases automatically forfeit flat data access. Mandatory E.164 phone normalization is enforced.",
            body_style,
        )
    )

    story.append(
        Paragraph("3.2 Billing Engine & Append-Only Financial Ledger", h2_style)
    )
    story.append(
        Paragraph(
            "Invoices snapshot unit rates at generation. Balances are derived dynamically from an append-only double-entry "
            "financial ledger. The late-fee engine supports Flat Fee, Monthly Percentage, and Daily Simple Interest in basis points. "
            "Row-level locking (SELECT ... FOR UPDATE) and idempotency keys protect payment allocations.",
            body_style,
        )
    )

    story.append(Paragraph("3.3 UPI-Aware Automated Bank Reconciliation", h2_style))
    story.append(
        Paragraph(
            "Bank statement imports undergo concurrent SHA-256 deduplication. An intelligent narration normalizer extracts UPI VPAs "
            "and fuzzy matches apartment identifiers. Matches with >= 90% confidence are promoted. A maker-checker verification modal "
            "enforces separation of duties prior to financial ledger settlement.",
            body_style,
        )
    )

    story.append(Paragraph("3.4 Service Desk & Persistent Safety Alerts", h2_style))
    story.append(
        Paragraph(
            "Complaints are auto-assigned via round-robin workload leveling. Emergency tickets feature a persistent duty-manager "
            "queue with a 15-minute response SLA. Staff can correct miscategorized tickets and link duplicates while preserving audit history.",
            body_style,
        )
    )

    story.append(
        Paragraph("3.5 Gate Management, Offline Sync & Photo Retention", h2_style)
    )
    story.append(
        Paragraph(
            "Decoupled approval and entry state machines. Salted guest passes (GP-XXXX). Offline-first tablet architecture "
            "using IndexedDB with replay protection. 90-day visitor photo retention enforced via S3 lifecycle and purge workers.",
            body_style,
        )
    )

    story.append(
        Paragraph("3.6 Multi-Channel Communications & Official Notices", h2_style)
    )
    story.append(
        Paragraph(
            "Outbox-driven notification engine over Amazon SQS queues with DLQs. Granular targeting for official notices "
            "by society, tower, and flat. Supports draft/publish states, auto-expiry, pinning, read tracking, and emergency outbox broadcast.",
            body_style,
        )
    )

    story.append(
        Paragraph("3.7 Amenity Booking & Concurrency Control", h2_style)
    )
    story.append(
        Paragraph(
            "Discrete time-slot booking engine with Asia/Kolkata timezone awareness, PostgreSQL row locking (SELECT ... FOR UPDATE) "
            "preventing capacity oversubscription, 15-minute payment expiration lock, cancellation policies, and staff maintenance blocking.",
            body_style,
        )
    )

    # Section 4
    story.append(Paragraph("4. Deployment & Infrastructure Architecture (Option B)", h1_style))
    story.append(
        Paragraph(
            "AWS CDK v2 provisions AWS Serverless compute (FastAPI on AWS Lambda with Mangum, Amazon API Gateway, Amazon SQS + DLQs, "
            "KMS-encrypted S3, and CloudFront CDN) paired with Supabase PostgreSQL 16 (Multi-AZ, RLS, PgBouncer port 6543 pooler). "
            "CI/CD pipelines enforce Ruff, Mypy strict typing, Pytest unit/integration/concurrency tests, Vitest, Gitleaks, and CodeQL SAST.",
            body_style,
        )
    )

    pdf.build(story)
    print(f"Generated PDF: {output_path}")


def create_submission_zip(
    zip_path: str, files_to_include: list[tuple[str, str]]
) -> None:
    """Creates a single submission ZIP containing deployment.md and Technical Design Documents."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src_path, arc_name in files_to_include:
            if os.path.exists(src_path):
                zf.write(src_path, arcname=arc_name)
                print(f"Added to ZIP: {arc_name} from {src_path}")
            else:
                print(f"Warning: File {src_path} not found for ZIP archive.")
    print(f"Created Submission Package ZIP: {zip_path}")


def main() -> None:
    docs_dir = os.path.join(os.getcwd(), "docs")
    os.makedirs(docs_dir, exist_ok=True)

    md_path = os.path.join(docs_dir, "technical_design_document.md")
    if not os.path.exists(md_path):
        print(f"Warning: {md_path} not found.")
    else:
        print(f"Verified Markdown: {md_path}")

    docx_path = os.path.join(docs_dir, "Technical_Design_Document.docx")
    generate_docx(docx_path)

    pdf_path = os.path.join(docs_dir, "Technical_Design_Document.pdf")
    generate_pdf(pdf_path)

    # Create submission_package.zip at repository root
    zip_path = os.path.join(os.getcwd(), "submission_package.zip")
    files_to_zip = [
        ("deployment.md", "deployment.md"),
        (docx_path, "docs/Technical_Design_Document.docx"),
        (pdf_path, "docs/Technical_Design_Document.pdf"),
        (md_path, "docs/technical_design_document.md"),
    ]
    create_submission_zip(zip_path, files_to_zip)


if __name__ == "__main__":
    main()
