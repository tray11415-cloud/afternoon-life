"""Persistent actor-scoped vector retrieval. No cloud token cost.

The default Chinese character/bigram hashing vector is lexical, not a trained
semantic embedding. An optional local Ollama embedding provider replaces it.
Event hashes and the current journal are checked before every retrieval, so
loading an older save or branching cannot import future/unauthorised memories.
"""
from __future__ import annotations
import hashlib, json, math, re, sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.request import Request, build_opener
from urllib.parse import urlsplit
from .model import canonical
from .policies import _NoRedirect

def content_text(event):
    """Search human content, not repeated JSON keys/actor ids."""
    data=event['data']
    text=' '.join(str(data[k]) for k in ('text','title','purpose','knowledge','scope','reason') if k in data)
    if event['kind']=='information_shared':
        text+=' '+content_text(data['source'])
    return text

def terms(text):
    # Chinese bigrams keep concrete names usable without a model download.
    chunks=re.findall(r'[\u3400-\u9fff]+|[a-z0-9]+',text.lower())
    result=[]
    for chunk in chunks:
        if re.fullmatch(r'[a-z0-9]+',chunk): result.append(chunk)
        elif len(chunk)==1: result.append(chunk)
        else: result.extend(chunk[i:i+2] for i in range(len(chunk)-1))
    return result

def importance(event):
    # Observed outcomes/commitments, never inferred affection or motives.
    return {'wardrobe_bought':.7,'wardrobe_worn':.6,'economy_job_completed':.85,'economy_bought':.8,'economy_consumed':.7,'invitation_created':.8,'invitation_status':.95,'venue_completed':.75,
            'work_completed':.7,'information_shared':.45,'message_spoken':.55}.get(event['kind'],.2)

class LexicalEmbedding:
    name = 'lexical-hash-v1-256'
    def embed(self, text):
        chars = re.findall(r'[\u3400-\u9fff]|[a-z0-9]+', text.lower())
        terms = chars + [a+b for a,b in zip(chars,chars[1:])]
        vector=[0.0]*256
        for term in terms:
            h=int.from_bytes(hashlib.blake2s(term.encode(),digest_size=4).digest(),'little')
            vector[h%256]+=1 if (h>>8)&1 else -1
        norm=math.sqrt(sum(x*x for x in vector)) or 1
        return [x/norm for x in vector]

class OllamaEmbedding:
    def __init__(self, base_url, model):
        url=urlsplit(base_url)
        if url.scheme!='http' or url.hostname not in {'127.0.0.1','localhost','::1'} or url.username or url.password or url.query or url.fragment:
            raise ValueError('embedding provider must be localhost')
        if not isinstance(model,str) or not model: raise ValueError('embedding model required')
        self.endpoint=base_url.rstrip('/')+'/api/embed'; self.model=model
        self.name='ollama:'+base_url+':'+model
        self.opener=build_opener(_NoRedirect)
    def embed(self,text):
        req=Request(self.endpoint,canonical({'model':self.model,'input':text[:6000]}).encode(),{'Content-Type':'application/json'},method='POST')
        with self.opener.open(req,timeout=15) as response: raw=response.read(1024*1024+1)
        if len(raw)>1024*1024: raise ValueError('embedding too large')
        value=json.loads(raw)['embeddings'][0]
        if not isinstance(value,list) or not 8<=len(value)<=8192 or any(type(x) not in (int,float) or not math.isfinite(x) for x in value):
            raise ValueError('invalid embedding')
        norm=math.sqrt(sum(x*x for x in value))
        if norm==0: raise ValueError('zero embedding')
        return [x/norm for x in value]

