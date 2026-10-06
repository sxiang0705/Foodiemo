"""Add the restaurant tag dictionary and restaurant-to-tag mapping."""
from alembic import op

revision = "0010_restaurant_tags"
down_revision = "0009_restaurant_price_range"
branch_labels = None
depends_on = None

DDL = (
    """CREATE TABLE public.tags_rows (
        tag_id SERIAL NOT NULL,
        tag_name text NOT NULL,
        category text NOT NULL,
        is_active boolean NOT NULL DEFAULT true,
        CONSTRAINT tags_rows_pkey PRIMARY KEY (tag_id),
        CONSTRAINT tags_rows_tag_id_check CHECK (tag_id > 0),
        CONSTRAINT tags_rows_tag_name_check CHECK (btrim(tag_name) <> ''),
        CONSTRAINT tags_rows_category_check CHECK (
            category IN ('cuisine', 'food_type', 'amenity', 'feature', 'occasion', 'time_period')
        ),
        CONSTRAINT tags_rows_category_tag_name_key UNIQUE (category, tag_name)
    )""",
    """CREATE TABLE public.restaurant_tags_rows (
        restaurant_id bigint NOT NULL,
        tag_id integer NOT NULL,
        CONSTRAINT restaurant_tags_rows_pkey PRIMARY KEY (restaurant_id, tag_id),
        CONSTRAINT restaurant_tags_rows_restaurant_id_fkey
            FOREIGN KEY (restaurant_id)
            REFERENCES public.restaurant_rows (restaurant_id) ON DELETE CASCADE,
        CONSTRAINT restaurant_tags_rows_tag_id_fkey
            FOREIGN KEY (tag_id)
            REFERENCES public.tags_rows (tag_id) ON DELETE CASCADE
    )""",
    """CREATE INDEX ix_restaurant_tags_rows_tag_restaurant
        ON public.restaurant_tags_rows USING btree (tag_id, restaurant_id)""",
)


def upgrade():
    connection = op.get_bind()
    for statement in DDL:
        connection.exec_driver_sql(statement)


def downgrade():
    raise RuntimeError("Preserve imported tag data; restore into a new isolated database")
