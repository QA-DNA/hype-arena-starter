import json
R=[json.loads(l) for l in open('/tmp/veridyct-emb/results/w1.jsonl')]
REF=json.load(open('/tmp/veridyct-emb/w1/tfidf_ref.json')); A,F=REF['attr'],REF['false']
SH={'all-MiniLM-L6-v2':'MiniLM-L6','all-MiniLM-L12-v2':'MiniLM-L12','all-mpnet-base-v2':'mpnet-base','paraphrase-MiniLM-L3-v2':'para-MiniLM-L3','bge-small-en-v1.5':'bge-small','bge-base-en-v1.5':'bge-base','gte-small':'gte-small','gte-base':'gte-base','e5-small-v2':'e5-small','e5-base-v2':'e5-base','snowflake-arctic-embed-s':'arctic-s','snowflake-arctic-embed-m-v1.5':'arctic-m-1.5','gte-base-en-v1.5':'gte-base-1.5','jina-embeddings-v2-small-en':'jina-v2-small','mxbai-embed-xsmall-v1':'mxbai-xs'}
I={(r['model'].split('/')[-1],r['task'],r['variant']):r for r in R}
def col(task,var,key):
    return {SH[m]:I[(m,t,v)]['metrics'][key] for (m,t,v) in I if t==task and v==var and I[(m,t,v)]['metrics'].get(key) is not None}
def top(name,d,ref=None,n=3):
    s=sorted(d.items(),key=lambda kv:-kv[1]); print(name.ljust(34),' | '.join(f'{k} {v:.3f}' for k,v in s[:n]), (f'  (ref {ref:.3f}; best {s[0][1]-ref:+.3f}; models above ref: {sum(v>ref for v in d.values())}/{len(d)})' if ref is not None else ''), f'  worst {s[-1][0]} {s[-1][1]:.3f}')
top('attr_probe C=10 acc_all',col('attr_probe','LR_C10','acc_all'),A['acc_all'])
top('attr_probe C=10 ge5',col('attr_probe','LR_C10','acc_ge5'),A['acc_ge5'])
top('attr_probe C=10 1to4',col('attr_probe','LR_C10','acc_1to4'),A['acc_1to4'])
top('attr_probe C=100 acc_all',col('attr_probe','LR_C100','acc_all'),A['acc_all'])
top('attr_probe C=1000 acc_all',col('attr_probe','LR_C1000','acc_all'),A['acc_all'])
top('attr_knn acc_all',col('attr_knn','k5','acc_all'),A['acc_all'])
top('attr_zeroshot describe',col('attr_zeroshot','describe','acc_all'))
top('attr_zeroshot words',col('attr_zeroshot','attr_words_only','acc_all'))
top('attr_hybrid w1 acc_all',col('attr_hybrid','z_probe+z_zeroshot','acc_all'),A['acc_all'])
top('attr_hybrid w1 unseen76',col('attr_hybrid','z_probe+z_zeroshot','acc_unseen'),0.0)
top('attr_hybrid C=100',col('attr_hybrid','C100_z_probe+z_zeroshot','acc_all'),A['acc_all'])
top('attr_hybrid C=1000',col('attr_hybrid','C1000_z_probe+z_zeroshot','acc_all'),A['acc_all'])
top('attr_unseen hybrid w1 (spec)',col('attr_unseen','hybrid_z_probe+z_zeroshot','acc_all'))
top('attr_unseen hybrid max-imp',col('attr_unseen','hybrid_unseen_max','acc_all'))
top('attr_unseen zeroshot alone',col('attr_unseen','zeroshot_alone','acc_all'))
kr=col('key_retrieval','cosine_k10','recall_at_k'); tf=[r for r in R if r['task']=='key_retrieval'][0]['metrics']['tfidf_recall_at_k']
top('key_retrieval recall@10',kr,tf)
top('key_retrieval mrr',col('key_retrieval','cosine_k10','mrr'),[r for r in R if r['task']=='key_retrieval'][0]['metrics']['tfidf_mrr'])
top('truth_false auc',col('truth_false','LR_balanced_C1','auc'),F['auc'])
top('truth_three arena_best',col('truth_three','LR_balanced_C1','arena_best'),0.687)
top('truth_three macro_f1',col('truth_three','LR_balanced_C1','macro_f1'))
sp={SH[m]:I[(m,'speed','bs32_2000texts')]['metrics']['sentences_per_s'] for (m,t,v) in I if t=='speed' and v=='bs32_2000texts'}
top('speed wall sents/s',sp,None,5)
cp={SH[m]:I[(m,'speed','bs32_2000texts_cpu_time')]['metrics']['sents_per_cpu_s'] for (m,t,v) in I if t=='speed' and v=='bs32_2000texts_cpu_time'}
if cp: top('speed sents per cpu-s',cp,None,5)
from collections import Counter
print(Counter(r['model'].split('/')[-1] for r in R))
