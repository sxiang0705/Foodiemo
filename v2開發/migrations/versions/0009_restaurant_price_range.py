"""Add the restaurant price-range bucket used by recommendations."""
from alembic import op

revision = "0009_restaurant_price_range"
down_revision = "0008_email_less_first_admin"
branch_labels = None
depends_on = None

DDL = "ALTER TABLE public.restaurant_rows ADD COLUMN price_range text;"


def upgrade():
    op.get_bind().exec_driver_sql(DDL)


def downgrade():
    raise RuntimeError("Preserve imported price data; restore into a new isolated database")
