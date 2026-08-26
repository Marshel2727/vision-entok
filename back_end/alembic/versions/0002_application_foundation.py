"""Tambah auth, event detection, camera, dan backfill data lama."""

from alembic import op
import sqlalchemy as sa


revision = "0002_application_foundation"
down_revision = "0001_existing_baseline"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    tables = _tables()

    if "uploaded_images" not in tables:
        op.create_table(
            "uploaded_images",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("original_filename", sa.String(255), nullable=False),
            sa.Column("file_path", sa.String(500), nullable=False),
            sa.Column("content_type", sa.String(100)),
            sa.Column("size_bytes", sa.Integer()),
            sa.Column("width", sa.Integer()),
            sa.Column("height", sa.Integer()),
            sa.Column("source", sa.String(50), nullable=False, server_default="upload"),
            sa.Column("status", sa.String(30), nullable=False, server_default="uploaded"),
            sa.Column("error_message", sa.Text()),
            sa.Column("processed_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_uploaded_images_id", "uploaded_images", ["id"])
    else:
        columns = _columns("uploaded_images")
        if "status" not in columns:
            op.add_column(
                "uploaded_images",
                sa.Column("status", sa.String(30), nullable=False, server_default="uploaded"),
            )
        if "error_message" not in columns:
            op.add_column("uploaded_images", sa.Column("error_message", sa.Text()))
        if "processed_at" not in columns:
            op.add_column("uploaded_images", sa.Column("processed_at", sa.DateTime()))

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(80), nullable=False),
            sa.Column("full_name", sa.String(150), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("role", sa.String(20), nullable=False, server_default="operator"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime()),
            sa.Column("last_login_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("username", name="uq_users_username"),
        )
        op.create_index("ix_users_username", "users", ["username"])
        op.create_index("ix_users_role", "users", ["role"])
        op.create_index("ix_users_is_active", "users", ["is_active"])

    if "auth_sessions" not in tables:
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.String(64), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("refresh_token_hash", sa.String(64), nullable=False),
            sa.Column("ip_address", sa.String(64)),
            sa.Column("user_agent", sa.String(500)),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("session_id", name="uq_auth_sessions_session_id"),
            sa.UniqueConstraint("refresh_token_hash", name="uq_auth_sessions_refresh_hash"),
        )
        op.create_index("ix_auth_sessions_session_id", "auth_sessions", ["session_id"])
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
        op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    if "cameras" not in tables:
        op.create_table(
            "cameras",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False, server_default="Kamera Entok"),
            sa.Column("source_type", sa.String(30), nullable=False, server_default="opencv"),
            sa.Column("source_value", sa.Text(), nullable=False, server_default="0"),
            sa.Column("username_encrypted", sa.Text()),
            sa.Column("password_encrypted", sa.Text()),
            sa.Column("config_json", sa.JSON(), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("auto_start", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("detection_interval_seconds", sa.Float(), nullable=False, server_default="2"),
            sa.Column("confidence_threshold", sa.Float(), nullable=False, server_default="0.5"),
            sa.Column("snapshot_cooldown_seconds", sa.Float(), nullable=False, server_default="5"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if "detection_events" not in tables:
        op.create_table(
            "detection_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("uploaded_image_id", sa.Integer(), sa.ForeignKey("uploaded_images.id")),
            sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id")),
            sa.Column("source_type", sa.String(30), nullable=False, server_default="upload"),
            sa.Column("status", sa.String(30), nullable=False, server_default="processing"),
            sa.Column("outcome", sa.String(30)),
            sa.Column("max_confidence", sa.Float()),
            sa.Column("detection_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("inference_time_ms", sa.Float()),
            sa.Column("model_version", sa.String(150)),
            sa.Column("annotated_path", sa.String(500)),
            sa.Column("error_message", sa.Text()),
            sa.Column("review_status", sa.String(30), nullable=False, server_default="unreviewed"),
            sa.Column("reviewed_label", sa.String(30)),
            sa.Column("review_notes", sa.Text()),
            sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("reviewed_at", sa.DateTime()),
            sa.Column("detected_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        for name, columns in (
            ("ix_detection_events_uploaded_image_id", ["uploaded_image_id"]),
            ("ix_detection_events_camera_id", ["camera_id"]),
            ("ix_detection_events_source_type", ["source_type"]),
            ("ix_detection_events_status", ["status"]),
            ("ix_detection_events_outcome", ["outcome"]),
            ("ix_detection_events_max_confidence", ["max_confidence"]),
            ("ix_detection_events_review_status", ["review_status"]),
            ("ix_detection_events_detected_at", ["detected_at"]),
        ):
            op.create_index(name, "detection_events", columns)

    tables = _tables()
    if "detection_results" not in tables:
        op.create_table(
            "detection_results",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), sa.ForeignKey("detection_events.id")),
            sa.Column("uploaded_image_id", sa.Integer(), sa.ForeignKey("uploaded_images.id")),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("bbox_x", sa.Float()),
            sa.Column("bbox_y", sa.Float()),
            sa.Column("bbox_width", sa.Float()),
            sa.Column("bbox_height", sa.Float()),
            sa.Column("is_abnormal", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("frame_path", sa.String(500)),
            sa.Column("annotated_path", sa.String(500)),
            sa.Column("camera_source", sa.String(255)),
            sa.Column("detected_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_detection_results_id", "detection_results", ["id"])
        op.create_index("ix_detection_results_event_id", "detection_results", ["event_id"])
    else:
        columns = _columns("detection_results")
        if "event_id" not in columns:
            op.add_column("detection_results", sa.Column("event_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                "fk_detection_results_event_id",
                "detection_results",
                "detection_events",
                ["event_id"],
                ["id"],
            )
        if "ix_detection_results_event_id" not in _indexes("detection_results"):
            op.create_index("ix_detection_results_event_id", "detection_results", ["event_id"])

        bind = op.get_bind()
        uploaded_ids = bind.execute(
            sa.text(
                "SELECT DISTINCT uploaded_image_id FROM detection_results "
                "WHERE event_id IS NULL AND uploaded_image_id IS NOT NULL"
            )
        ).scalars()
        for uploaded_id in uploaded_ids:
            summary = bind.execute(
                sa.text(
                    "SELECT MAX(confidence) max_confidence, COUNT(*) detection_count, "
                    "MAX(CASE WHEN is_abnormal = 1 THEN 1 ELSE 0 END) has_abnormal, "
                    "MIN(detected_at) detected_at FROM detection_results "
                    "WHERE uploaded_image_id = :uploaded_id AND event_id IS NULL"
                ),
                {"uploaded_id": uploaded_id},
            ).mappings().one()
            result = bind.execute(
                sa.text(
                    "INSERT INTO detection_events "
                    "(uploaded_image_id, source_type, status, outcome, max_confidence, "
                    "detection_count, model_version, review_status, detected_at, created_at) "
                    "VALUES (:uploaded_id, 'upload', 'completed', :outcome, :confidence, "
                    ":count, 'legacy', 'unreviewed', :detected_at, CURRENT_TIMESTAMP)"
                ),
                {
                    "uploaded_id": uploaded_id,
                    "outcome": "abnormal" if summary["has_abnormal"] else "normal",
                    "confidence": summary["max_confidence"],
                    "count": summary["detection_count"],
                    "detected_at": summary["detected_at"],
                },
            )
            bind.execute(
                sa.text(
                    "UPDATE detection_results SET event_id = :event_id "
                    "WHERE uploaded_image_id = :uploaded_id AND event_id IS NULL"
                ),
                {"event_id": result.lastrowid, "uploaded_id": uploaded_id},
            )


def downgrade() -> None:
    tables = _tables()
    if "detection_results" in tables and "event_id" in _columns("detection_results"):
        if "ix_detection_results_event_id" in _indexes("detection_results"):
            op.drop_index("ix_detection_results_event_id", table_name="detection_results")
        try:
            op.drop_constraint("fk_detection_results_event_id", "detection_results", type_="foreignkey")
        except Exception:
            pass
        op.drop_column("detection_results", "event_id")
    for table in ("auth_sessions", "detection_events", "cameras", "users"):
        if table in _tables():
            op.drop_table(table)
