"""Alerts, deliveries and runbook runs, written by the pipeline.

A partial unique index on the fingerprint of unresolved alerts makes the dedup upsert idempotent; failed
deliveries and scheduled steps have partial indexes for the retry loop and the executor (SPEC §9-§11).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-20 22:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "acknowledged",
                "resolved",
                name="alert_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "debug",
                "info",
                "warn",
                "error",
                "critical",
                name="severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "colour",
            sa.Enum(
                "red",
                "orange",
                "yellow",
                "green",
                "blue",
                "grey",
                name="colour",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolution",
            sa.Enum("manual", "auto", name="resolution", native_enum=False, create_constraint=True, length=32),
            nullable=True,
        ),
        sa.Column("escalated_team_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "(status = 'resolved') = (resolved_at IS NOT NULL AND resolution IS NOT NULL)",
            name=op.f("ck_alerts_resolved_has_time"),
        ),
        sa.CheckConstraint(
            "resolved_by IS NULL OR resolution = 'manual'", name=op.f("ck_alerts_auto_resolution_has_no_user")
        ),
        sa.CheckConstraint(
            "status <> 'acknowledged' OR acknowledged_at IS NOT NULL", name=op.f("ck_alerts_acknowledged_has_time")
        ),
        sa.CheckConstraint("occurrences >= 1", name=op.f("ck_alerts_occurrences_positive")),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"], ["users.id"], name=op.f("fk_alerts_acknowledged_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.id"], name=op.f("fk_alerts_resolved_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["rule_id"], ["rules.id"], name=op.f("fk_alerts_rule_id_rules"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_alerts_team_id_teams"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index(
        "ix_alerts_escalated_team_ids", "alerts", ["escalated_team_ids"], unique=False, postgresql_using="gin"
    )
    op.create_index(op.f("ix_alerts_rule_id"), "alerts", ["rule_id"], unique=False)
    op.create_index(op.f("ix_alerts_team_id"), "alerts", ["team_id"], unique=False)
    op.create_index(
        "uq_alerts_fingerprint_unresolved",
        "alerts",
        ["fingerprint"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "email", "sms", "phone", "ui", name="channel", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "failed",
                name="delivery_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_deliveries_attempts_non_negative")),
        sa.ForeignKeyConstraint(
            ["alert_id"], ["alerts.id"], name=op.f("fk_deliveries_alert_id_alerts"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_deliveries_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deliveries")),
    )
    op.create_index(op.f("ix_deliveries_alert_id"), "deliveries", ["alert_id"], unique=False)
    op.create_index(
        "ix_deliveries_retry_at",
        "deliveries",
        ["retry_at"],
        unique=False,
        postgresql_where=sa.text("status = 'failed'"),
    )
    op.create_index(op.f("ix_deliveries_user_id"), "deliveries", ["user_id"], unique=False)
    op.create_table(
        "runbook_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("runbook_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["alert_id"], ["alerts.id"], name=op.f("fk_runbook_runs_alert_id_alerts"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["runbook_id"], ["runbooks.id"], name=op.f("fk_runbook_runs_runbook_id_runbooks"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runbook_runs")),
        sa.UniqueConstraint("alert_id", name=op.f("uq_runbook_runs_alert_id")),
    )
    op.create_index(op.f("ix_runbook_runs_runbook_id"), "runbook_runs", ["runbook_id"], unique=False)
    op.create_table(
        "step_runs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("step", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "awaiting_approval",
                "awaiting_answer",
                "awaiting_manual",
                "running",
                "succeeded",
                "failed",
                "skipped",
                name="step_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_step_runs_attempts_non_negative")),
        sa.CheckConstraint("failures >= 0", name=op.f("ck_step_runs_failures_non_negative")),
        sa.CheckConstraint("index >= 0", name=op.f("ck_step_runs_index_non_negative")),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name=op.f("fk_step_runs_decided_by_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runbook_runs.id"], name=op.f("fk_step_runs_run_id_runbook_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id", "index", name=op.f("pk_step_runs")),
    )
    op.create_index(
        "ix_step_runs_run_at", "step_runs", ["run_at"], unique=False, postgresql_where=sa.text("run_at IS NOT NULL")
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_step_runs_run_at", table_name="step_runs", postgresql_where=sa.text("run_at IS NOT NULL"))
    op.drop_table("step_runs")
    op.drop_index(op.f("ix_runbook_runs_runbook_id"), table_name="runbook_runs")
    op.drop_table("runbook_runs")
    op.drop_index(op.f("ix_deliveries_user_id"), table_name="deliveries")
    op.drop_index("ix_deliveries_retry_at", table_name="deliveries", postgresql_where=sa.text("status = 'failed'"))
    op.drop_index(op.f("ix_deliveries_alert_id"), table_name="deliveries")
    op.drop_table("deliveries")
    op.drop_index(
        "uq_alerts_fingerprint_unresolved", table_name="alerts", postgresql_where=sa.text("status <> 'resolved'")
    )
    op.drop_index(op.f("ix_alerts_team_id"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_rule_id"), table_name="alerts")
    op.drop_index("ix_alerts_escalated_team_ids", table_name="alerts", postgresql_using="gin")
    op.drop_table("alerts")
