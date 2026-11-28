"""Rebuild the vector index after document chunks are populated."""
from typing import Sequence, Union

from alembic import op


revision: str = "0003_rebuild_embedding_index"
down_revision: Union[str, None] = "0002_document_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Recreate IVFFlat centroids from the existing chunk vectors."""
    op.drop_index("ix_document_chunks_embedding_cosine", table_name="document_chunks")
    op.create_index(
        "ix_document_chunks_embedding_cosine",
        "document_chunks",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"lists": 10},
    )


def downgrade() -> None:
    """Restore the prior index definition without changing stored vectors."""
    op.drop_index("ix_document_chunks_embedding_cosine", table_name="document_chunks")
    op.create_index(
        "ix_document_chunks_embedding_cosine",
        "document_chunks",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
