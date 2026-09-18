"""Deterministic record operators. Text remains byte-for-byte unchanged for offsets."""
import re
import unicodedata
from .common import digest

EMAIL = re.compile(r'(?<![\w.])[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
PHONE = re.compile(r'(?<!\d)(?:\+86[- ]?)?1[3-9]\d{9}(?!\d)')


def normalize_title(text):
    return ''.join(unicodedata.normalize('NFC', text).casefold().split())


def process_batch(records):
    result = []
    for record in records:
        reason = None
        if not isinstance(record, dict) or not all(isinstance(record.get(k), str) for k in ('source_id', 'title', 'text')):
            reason = 'schema'
        elif not record['source_id'] or not record['text'].strip() or not record['title'].strip():
            reason = 'empty'
        elif EMAIL.search(record['text']) or PHONE.search(record['text']):
            reason = 'suspected_contact_pattern'
        if reason:
            # Store source/hash/reason only, never copy suspected contact data into quarantine.
            result.append({'status':'quarantine','source_id':record.get('source_id', '') if isinstance(record, dict) else '',
                           'record_hash':digest(record),'reason':reason})
        else:
            result.append({'status':'accepted','source_id':record['source_id'], 'title':record['title'],
                           'text':record['text'],'doc_id':digest(record['text']), 'title_key':normalize_title(record['title'])})
    return result


def consolidate(processed):
    groups = {}
    quarantine = []
    for row in processed:
        if row['status'] == 'quarantine':
            quarantine.append(row)
        else:
            groups.setdefault(row['doc_id'], []).append(row)
    docs, lineage = [], []
    for doc_id, group in sorted(groups.items()):
        representative = min(group, key=lambda x:(x['source_id'], x['title']))
        docs.append({k:representative[k] for k in ('doc_id','title','title_key','text')})
        for row in sorted(group, key=lambda x:x['source_id']):
            lineage.append({'doc_id':doc_id,'source_id':row['source_id'],'title_key':row['title_key']})
    return docs, sorted(quarantine,key=lambda x:(str(x['source_id']),x['record_hash'])), lineage
