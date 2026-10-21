"""add proxmox fields, hardware metrics and command payload

Revision ID: 31a5a8e0f12c
Revises: 2245eeff675a
Create Date: 2026-10-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '31a5a8e0f12c'
down_revision = '2245eeff675a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ip_address', sa.String(length=45), nullable=True))
        batch_op.add_column(sa.Column('cpu_percent', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('ram_percent', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('disk_percent', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('proxmox_vmid', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('proxmox_node', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('last_screenshot_at', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('commands', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payload', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('commands', schema=None) as batch_op:
        batch_op.drop_column('payload')

    with op.batch_alter_table('devices', schema=None) as batch_op:
        batch_op.drop_column('last_screenshot_at')
        batch_op.drop_column('proxmox_node')
        batch_op.drop_column('proxmox_vmid')
        batch_op.drop_column('disk_percent')
        batch_op.drop_column('ram_percent')
        batch_op.drop_column('cpu_percent')
        batch_op.drop_column('ip_address')
