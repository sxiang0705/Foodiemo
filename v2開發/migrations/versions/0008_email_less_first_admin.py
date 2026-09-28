"""Allow one explicitly provisioned administrator without email verification."""
from alembic import op

revision = "0008_email_less_first_admin"
down_revision = "0007_admin_console"
branch_labels = None
depends_on = None

DDL = """
ALTER TABLE public.users
 ADD COLUMN email_auth_exempt boolean NOT NULL DEFAULT false,
 ADD CONSTRAINT users_email_auth_exempt_admin_check
   CHECK (NOT email_auth_exempt OR (role='admin' AND email IS NULL));
CREATE UNIQUE INDEX users_single_email_auth_exempt_uq
 ON public.users(email_auth_exempt) WHERE email_auth_exempt;
"""


def upgrade():
    op.get_bind().exec_driver_sql(DDL)


def downgrade():
    raise RuntimeError("Preserve account auth state; restore into a new isolated database")
