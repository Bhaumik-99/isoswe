"""Idempotent Synthetic Seed Data Script

Populates the Pune township operations database with:
- 1 Society (Marvel Greenfield Residences, Pune)
- 3 Towers (T07, T12, T21)
- 3 Required Flats (T07-1203, T12-0408, T21-1601)
- Residents: Neeraj Kulkarni (Owner), Swati Joshi (Tenant), Aamir Shaikh (Owner)
- Staff: Helpdesk (Rajesh Shinde), Finance (Priya Deshmukh), Committee (Aniket Patwardhan), Admin (Vikram Joshi)

INVARIANT: Idempotent execution. Running multiple times produces no duplicates.
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta

# Ensure services/api is on sys.path
sys.path.insert(0, "services/api")
sys.path.insert(0, ".")

from app.core.database import SessionLocal
from app.core.logging import logger
from app.domains.billing.models import (
    BillingConfiguration,
    FinancialLedgerEntry,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    LedgerEntryType,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    FlatStatus,
    MembershipStatus,
    MembershipType,
    Permission,
    RoleType,
    Society,
    SocietyStatus,
    Tower,
    User,
    UserPermission,
    UserRole,
    UserStatus,
)
from app.domains.visitors.models import (
    Gate,
    GateStaffAssignment,
    GateStatus,
)
from sqlalchemy import select

# Fixed deterministic UUIDs for seed records so they are easily referenceable in tests
SOCIETY_PUNE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TOWER_T07_ID = uuid.UUID("22222222-2222-2222-2222-222222222207")
TOWER_T12_ID = uuid.UUID("22222222-2222-2222-2222-222222222212")
TOWER_T21_ID = uuid.UUID("22222222-2222-2222-2222-222222222221")

FLAT_1203_ID = uuid.UUID("33333333-3333-3333-3333-333333331203")
FLAT_0408_ID = uuid.UUID("33333333-3333-3333-3333-333333330408")
FLAT_1601_ID = uuid.UUID("33333333-3333-3333-3333-333333331601")

USER_NEERAJ_ID = uuid.UUID("44444444-4444-4444-4444-444444440001")
USER_SWATI_ID = uuid.UUID("44444444-4444-4444-4444-444444440002")
USER_AAMIR_ID = uuid.UUID("44444444-4444-4444-4444-444444440003")
USER_HELPDESK_ID = uuid.UUID("44444444-4444-4444-4444-444444440004")
USER_FINANCE_ID = uuid.UUID("44444444-4444-4444-4444-444444440005")
USER_COMMITTEE_ID = uuid.UUID("44444444-4444-4444-4444-444444440006")
USER_ADMIN_ID = uuid.UUID("44444444-4444-4444-4444-444444440007")

BILLING_CONFIG_PUNE_ID = uuid.UUID("66666666-6666-6666-6666-666666660001")
INVOICE_NEERAJ_ID = uuid.UUID("77777777-7777-7777-7777-777777770001")
INVOICE_SWATI_ID = uuid.UUID("77777777-7777-7777-7777-777777770002")
INVOICE_AAMIR_ID = uuid.UUID("77777777-7777-7777-7777-777777770003")
PAYMENT_AAMIR_ID = uuid.UUID("88888888-8888-8888-8888-888888880001")
ALLOCATION_AAMIR_ID = uuid.UUID("99999999-9999-9999-9999-999999990001")

# 4 Gates for Marvel Greenfield Residences (Phase 6)
GATE_1_ID = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
GATE_2_ID = uuid.UUID("aaaaaaaa-2222-0000-0000-000000000002")
GATE_3_ID = uuid.UUID("aaaaaaaa-3333-0000-0000-000000000003")
GATE_4_ID = uuid.UUID("aaaaaaaa-4444-0000-0000-000000000004")
GATE_ASSIGNMENT_1_ID = uuid.UUID("77777777-1111-0000-0000-000000000001")


def seed_database() -> None:
    now = datetime.now(UTC)
    one_year_later = now + timedelta(days=365)

    with SessionLocal() as db:
        logger.info(
            "Starting idempotent database seed for Marvel Greenfield Residences, Pune..."
        )

        # 1. Society
        society = db.get(Society, SOCIETY_PUNE_ID)
        if not society:
            society = Society(
                id=SOCIETY_PUNE_ID,
                name="Marvel Greenfield Residences",
                timezone="Asia/Kolkata",
                preferred_currency="INR",
                status=SocietyStatus.ACTIVE,
            )
            db.add(society)
            db.flush()
            logger.info("Created Society: Marvel Greenfield Residences")

        # 2. Towers
        towers_data = [
            (TOWER_T07_ID, "T07", "Tower 7"),
            (TOWER_T12_ID, "T12", "Tower 12"),
            (TOWER_T21_ID, "T21", "Tower 21"),
        ]
        for t_id, t_num, t_name in towers_data:
            tower = db.get(Tower, t_id)
            if not tower:
                tower = Tower(
                    id=t_id,
                    society_id=SOCIETY_PUNE_ID,
                    tower_number=t_num,
                    name=t_name,
                )
                db.add(tower)
                db.flush()
                logger.info(f"Created Tower: {t_name} ({t_num})")

        # 3. Flats
        flats_data = [
            (FLAT_1203_ID, TOWER_T07_ID, "1203", 1150, FlatStatus.OCCUPIED),
            (FLAT_0408_ID, TOWER_T12_ID, "0408", 980, FlatStatus.OCCUPIED),
            (FLAT_1601_ID, TOWER_T21_ID, "1601", 1640, FlatStatus.OCCUPIED),
        ]
        for f_id, tow_id, f_num, area, f_status in flats_data:
            flat = db.get(Flat, f_id)
            if not flat:
                flat = Flat(
                    id=f_id,
                    society_id=SOCIETY_PUNE_ID,
                    tower_id=tow_id,
                    flat_number=f_num,
                    area_sqft=area,
                    status=f_status,
                )
                db.add(flat)
                db.flush()
                logger.info(f"Created Flat: {f_num} (Area: {area} sq ft)")

        # 4. Users (Linked to Supabase Auth UUIDs)
        users_data = [
            (
                USER_NEERAJ_ID,
                uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "neeraj.kulkarni@example.com",
                "+91-98000-00001",
                "Neeraj Kulkarni",
                RoleType.RESIDENT,
            ),
            (
                USER_SWATI_ID,
                uuid.UUID("00000000-0000-0000-0000-000000000002"),
                "swati.joshi@example.com",
                "+91-98000-00002",
                "Swati Joshi",
                RoleType.RESIDENT,
            ),
            (
                USER_AAMIR_ID,
                uuid.UUID("00000000-0000-0000-0000-000000000003"),
                "aamir.shaikh@example.com",
                "+91-98000-00003",
                "Aamir Shaikh",
                RoleType.RESIDENT,
            ),
            (
                USER_HELPDESK_ID,
                uuid.UUID("00000000-0000-0000-0000-000000000004"),
                "helpdesk@example.com",
                "+91-98000-00004",
                "Rajesh Shinde",
                RoleType.HELPDESK,
            ),
            (
                USER_COMMITTEE_ID,
                uuid.UUID("00000000-0000-0000-0000-000000000006"),
                "committee@example.com",
                "+91-98000-00006",
                "Aniket Patwardhan",
                RoleType.HELPDESK,
            ),
        ]

        for u_id, s_uid, email, phone, name, primary_role in users_data:
            user = db.get(User, u_id)
            if not user:
                user = User(
                    id=u_id,
                    supabase_uid=s_uid,
                    email=email,
                    phone=phone,
                    full_name=name,
                    status=UserStatus.ACTIVE,
                )
                db.add(user)
                db.flush()
                logger.info(f"Created User: {name} ({email})")

            # Assign Role
            role_stmt = select(UserRole).where(
                UserRole.user_id == u_id,
                UserRole.society_id == SOCIETY_PUNE_ID,
                UserRole.role == primary_role,
            )
            existing_role = db.scalars(role_stmt).first()
            if not existing_role:
                new_role = UserRole(
                    user_id=u_id,
                    society_id=SOCIETY_PUNE_ID,
                    role=primary_role,
                )
                db.add(new_role)
                db.flush()
                logger.info(f"Assigned role {primary_role.value} to {name}")

        # 4b. Explicit Granular User Permissions
        permissions_data = [
            (USER_HELPDESK_ID, SOCIETY_PUNE_ID, Permission.COMPLAINT_MANAGE),
            (USER_HELPDESK_ID, SOCIETY_PUNE_ID, Permission.BANK_IMPORT),
            (USER_HELPDESK_ID, SOCIETY_PUNE_ID, Permission.RECONCILIATION_REVIEW),
            (USER_HELPDESK_ID, SOCIETY_PUNE_ID, Permission.BILLING_MANAGE),
            (USER_HELPDESK_ID, SOCIETY_PUNE_ID, Permission.GATE_OPERATIONS),
            (USER_HELPDESK_ID, SOCIETY_PUNE_ID, Permission.COMMITTEE_REPORT_READ),
            (USER_COMMITTEE_ID, SOCIETY_PUNE_ID, Permission.COMMITTEE_REPORT_READ),
        ]
        for u_id, soc_id, perm in permissions_data:
            perm_stmt = select(UserPermission).where(
                UserPermission.user_id == u_id,
                UserPermission.society_id == soc_id,
                UserPermission.permission == perm,
            )
            existing_perm = db.scalars(perm_stmt).first()
            if not existing_perm:
                new_perm = UserPermission(
                    user_id=u_id,
                    society_id=soc_id,
                    permission=perm,
                )
                db.add(new_perm)
                db.flush()
                logger.info(f"Assigned permission {perm.value} to user {u_id}")

        # 4c. Physical Gates (Phase 6)
        gates_data = [
            (
                GATE_1_ID,
                1,
                "Gate 1 - North Main",
                "North primary visitor and residential entrance",
            ),
            (
                GATE_2_ID,
                2,
                "Gate 2 - South Entry",
                "South commercial and visitor entrance",
            ),
            (
                GATE_3_ID,
                3,
                "Gate 3 - East Service",
                "East service and delivery vehicle entrance",
            ),
            (
                GATE_4_ID,
                4,
                "Gate 4 - West Resident",
                "West resident RFID and pedestrian gate",
            ),
        ]
        for g_id, g_num, g_name, g_desc in gates_data:
            existing_gate = db.get(Gate, g_id)
            if not existing_gate:
                new_gate = Gate(
                    id=g_id,
                    society_id=SOCIETY_PUNE_ID,
                    gate_number=g_num,
                    gate_name=g_name,
                    name=g_name,
                    description=g_desc,
                    status=GateStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
                db.add(new_gate)
                db.flush()
                logger.info(f"Created Gate: {g_name} (#{g_num})")

        # 4d. Gate Staff Assignment for Rajesh Shinde (Helpdesk) to Gate 1
        existing_assignment = db.get(GateStaffAssignment, GATE_ASSIGNMENT_1_ID)
        if not existing_assignment:
            new_assignment = GateStaffAssignment(
                id=GATE_ASSIGNMENT_1_ID,
                society_id=SOCIETY_PUNE_ID,
                gate_id=GATE_1_ID,
                user_id=USER_HELPDESK_ID,
                is_active=True,
                assigned_from=now - timedelta(days=30),
                assigned_until=now + timedelta(days=365),
                created_at=now,
                updated_at=now,
            )
            db.add(new_assignment)
            db.flush()
            logger.info("Assigned Rajesh Shinde to Gate 1 (North Main)")

        # 5. Flat Memberships
        memberships_data = [
            (
                uuid.UUID("55555555-5555-5555-5555-555555550001"),
                USER_NEERAJ_ID,
                FLAT_1203_ID,
                MembershipType.OWNER,
                now - timedelta(days=180),
                None,  # Owner has no expiry
                True,
            ),
            (
                uuid.UUID("55555555-5555-5555-5555-555555550002"),
                USER_SWATI_ID,
                FLAT_0408_ID,
                MembershipType.TENANT,
                now - timedelta(days=60),
                one_year_later,  # Tenant active lease
                True,
            ),
            (
                uuid.UUID("55555555-5555-5555-5555-555555550003"),
                USER_AAMIR_ID,
                FLAT_1601_ID,
                MembershipType.OWNER,
                now - timedelta(days=365),
                None,  # Owner has no expiry
                True,
            ),
        ]

        for m_id, u_id, f_id, m_type, v_from, v_until, is_pri in memberships_data:
            membership = db.get(FlatMembership, m_id)
            if not membership:
                membership = FlatMembership(
                    id=m_id,
                    society_id=SOCIETY_PUNE_ID,
                    user_id=u_id,
                    flat_id=f_id,
                    membership_type=m_type,
                    valid_from=v_from,
                    valid_until=v_until,
                    is_primary=is_pri,
                    status=MembershipStatus.APPROVED,
                )
                db.add(membership)
                db.flush()
                logger.info(
                    f"Assigned {m_type.value} membership for user {u_id} to flat {f_id}"
                )

        # 6. Billing Configuration (Rate: ₹6.50/sq ft = 650 paise)
        b_config = db.get(BillingConfiguration, BILLING_CONFIG_PUNE_ID)
        if not b_config:
            b_config = BillingConfiguration(
                id=BILLING_CONFIG_PUNE_ID,
                society_id=SOCIETY_PUNE_ID,
                rate_paise_per_sqft=650,
                currency="INR",
                effective_from=now - timedelta(days=90),
                due_day=10,
            )
            db.add(b_config)
            db.flush()
            logger.info("Created BillingConfiguration: ₹6.50/sq ft (650 paise)")

        # 7. Required Invoices
        # Period strings
        current_period = now.strftime("%Y-%m")
        prev_period_1 = (now - timedelta(days=30)).strftime("%Y-%m")
        prev_period_2 = (now - timedelta(days=60)).strftime("%Y-%m")

        invoices_data = [
            # Neeraj Kulkarni (T07-1203, 1,150 sq ft, ₹7,475, UNPAID, due in 7 days)
            (
                INVOICE_NEERAJ_ID,
                FLAT_1203_ID,
                current_period,
                f"INV-{current_period.replace('-', '')}-T07-1203",
                1150,
                650,
                747500,
                now + timedelta(days=7),
                InvoiceStatus.UNPAID,
                "Neeraj Kulkarni",
            ),
            # Swati Joshi (T12-0408, 980 sq ft, ₹6,370, OVERDUE by 47 days)
            (
                INVOICE_SWATI_ID,
                FLAT_0408_ID,
                prev_period_2,
                f"INV-{prev_period_2.replace('-', '')}-T12-0408",
                980,
                650,
                637000,
                now - timedelta(days=47),
                InvoiceStatus.OVERDUE,
                "Swati Joshi",
            ),
            # Aamir Shaikh (T21-1601, 1,640 sq ft, ₹10,660, OVERDUE by 18 days, PARTIALLY_PAID)
            (
                INVOICE_AAMIR_ID,
                FLAT_1601_ID,
                prev_period_1,
                f"INV-{prev_period_1.replace('-', '')}-T21-1601",
                1640,
                650,
                1066000,
                now - timedelta(days=18),
                InvoiceStatus.PARTIALLY_PAID,
                "Aamir Shaikh",
            ),
        ]

        for (
            inv_id,
            f_id,
            period,
            inv_num,
            area,
            rate,
            total_paise,
            due_d,
            inv_status,
            resident_name,
        ) in invoices_data:
            inv = db.get(Invoice, inv_id)
            if not inv:
                inv = Invoice(
                    id=inv_id,
                    society_id=SOCIETY_PUNE_ID,
                    flat_id=f_id,
                    billing_period=period,
                    invoice_number=inv_num,
                    area_sqft_snapshot=area,
                    rate_paise_per_sqft_snapshot=rate,
                    subtotal_paise=total_paise,
                    total_paise=total_paise,
                    due_date=due_d,
                    status=inv_status,
                )
                db.add(inv)
                db.flush()

                line_item = InvoiceLineItem(
                    id=uuid.uuid4(),
                    invoice_id=inv.id,
                    description=f"Monthly Maintenance ({area:,} sq ft @ ₹6.50/sq ft)",
                    quantity=1,
                    unit_rate_paise=total_paise,
                    amount_paise=total_paise,
                )
                db.add(line_item)
                db.flush()

                # Financial ledger entry: CHARGE
                charge_entry = FinancialLedgerEntry(
                    id=uuid.uuid4(),
                    society_id=SOCIETY_PUNE_ID,
                    flat_id=f_id,
                    invoice_id=inv.id,
                    entry_type=LedgerEntryType.CHARGE,
                    amount_paise=total_paise,
                    reference_id=inv.invoice_number,
                    description=f"Monthly maintenance charge for unit ({period})",
                )
                db.add(charge_entry)
                db.flush()
                logger.info(
                    f"Created Invoice: {inv_num} for {resident_name} (₹{total_paise / 100:,.2f})"
                )

        # 8. Payments & Allocations (Aamir Shaikh: ₹5,000 paid against ₹10,660 invoice)
        payment_aamir = db.get(Payment, PAYMENT_AAMIR_ID)
        if not payment_aamir:
            payment_aamir = Payment(
                id=PAYMENT_AAMIR_ID,
                society_id=SOCIETY_PUNE_ID,
                flat_id=FLAT_1601_ID,
                amount_paise=500000,  # ₹5,000
                currency="INR",
                provider="SIMULATED",
                provider_reference="SIM-SEED-AAMIR-5000",
                status=PaymentStatus.SUCCESS,
                initiated_by=USER_AAMIR_ID,
            )
            db.add(payment_aamir)
            db.flush()

            # Allocation
            alloc = PaymentAllocation(
                id=ALLOCATION_AAMIR_ID,
                payment_id=payment_aamir.id,
                invoice_id=INVOICE_AAMIR_ID,
                allocated_paise=500000,
            )
            db.add(alloc)
            db.flush()

            # Ledger entries: PAYMENT_RECEIVED and PAYMENT_ALLOCATED
            db.add(
                FinancialLedgerEntry(
                    id=uuid.uuid4(),
                    society_id=SOCIETY_PUNE_ID,
                    flat_id=FLAT_1601_ID,
                    invoice_id=INVOICE_AAMIR_ID,
                    payment_id=payment_aamir.id,
                    entry_type=LedgerEntryType.PAYMENT_RECEIVED,
                    amount_paise=500000,
                    reference_id=payment_aamir.provider_reference,
                    description="Simulated partial payment received for Aamir Shaikh",
                )
            )
            db.add(
                FinancialLedgerEntry(
                    id=uuid.uuid4(),
                    society_id=SOCIETY_PUNE_ID,
                    flat_id=FLAT_1601_ID,
                    invoice_id=INVOICE_AAMIR_ID,
                    payment_id=payment_aamir.id,
                    entry_type=LedgerEntryType.PAYMENT_ALLOCATED,
                    amount_paise=500000,
                    reference_id=str(alloc.id),
                    description="Funds allocated to invoice (Outstanding: ₹5,660)",
                )
            )
            db.flush()
            logger.info("Created Seed Payment & Allocation: ₹5,000 for Aamir Shaikh")

        db.commit()
        logger.info("Seed data successfully committed without errors.")


if __name__ == "__main__":
    seed_database()
