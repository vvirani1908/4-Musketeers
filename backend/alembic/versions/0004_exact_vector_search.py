"""Use exact pgvector cosine search for the small development dataset."""
from typing import Sequence, Union

from alembic import op


revision: str = "0004_exact_vector_search"
down_revision: Union[str, None] = "0003_rebuild_embedding_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove only the approximate vector index; keep the table and vectors."""
    op.drop_index("ix_document_chunks_embedding_cosine", table_name="document_chunks")


def downgrade() -> None:
    """Restore the 0003 IVFFlat index definition without changing stored vectors."""
    op.create_index(
        "ix_document_chunks_embedding_cosine",
        "document_chunks",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"lists": 10},
    )
