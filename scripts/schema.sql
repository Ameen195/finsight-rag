create extension if not exists vector;

create table if not exists chunks (
  id           bigserial primary key,
  company      text not null,
  fiscal_year  text not null,
  page         int  not null,
  section      text,
  content      text not null,
  is_table     boolean default false,
  embedding    vector(384),
  fts          tsvector generated always as (to_tsvector('english', content)) stored
);

create index if not exists chunks_embedding_idx on chunks using hnsw (embedding vector_cosine_ops);
create index if not exists chunks_fts_idx       on chunks using gin (fts);
create index if not exists chunks_meta_idx      on chunks (company, fiscal_year);
