"""Gold-only benchmark evaluation helpers."""
from __future__ import annotations
import json
from pathlib import Path
from collections import Counter
from .dataset import OUTCOMES
LABELS = sorted(OUTCOMES)

def read_jsonl(path):
    rows=[]
    for number, raw in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        line=raw.strip()
        if not line or line.startswith('#'): continue
        try: item=json.loads(line)
        except json.JSONDecodeError as exc: raise ValueError(f'{path}:{number}: invalid JSON') from exc
        if not isinstance(item, dict): raise TypeError(f'{path}:{number}: expected object')
        rows.append(item)
    return rows

def audit(items):
    statuses=Counter(str(x.get('annotation_status','missing')) for x in items)
    gold=[x for x in items if x.get('annotation_status')=='gold_verified' and x.get('gold_outcome') in OUTCOMES]
    outcomes=Counter(x['gold_outcome'] for x in gold)
    groups={}
    for x in items:
        group, split=x.get('split_group_id'), x.get('split')
        if isinstance(group,str) and isinstance(split,str) and split: groups.setdefault(group,set()).add(split)
    return {'n_items':len(items),'status_counts':dict(statuses),'gold_verified_n':len(gold),'gold_outcome_counts':{x:outcomes.get(x,0) for x in LABELS},'split_group_leakage':sorted(g for g,s in groups.items() if len(s)>1),'gold_ready':bool(gold),'note':'No gold labels: metrics unavailable, not zero.' if not gold else 'Source verification and adjudication still require human review.'}

def score(items, predictions):
    gold={}
    for x in items:
        if x.get('annotation_status')=='gold_verified' and x.get('gold_outcome') in OUTCOMES:
            key=x.get('benchmark_item_id')
            if not key: raise ValueError('gold item missing benchmark_item_id')
            if key in gold: raise ValueError(f'duplicate gold item: {key}')
            gold[key]=x['gold_outcome']
    pred={}
    for x in predictions:
        key, label=x.get('benchmark_item_id'), x.get('outcome')
        if not isinstance(key,str) or not key: raise ValueError('prediction missing benchmark_item_id')
        if label not in OUTCOMES: raise ValueError(f'invalid outcome for {key}: {label!r}')
        if key in pred: raise ValueError(f'duplicate prediction: {key}')
        pred[key]=label
    matched=sorted(set(gold)&set(pred)); missing=sorted(set(gold)-set(pred)); extra=sorted(set(pred)-set(gold))
    cm={a:{b:0 for b in LABELS} for a in LABELS}
    for key in matched: cm[gold[key]][pred[key]]+=1
    if not gold: return {'status':'unavailable','reason':'No gold_verified items; accuracy is not zero, it is unavailable.','gold_n':0,'matched_n':0,'coverage':None,'accuracy':None,'macro_f1':None,'per_class':{},'confusion_matrix':cm,'missing_prediction_ids':missing,'prediction_ids_not_in_gold':extra}
    per={}; f1s=[]
    for label in LABELS:
        tp=cm[label][label]; fp=sum(cm[a][label] for a in LABELS if a!=label); fn=sum(cm[label][b] for b in LABELS if b!=label)
        p=tp/(tp+fp) if tp+fp else 0.0; r=tp/(tp+fn) if tp+fn else 0.0; f=2*p*r/(p+r) if p+r else 0.0
        per[label]={'precision':round(p,6),'recall':round(r,6),'f1':round(f,6),'support':sum(cm[label].values())}; f1s.append(f)
    return {'status':'ok' if matched else 'unavailable','gold_n':len(gold),'matched_n':len(matched),'coverage':round(len(matched)/len(gold),6),'accuracy':round(sum(cm[x][x] for x in LABELS)/len(matched),6) if matched else None,'macro_f1':round(sum(f1s)/4,6) if matched else None,'per_class':per,'confusion_matrix':cm,'missing_prediction_ids':missing,'prediction_ids_not_in_gold':extra,'note':'Metrics use matched predictions only; report coverage and missing IDs.'}
