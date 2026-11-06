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

# 1. Generate Markdown Deliverable
TDD_CONTENT_MARKDOWN = """# Technical Design Document (TDD)
# Township Operations Platform
**Target Scope**: 2,400 Apartments | 28 Towers | 180 Facility Staff | Pune, Maharashtra  
**Document Revision**: Phase 5 Complete  
**Date**: November 2026  
**Status**: APPROVED & IMPLEMENTED  

---

## 1. Executive Summary & Problem Context

The Township Operations Platform is an enterprise-grade multi-tenant property governance system purpose-built for a large-scale residential gated community in Pune, Maharashtra comprising:
- **2,400 residential flats** distributed across **28 residential towers**.
- **180 on-site facility management staff** across helpdesk, electrical, plumbing, civil, security, and administrative teams.
- **₹6.50 per sq. ft. per month** standard maintenance billing (e.g., ₹7,475/month for a 1,150 sq. ft. 2BHK flat).
- **Payment channels**: Cheque, NEFT/RTGS bank transfer, and UPI.
- **Key operational challenges**: Automated invoice reconciliation against noisy bank narrations, tenant onboarding with lease tracking, SLA enforcement for emergency complaints, and committee-level financial governance.

---

## 2. Architecture & Multi-Tenancy Principles

### 2.1 Two-Role Strict RBAC with Granular Permissions
The platform enforces strictly two application roles at the identity layer:
- `RESIDENT`: Scoped strictly to active, approved flat memberships.
- `HELPDESK`: Authorized facility management staff.

Operational capabilities are granted via granular permissions:
- `COMPLAINT_MANAGE`: Triage, update, assign, and resolve complaint tickets.
- `BANK_IMPORT`: Upload and confirm bank statement CSV files.
- `RECONCILIATION_REVIEW`: Propose and approve financial matching allocations.
- `BILLING_MANAGE`: Configure billing cycles, generate monthly invoice runs, and apply late fees.
- `COMMITTEE_REPORT_READ`: Explicitly granted permission enabling access to executive financial summaries, ageing arrears, and CSV export.

### 2.2 PostgreSQL Row-Level Security (RLS)
Every financial and transactional table enforces `FORCE ROW LEVEL SECURITY`:
- Financial tables (`invoices`, `payments`, `payment_allocations`, `financial_ledger_entries`, `bank_transactions`) enforce tenant isolation by `society_id`.
- Residents can read only records bound to flats for which they hold an active, non-expired `FlatMembership`.
- Staff access is strictly restricted to assigned societies via security definer helper `public.is_helpdesk_for_society(society_id)`.

---

## 3. Core Domain Subsystems

### 3.1 Identity & Resident Registry
- **Membership Types**: `OWNER`, `TENANT`, `FAMILY_MEMBER`.
- **Lease Window Enforcement**: Leases require `valid_from` and `valid_until` with validation ensuring end date is not prior to start date. Expired tenant leases automatically forfeit flat data access.
- **Resident Onboarding**: Phone numbers normalized to international E.164 (`+91XXXXXXXXXX`). Self-registration requests enter `PENDING` state until staff verification.
- **Audit Logging**: Every membership state change records structured audit events (`identity.membership.created`, `identity.membership.updated`, `identity.membership.approved`, `identity.membership.terminated`).

### 3.2 Maintenance Billing & Append-Only Financial Ledger
- **Integer Paise Arithmetic**: All monetary quantities are stored as 64-bit BigInt paise (₹1.00 = 100 paise) preventing floating-point rounding discrepancies.
- **Formula**: `area_sqft * rate_paise_per_sqft` (1,150 sq. ft. * 650 paise = 747,500 paise = ₹7,475.00).
- **Snapshot Pricing**: Generated invoices snapshot current rates, shielding historical obligations from future tariff modifications.
- **Append-Only Ledger**: Balances are calculated dynamically from immutable ledger entries (`INVOICE`, `PAYMENT`, `ADJUSTMENT`, `LATE_FEE`). Updates or deletes to ledger entries are blocked by database triggers.
- **Late-Fee Engine**: Society bye-law policy evaluation supporting Flat Fee (paise), Monthly Percentage (basis points), and Daily Simple Interest (`(unpaid * amount_or_rate_bps * days + 1825000) // 3650000`).

### 3.3 Automated Bank Statement Reconciliation
- **Deduplication**: Concurrency-safe SHA-256 fingerprinting on `(society_id, transaction_date, amount_paise, narration)` with unique database constraint.
- **UPI VPA Normalization**: Regex extraction of UPI VPAs from banker narrations (`UPI/123456789012/PAYMENT/resident@okhdfcbank/...`).
- **Confidence Scoring & Promotion**:
  - Exact UPI VPA mapping match: `confidence = 0.98` -> Auto-promoted to match.
  - Narration containing exact Tower + Flat + Amount: `confidence = 0.95` -> Promoted to match.
  - Partial match: Suggestion created for manual review.
- **Financial Maker-Checker**: Mandatory separation of duties. Users cannot approve proposals they submitted; requires `PENDING_APPROVAL` status before financial settlement.

### 3.4 Complaints & Service Desk
- **Auto-Assignment**: Round-robin assignment to active staff in the society with the fewest open tickets.
- **SLA Tracking**:
  - First Response SLA (e.g. 15 minutes for EMERGENCY, 2 hours for HIGH).
  - Resolution SLA (e.g. 4 hours for EMERGENCY, 24 hours for HIGH).
- **Category Correction & Duplication**: Staff can reclassify misrouted categories while preserving `original_category`, and link duplicate complaints to a primary parent ticket.
- **Persistent Safety Alerts**: Dedicated high-priority emergency queue for urgent health/safety hazards.

### 3.5 Committee Financial Governance
- **SQL Aggregates**: Zero memory limit aggregation over all 2,400 flats directly in database queries.
- **Ageing Arrears Buckets**: Live segregation of outstanding receivables:
  - 0-30 Days (Current)
  - 31-60 Days (Overdue)
  - 61-90 Days (Delinquent)
  - 90+ Days (Critical Recovery)
- **Tower Breakdown**: Tower-by-tower collection percentages and complaint volume.
- **CSV Export Sanitization**: Formula injection mitigation (CWE-1236) prepending single-quote `'` to cells starting with `=`, `+`, `-`, `@`, `\\t`, or `\\r`.

### 3.6 Offline-Capable Resident PWA
- Progressive Web Application with responsive layout, app shell caching via `sw.js`, and installable web manifest.
- 1-tap quick actions: Pay Maintenance Bill, Raise Urgent Complaint.

---

## 4. Infrastructure & Deployment Architecture

- **AWS CDK v2**: Infrastructure-as-code deploying VPC, RDS PostgreSQL 16 Multi-AZ, ECS Fargate API container, and CloudFront S3 SPA distribution.
- **Secrets Management**: AWS Secrets Manager with fail-closed production validation.
- **CI/CD Pipeline**: GitHub Actions running Ruff linting, Mypy strict typing, Pytest unit/integration tests, Vitest frontend tests, Gitleaks secret scanning, and CodeQL SAST.
"""


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
        "Pune Gated Township (2,400 Flats · 28 Towers · 180 Staff)\nPhase 5: Financial Governance, Automated Reconciliation & PWA Handover"
    )
    run_sub.font.name = "Arial"
    run_sub.font.size = Pt(12)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(100, 116, 139)

    doc.add_paragraph()  # Spacing

    # Metadata Table
    table = doc.add_table(rows=5, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    metadata = [
        ("Platform Name", "Isoswe Township Operations Platform"),
        ("Architecture Version", "Phase 5 Core Production Release"),
        ("Date", datetime.now().strftime("%B %d, %Y")),
        (
            "Security Compliance",
            "SOC 2 Type II Invariants, OWASP Top 10, CWE-1236 Shield",
        ),
        ("Target Deployment", "AWS ap-south-1 (Mumbai) / ECS Fargate + RDS Multi-AZ"),
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
        "and committee financial governance."
    )

    # Section 2
    doc.add_heading("2. Multi-Tenant Architecture & Security Model", level=1)
    doc.add_paragraph(
        "The system enforces strictly two application roles (RESIDENT and HELPDESK) across all APIs. "
        "Fine-grained operational permissions govern specific staff actions: COMPLAINT_MANAGE, BANK_IMPORT, "
        "RECONCILIATION_REVIEW, BILLING_MANAGE, and COMMITTEE_REPORT_READ. Database isolation is guaranteed via "
        "PostgreSQL FORCE ROW LEVEL SECURITY (RLS) on all financial tables, ensuring cross-society tenant isolation "
        "is enforced at the database kernel."
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
        "Simple Interest calculated as (unpaid * amount_or_rate_bps * days + 1825000) // 3650000."
    )

    doc.add_heading("3.3 UPI-Aware Automated Bank Reconciliation", level=2)
    doc.add_paragraph(
        "Bank statement CSVs undergo concurrent SHA-256 deduplication. An intelligent narration normalizer extracts UPI VPAs "
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

    doc.add_heading("3.6 Offline-Capable Resident PWA", level=2)
    doc.add_paragraph(
        "A responsive mobile-first Progressive Web Application with client-side service worker caching (sw.js), "
        "instant bill payment shortcuts, and offline-resilient access."
    )

    # Section 4
    doc.add_heading("4. Cloud Infrastructure & DevOps Pipeline", level=1)
    doc.add_paragraph(
        "The infrastructure is codified using AWS CDK v2 in Python, provisioning Amazon VPC (ap-south-1), "
        "Amazon RDS PostgreSQL 16 Multi-AZ, ECS Fargate FastAPI container clusters, and CloudFront CDN. "
        "Automated CI/CD pipelines in GitHub Actions enforce Ruff, Mypy, Pytest, Vitest, Gitleaks, and CodeQL SAST."
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
            "Township Operations Platform — Phase 5 Production Release", title_style
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
            Paragraph("Pune Gated Township (2,400 Flats, 28 Towers)", body_style),
        ],
        [
            Paragraph("<b>Maintenance Tariff:</b>", body_style),
            Paragraph(
                "₹6.50 per sq. ft. per month (₹7,475/mo for 1,150 sq. ft.)", body_style
            ),
        ],
        [
            Paragraph("<b>Security & Roles:</b>", body_style),
            Paragraph(
                "Strict 2-Role RBAC (RESIDENT, HELPDESK) + PostgreSQL Force RLS",
                body_style,
            ),
        ],
        [
            Paragraph("<b>Reconciliation:</b>", body_style),
            Paragraph(
                "UPI VPA Normalizer + Fuzzy Matching (>= 90%) + Dual Verification",
                body_style,
            ),
        ],
        [
            Paragraph("<b>Cloud Platform:</b>", body_style),
            Paragraph(
                "AWS ap-south-1 (Mumbai) / ECS Fargate + RDS PostgreSQL 16 Multi-AZ",
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
            "resident registry management, SLA-driven complaint ticketing, and committee executive reporting. "
            "All calculations strictly utilize integer paise arithmetic to guarantee financial integrity.",
            body_style,
        )
    )

    # Section 2
    story.append(Paragraph("2. Identity, RBAC & Multi-Tenant Security", h1_style))
    story.append(
        Paragraph(
            "The platform maintains strictly two application roles: RESIDENT and HELPDESK. Fine-grained permissions "
            "(COMPLAINT_MANAGE, BANK_IMPORT, RECONCILIATION_REVIEW, BILLING_MANAGE, COMMITTEE_REPORT_READ) govern "
            "operational capabilities. Multi-tenant isolation is enforced at the database engine level via PostgreSQL "
            "FORCE ROW LEVEL SECURITY across all five financial tables.",
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
            "financial ledger. The late-fee engine supports Flat Fee, Monthly Percentage, and Daily Simple Interest in basis points.",
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
        Paragraph("3.5 Committee Reporting & PWA Resident Experience", h2_style)
    )
    story.append(
        Paragraph(
            "Live SQL aggregates calculate arrears across 0-30, 31-60, 61-90, and 90+ day buckets. CSV exports include formula injection "
            "mitigation (CWE-1236). The resident portal is delivered as an installable, offline-capable Progressive Web Application (PWA).",
            body_style,
        )
    )

    # Section 4
    story.append(Paragraph("4. Deployment & Infrastructure Architecture", h1_style))
    story.append(
        Paragraph(
            "AWS CDK v2 provisions Amazon VPC in Mumbai (ap-south-1), RDS PostgreSQL 16 Multi-AZ, ECS Fargate FastAPI container tasks, "
            "and CloudFront S3 static hosting. CI/CD pipelines enforce Ruff, Mypy, Pytest, Vitest, Gitleaks, and CodeQL SAST.",
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
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(TDD_CONTENT_MARKDOWN)
    print(f"Generated Markdown: {md_path}")

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
