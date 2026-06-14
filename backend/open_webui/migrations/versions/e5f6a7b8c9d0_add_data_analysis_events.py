"""add data_analysis_events table

Revision ID: e5f6a7b8c9d0
Revises: a0b1c2d3e4f5
Create Date: 2026-05-12
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'a0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'data_analysis_events',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('ts', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('user_org_id', sa.Text(), nullable=True),
        sa.Column('chat_id', sa.Text(), nullable=True),
        sa.Column('message_id', sa.Text(), nullable=True),
        sa.Column('workspace', sa.Text(), nullable=False, server_default='data-analysis'),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('dataset_id', sa.Text(), nullable=True),
        sa.Column('chart_type', sa.Text(), nullable=True),
        sa.Column('tool_name', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('error_code', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('deleted_at', sa.BigInteger(), nullable=True),
    )
    op.create_index('idx_events_user_ts', 'data_analysis_events', ['user_id', 'ts'])
    op.create_index('idx_events_chat_ts', 'data_analysis_events', ['chat_id', 'ts'])
    op.create_index('idx_events_event_type_ts', 'data_analysis_events', ['event_type', 'ts'])
    op.create_index('idx_events_dataset_ts', 'data_analysis_events', ['dataset_id', 'ts'])
    op.create_index('idx_events_chart_type_ts', 'data_analysis_events', ['chart_type', 'ts'])
    op.create_index('idx_events_success_ts', 'data_analysis_events', ['success', 'ts'])


def downgrade() -> None:
    op.drop_index('idx_events_success_ts', table_name='data_analysis_events')
    op.drop_index('idx_events_chart_type_ts', table_name='data_analysis_events')
    op.drop_index('idx_events_dataset_ts', table_name='data_analysis_events')
    op.drop_index('idx_events_event_type_ts', table_name='data_analysis_events')
    op.drop_index('idx_events_chat_ts', table_name='data_analysis_events')
    op.drop_index('idx_events_user_ts', table_name='data_analysis_events')
    op.drop_table('data_analysis_events')