class VectorMemory:
    def __init__(self,path: Path,embedding=None):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.embedding=embedding or LexicalEmbedding()
        # Input projection changed in v0.7; never mix with JSON-key vectors.
        self.provider=self.embedding.name+'|content-v2'
        self.last_revision=None; self.last_engine=None; self.error=None
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS memories (owner TEXT, event_hash TEXT, provider TEXT, event_id TEXT, vector TEXT, event TEXT, PRIMARY KEY(owner,event_hash,provider))')
            db.execute('CREATE INDEX IF NOT EXISTS owner_provider ON memories(owner,provider)')
            db.execute('CREATE TABLE IF NOT EXISTS memory_meta (owner TEXT, event_hash TEXT, location TEXT, importance REAL, PRIMARY KEY(owner,event_hash))')
            db.execute('CREATE TABLE IF NOT EXISTS memory_presentations (owner TEXT, event_hash TEXT, anchor_hash TEXT, tick INTEGER, PRIMARY KEY(owner,event_hash,anchor_hash))')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db: yield db
        finally: db.close()
    def sync(self,engine):
        if self.last_engine is engine and self.last_revision==engine.revision: return
        # Re-index only observed events. One shared vector can have multiple ACLs.
        try:
            with self.connect() as db:
                indexed_meta=set(db.execute('SELECT owner,event_hash FROM memory_meta'))
                locations={a['id']:a['location'] for a in engine.journal()['genesis']['actors']}
                for event in engine.journal()['events']:
                    if event['kind']=='actor_moved':
                        locations[event['actor']]=event['data']['to']
                    if not event['remember']: continue
                    for owner in event['audience']:
                        # Scene is where THIS observer experienced the event.
                        location=event['data'].get('venue') if event['kind']=='venue_completed' and event['actor']==owner else locations[owner]
                        if (owner,event['hash']) not in indexed_meta:
                            db.execute('INSERT OR IGNORE INTO memory_meta VALUES (?,?,?,?)',(owner,event['hash'],location,importance(event)))
                    known=db.execute('SELECT 1 FROM memories WHERE event_hash=? AND provider=? LIMIT 1',(event['hash'],self.provider)).fetchone()
                    if known: continue
                    projected={k:event[k] for k in ('id','tick','kind','actor','data')}
                    vector=json.dumps(self.embedding.embed(content_text(projected)))
                    db.executemany('INSERT OR IGNORE INTO memories VALUES (?,?,?,?,?,?)',
                        [(owner,event['hash'],self.provider,event['id'],vector,canonical(projected)) for owner in event['audience']])
            self.last_engine=engine; self.last_revision=engine.revision; self.error=None
        except Exception:
            # Do not silently mix vectors from different providers. Recent known
            # events remain available from the authoritative engine on failure.
            self.error='local_embedding_unavailable'
    def ranked(self,engine,owner,query,limit=4):
        self.sync(engine)
        if self.error: return []
        journal=engine.journal()['events']
        anchors={e['hash'] for e in journal}
        allowed={e['hash'] for e in journal if e['remember'] and owner in e['audience']}
        q=self.embedding.embed(query)
        query_terms=set(terms(query)); documents=[]; scores=[]
        scene=engine.view(owner,memory_limit=1)['self']['location']
        with self.connect() as db:
            presentations={}
            for event_hash,anchor,tick in db.execute('SELECT event_hash,anchor_hash,tick FROM memory_presentations WHERE owner=?',(owner,)):
                if anchor in anchors:
                    count,last=presentations.get(event_hash,(0,0));presentations[event_hash]=(count+1,max(last,tick))
            for event_hash,vector,event in db.execute('SELECT event_hash,vector,event FROM memories WHERE owner=? AND provider=?',(owner,self.provider)):
                if event_hash not in allowed: continue
                event=json.loads(event); tokens=terms(content_text(event))
                if not tokens: continue
                v=json.loads(vector)
                if len(v)!=len(q): continue
                metadata=db.execute('SELECT location,importance FROM memory_meta WHERE owner=? AND event_hash=?',(owner,event_hash)).fetchone()
                documents.append((event_hash,event,tokens,sum(a*b for a,b in zip(q,v)),metadata))
        average=sum(len(d[2]) for d in documents)/max(1,len(documents))
        frequency={term:sum(term in set(d[2]) for d in documents) for term in query_terms}
        for event_hash,event,tokens,similarity,metadata in documents:
            overlap=query_terms.intersection(tokens)
            # Lexical hash collisions must not recall an unrelated secret/topic.
            if not overlap and (isinstance(self.embedding,LexicalEmbedding) or similarity<.35): continue
            lexical=0.0
            for term in overlap:
                tf=tokens.count(term);idf=math.log(1+(len(documents)-frequency[term]+.5)/(frequency[term]+.5))
                lexical+=idf*tf*2.2/(tf+1.2*(.25+.75*len(tokens)/max(1,average)))
            lexical=lexical/(1+lexical)
            count,last=presentations.get(event_hash,(0,event['tick']))
            age=max(0,engine.tick-max(event['tick'],last))
            retention=.2+.8*2**(-age/(1440*7*(1+min(count,12)/4)))
            salience=metadata[1] if metadata else importance(event)
            same_scene=float(bool(metadata and metadata[0]==scene))
            # Relevance dominates; time/scene/presentation only order relevant hits.
            score=.52*lexical+.23*max(0,similarity)+.12*salience*retention+.08*count/(1+count)+.05*same_scene
            breakdown={'lexical':round(lexical,3),'similarity':round(similarity,3),
                       'importance':salience,'retention':round(retention,3),'presentations':count,
                       'scene':metadata[0] if metadata else None,'score':round(score,3),
                       'evidence':event['data'].get('epistemic_status','observed_event')}
            scores.append((score,event,breakdown))
        scores.sort(key=lambda row:(row[0],row[1]['tick']),reverse=True)
        return [{'event':event,'signals':signals} for _,event,signals in scores[:limit]]

    def retrieve(self,engine,owner,query,limit=4):
        return [hit['event'] for hit in self.ranked(engine,owner,query,limit)]

    def presented(self,engine,owner,context):
        """Count only context delivered to an accepted decision, once per anchor.

        Retrieval/preview is read-only. This is exposure, not proof the model used
        a memory. Anchor hashes prevent future-branch reinforcement leaking back.
        """
        events=engine.journal()['events']
        if not events: return
        ids={hit['id'] for hit in context.get('memory_retrieval',{}).get('hits',[])}
        anchor=events[-1]['hash']
        with self.connect() as db:
            db.executemany('INSERT OR IGNORE INTO memory_presentations VALUES (?,?,?,?)',
                [(owner,e['hash'],anchor,engine.tick) for e in events
                 if e['id'] in ids and e['remember'] and owner in e['audience']])
    def context(self,engine,owner,query,nearby=None):
        view=engine.view(owner,memory_limit=6)
        # The wardrobe service adds compact owned IDs separately. Rendering
        # descriptions and model provenance belong in assets, not each turn.
        view['self'].pop('wardrobe',None)
        try: hits=self.ranked(engine,owner,query);relevant=[h['event'] for h in hits]
        except Exception:
            relevant=[]; hits=[]; self.error='local_embedding_unavailable'
        recent=view['memories']; known={e['id'] for e in recent}
        view['memories']=[e for e in relevant if e['id'] not in known]+recent
        for event in view['memories']:
            if event['kind']=='wardrobe_bought':
                data=event['data'];item=data['item']
                event['data']={'item':item['id'],'title':item['title'],'style':item['style'],'price':data['price'],'day':data['day']}
        if nearby is not None: view['nearby']=nearby
        # Keep recent interaction and own state intact; trim older retrieved
        # events first, then old recent entries. Never pass a whole-world dump.
        view['memory_retrieval']={'provider':self.embedding.name,'status':'recent_only' if self.error else 'ready',
                                 'ranking':'hybrid-episode-v1','hits':[{'id':h['event']['id'],**h['signals']} for h in hits]}
        while len(canonical(view).encode())>10000 and len(view['memories'])>1: view['memories'].pop(0)
        retained={e['id'] for e in view['memories']}
        view['memory_retrieval']['hits']=[h for h in view['memory_retrieval']['hits'] if h['id'] in retained]
        return view
