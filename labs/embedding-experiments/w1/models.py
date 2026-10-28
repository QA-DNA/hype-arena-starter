# Model registry for worker w1: id -> (query_prefix, doc_prefix, trust_remote_code)
# query_prefix: used on the query side of asymmetric tasks (zero-shot rows).  doc_prefix: used on descriptions (docs).
# symmetric prefix: used for every symmetric task (probe, kNN, retrieval, truth) = sym.
MODELS = {
 'sentence-transformers/all-MiniLM-L6-v2':        dict(sym='', q='', d='', trc=False),
 'sentence-transformers/all-MiniLM-L12-v2':       dict(sym='', q='', d='', trc=False),
 'sentence-transformers/all-mpnet-base-v2':       dict(sym='', q='', d='', trc=False),
 'sentence-transformers/paraphrase-MiniLM-L3-v2': dict(sym='', q='', d='', trc=False),
 'BAAI/bge-small-en-v1.5':                        dict(sym='', q='Represent this sentence for searching relevant passages: ', d='', trc=False),
 'BAAI/bge-base-en-v1.5':                         dict(sym='', q='Represent this sentence for searching relevant passages: ', d='', trc=False),
 'thenlper/gte-small':                            dict(sym='', q='', d='', trc=False),
 'thenlper/gte-base':                             dict(sym='', q='', d='', trc=False),
 'intfloat/e5-small-v2':                          dict(sym='query: ', q='query: ', d='passage: ', trc=False),
 'intfloat/e5-base-v2':                           dict(sym='query: ', q='query: ', d='passage: ', trc=False),
 'Snowflake/snowflake-arctic-embed-s':            dict(sym='', q='Represent this sentence for searching relevant passages: ', d='', trc=False),
 'Snowflake/snowflake-arctic-embed-m-v1.5':       dict(sym='', q='Represent this sentence for searching relevant passages: ', d='', trc=False),
 'Alibaba-NLP/gte-base-en-v1.5':                  dict(sym='', q='', d='', trc=True),
 'jinaai/jina-embeddings-v2-small-en':            dict(sym='', q='', d='', trc=True),
 'mixedbread-ai/mxbai-embed-xsmall-v1':           dict(sym='', q='Represent this sentence for searching relevant passages: ', d='', trc=False),
}
# code repos pulled by trust_remote_code models (auto_map points at them)
REMOTE_CODE_REPOS = ['Alibaba-NLP/new-impl', 'jinaai/jina-bert-implementation']
PATTERNS = ['*.json', '*.txt', '*.safetensors', '*.model', '*.py', '*.jsonl']
