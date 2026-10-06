"""Store curated restaurant and food fallback image URLs."""
from alembic import op

revision = "0011_restaurant_image_links"
down_revision = "0010_restaurant_tags"
branch_labels = None
depends_on = None

DDL = (
    """ALTER TABLE public.restaurant_rows
        ADD COLUMN restaurant_image_url text NULL,
        ADD COLUMN food_image_url text NULL""",
    """ALTER TABLE public.restaurant_rows
        ADD CONSTRAINT restaurant_rows_restaurant_image_url_https_check
            CHECK (restaurant_image_url IS NULL OR restaurant_image_url ~ '^https://[^[:space:]]+$'),
        ADD CONSTRAINT restaurant_rows_food_image_url_https_check
            CHECK (food_image_url IS NULL OR food_image_url ~ '^https://[^[:space:]]+$')""",
)


def upgrade():
    connection = op.get_bind()
    for statement in DDL:
        connection.exec_driver_sql(statement)


def downgrade():
    raise RuntimeError("Preserve imported restaurant image URLs; restore into a new isolated database")
