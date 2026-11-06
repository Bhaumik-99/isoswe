import os

from alembic import command
from alembic.config import Config
from scripts.seed import (
    FLAT_0408_ID,
    FLAT_1203_ID,
    FLAT_1601_ID,
    seed_database,
)
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domains.billing.models import (
    FinancialLedgerEntry,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentAllocation,
)
from app.domains.identity.models import (
    Flat,
    FlatMembership,
    Society,
    Tower,
    User,
    UserRole,
)


def test_database_migration_works_from_empty_database() -> None:
    """Requirement 13.12: Database migration works from an empty database using real Alembic migrations."""
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)

    test_dir = os.path.dirname(__file__)
    api_dir = os.path.abspath(os.path.join(test_dir, ".."))
    alembic_ini_path = os.path.join(api_dir, "alembic.ini")

    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(api_dir, "migrations"))

    with engine.connect() as connection:
        alembic_cfg.attributes["connection"] = connection

        # 1. Run Alembic upgrade head from empty database
        command.upgrade(alembic_cfg, "head")

        inspector = inspect(connection)
        table_names = inspector.get_table_names()
        required_tables = [
            "societies",
            "towers",
            "flats",
            "users",
            "flat_memberships",
            "user_roles",
            "user_permissions",
            "audit_events",
            "outbox_events",
            "idempotency_keys",
            "processed_events",
            "billing_configurations",
            "invoices",
            "invoice_line_items",
            "payments",
            "payment_allocations",
            "financial_ledger_entries",
            "billing_runs",
        ]
        for tbl in required_tables:
            assert tbl in table_names, f"Table '{tbl}' must be created by Alembic upgrade head"

        # 2. Test Alembic downgrade to base
        command.downgrade(alembic_cfg, "base")
        connection.commit()
        inspector_after = inspect(engine)
        table_names_after_downgrade = inspector_after.get_table_names()
        for tbl in required_tables:
            assert tbl not in table_names_after_downgrade, (
                f"Table '{tbl}' must be dropped by Alembic downgrade base"
            )

        # 3. Upgrade back to head to verify re-application works idempotently
        command.upgrade(alembic_cfg, "head")
        connection.commit()


def test_seed_script_is_idempotent(monkeypatch) -> None:
    """Requirement 13.13: Seed script is idempotent. Re-running it must not duplicate records."""
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    # Monkeypatch SessionLocal in scripts.seed to point to our test engine
    import scripts.seed

    monkeypatch.setattr(scripts.seed, "SessionLocal", TestSession)

    # Pass 1: Run seed
    seed_database()

    with TestSession() as session:
        society_count_1 = session.scalar(select(func.count(Society.id)))
        tower_count_1 = session.scalar(select(func.count(Tower.id)))
        flat_count_1 = session.scalar(select(func.count(Flat.id)))
        user_count_1 = session.scalar(select(func.count(User.id)))
        membership_count_1 = session.scalar(select(func.count(FlatMembership.id)))
        role_count_1 = session.scalar(select(func.count(UserRole.id)))

        invoice_count_1 = session.scalar(select(func.count(Invoice.id)))
        payment_count_1 = session.scalar(select(func.count(Payment.id)))
        ledger_count_1 = session.scalar(select(func.count(FinancialLedgerEntry.id)))

        assert society_count_1 == 1
        assert tower_count_1 == 3
        assert flat_count_1 == 3
        assert user_count_1 == 5
        assert role_count_1 == 5
        assert invoice_count_1 == 3
        assert payment_count_1 == 1
        assert ledger_count_1 == 5

        # Verify the 3 required sample flats exist with correct details
        f1 = session.get(Flat, FLAT_1203_ID)
        assert f1.flat_number == "1203"
        assert f1.area_sqft == 1150

        f2 = session.get(Flat, FLAT_0408_ID)
        assert f2.flat_number == "0408"
        assert f2.area_sqft == 980

        f3 = session.get(Flat, FLAT_1601_ID)
        assert f3.flat_number == "1601"
        assert f3.area_sqft == 1640

        # Verify required sample calculations
        inv_neeraj = session.scalar(select(Invoice).where(Invoice.flat_id == FLAT_1203_ID))
        assert inv_neeraj is not None
        assert inv_neeraj.total_paise == 747500  # 1,150 sq ft * 650 = ₹7,475
        assert inv_neeraj.status == InvoiceStatus.UNPAID

        inv_swati = session.scalar(select(Invoice).where(Invoice.flat_id == FLAT_0408_ID))
        assert inv_swati is not None
        assert inv_swati.total_paise == 637000  # 980 sq ft * 650 = ₹6,370
        assert inv_swati.status == InvoiceStatus.OVERDUE

        inv_aamir = session.scalar(select(Invoice).where(Invoice.flat_id == FLAT_1601_ID))
        assert inv_aamir is not None
        assert inv_aamir.total_paise == 1066000  # 1,640 sq ft * 650 = ₹10,660
        assert inv_aamir.status == InvoiceStatus.PARTIALLY_PAID

        # Verify Aamir's payment allocation
        payment_aamir = session.scalar(select(Payment).where(Payment.flat_id == FLAT_1601_ID))
        assert payment_aamir is not None
        assert payment_aamir.amount_paise == 500000  # ₹5,000 paid

        alloc_aamir = session.scalar(
            select(PaymentAllocation).where(PaymentAllocation.payment_id == payment_aamir.id)
        )
        assert alloc_aamir is not None
        assert alloc_aamir.allocated_paise == 500000

    # Pass 2: Re-run seed immediately (must not fail or duplicate)
    seed_database()

    with TestSession() as session:
        society_count_2 = session.scalar(select(func.count(Society.id)))
        tower_count_2 = session.scalar(select(func.count(Tower.id)))
        flat_count_2 = session.scalar(select(func.count(Flat.id)))
        user_count_2 = session.scalar(select(func.count(User.id)))
        membership_count_2 = session.scalar(select(func.count(FlatMembership.id)))
        role_count_2 = session.scalar(select(func.count(UserRole.id)))
        invoice_count_2 = session.scalar(select(func.count(Invoice.id)))
        payment_count_2 = session.scalar(select(func.count(Payment.id)))
        ledger_count_2 = session.scalar(select(func.count(FinancialLedgerEntry.id)))

        # Counts must remain strictly identical
        assert society_count_2 == society_count_1
        assert tower_count_2 == tower_count_1
        assert flat_count_2 == flat_count_1
        assert user_count_2 == user_count_1
        assert membership_count_2 == membership_count_1
        assert role_count_2 == role_count_1
        assert invoice_count_2 == invoice_count_1
        assert payment_count_2 == payment_count_1
        assert ledger_count_2 == ledger_count_1

    Base.metadata.drop_all(bind=engine)
