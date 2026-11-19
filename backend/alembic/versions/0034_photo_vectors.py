"""Per-photo SigLIP vectors for «Похожие объекты» (Stanislav 11-20): a flat shot again from other angles, or an edited
copy, shares no dHash photo but its photos look alike. One row per photo of an object (property_media) or an outside ad
(listings.photos[n]); vec NULL = unreadable, not tried again. listings.photo_vec_sig = md5(photos) the ad's rows were
made from (photos changed → made again). Filled by the worker (app/embeddings.py photos).

Revision ID: 0034
Revises: 0033
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0034'
down_revision: Union[str, Sequence[str], None] = '0033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    v = op.get_bind().scalar(sa.text("SELECT extnamespace::regnamespace::text FROM pg_extension WHERE extname = 'vector'"))
    op.execute(f"""CREATE TABLE photo_vectors (
        id bigserial PRIMARY KEY,
        media_id integer UNIQUE REFERENCES property_media(id) ON DELETE CASCADE,
        listing_id text REFERENCES listings(id) ON DELETE CASCADE,
        n integer,
        vec {v}.vector(768),
        CHECK ((media_id IS NULL) <> (listing_id IS NULL)))""")
    op.execute("CREATE INDEX photo_vectors_listing_idx ON photo_vectors (listing_id)")
    op.execute(f"CREATE INDEX photo_vectors_vec_idx ON photo_vectors USING hnsw (vec {v}.vector_cosine_ops)")
    op.add_column("listings", sa.Column("photo_vec_sig", sa.Text))


def downgrade() -> None:
    op.drop_column("listings", "photo_vec_sig")
    op.execute("DROP TABLE photo_vectors")
