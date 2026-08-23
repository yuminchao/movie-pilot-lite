"""创建初始数据表。"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("isvalid", sa.Boolean(), nullable=False),
        sa.Column("ctime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mtime", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "admin_user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        *_audit_columns(),
    )
    op.create_table(
        "session",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *_audit_columns(),
    )
    op.create_table(
        "app_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False, unique=True),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        *_audit_columns(),
    )
    op.create_index("ix_app_config_key", "app_config", ["key"], unique=True)
    op.create_table(
        "download_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("qb_hash", sa.String(128)),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("category", sa.String(100)),
        sa.Column("save_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_message", sa.Text()),
        *_audit_columns(),
    )
    op.create_index("ix_download_record_qb_hash", "download_record", ["qb_hash"])
    op.create_index("ix_download_record_idempotency_key", "download_record", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_table("download_record")
    op.drop_table("app_config")
    op.drop_table("session")
    op.drop_table("admin_user")
