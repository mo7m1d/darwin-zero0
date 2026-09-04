from __future__ import annotations
import json,os,re,sqlite3
from pathlib import Path
from .model import ContextError,ContextFact,UNTRUSTED_SOURCES,canonical_json,normalized,payload_hash,validate_source_ref

AUTHORITY={
 "POLICY":{"owner_constitution":100,"owner_approval":100,"accepted_control":90},
 "SOURCE_CODE":{"canonical_git":100,"accepted_evidence":90},
 "LIVE_RUNTIME":{"live_runtime":100,"runtime_telemetry":90,"acceptance_gate":85,"readme":10},
 "TASK_STATE":{"supervisor":100,"kanban":95,"acceptance_gate":90,"readme":10},
 "ACCEPTANCE":{"acceptance_gate":100},
 "RECOVERY":{"recovery_manifest":100,"recovery_ledger":100,"accepted_evidence":90},
 "RUN_CONTROL":{"budget_store":100,"owner_approval":100,"accepted_evidence":90},
 "PROJECT":{"accepted_evidence":100,"canonical_git":90,"kanban":85,"readme":10},
 "DERIVED":{},"EXTERNAL":{},
}
TRUSTED={"AUTHORITATIVE","ACCEPTED"}
class ClosingConnection(sqlite3.Connection):
 def __exit__(self,*args):
  try:return super().__exit__(*args)
  finally:self.close()
class Resolution(dict):
 @property
 def state(self):return self["state"]

class ContinuityEngine:
 def __init__(self,database):self.database=Path(database);self.database.parent.mkdir(parents=True,exist_ok=True);self._initialize()
 def connect(self):
  db=sqlite3.connect(self.database,timeout=30,factory=ClosingConnection);db.row_factory=sqlite3.Row;db.execute("PRAGMA foreign_keys=ON");return db
 def _initialize(self):
  with self.connect() as db:db.executescript("""
CREATE TABLE IF NOT EXISTS sources(source_ref TEXT PRIMARY KEY,normalized_ref TEXT NOT NULL UNIQUE,source_type TEXT NOT NULL,source_hash TEXT NOT NULL,available INTEGER NOT NULL CHECK(available IN(0,1)));
CREATE TABLE IF NOT EXISTS facts(fact_id TEXT PRIMARY KEY,fact_type TEXT NOT NULL,fact_class TEXT NOT NULL,subject TEXT NOT NULL,value_json TEXT NOT NULL,value_hash TEXT NOT NULL,source_type TEXT NOT NULL,source_ref TEXT NOT NULL REFERENCES sources(source_ref),source_hash TEXT NOT NULL,observed_at TEXT NOT NULL,accepted_at TEXT,authority TEXT NOT NULL,status TEXT NOT NULL,supersedes_json TEXT NOT NULL,superseded_by TEXT,confidence INTEGER,generated_by_json TEXT NOT NULL,schema_version TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS fact_subject ON facts(fact_class,subject,status);
CREATE TABLE IF NOT EXISTS build_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),bundle_hash TEXT NOT NULL,built_at TEXT NOT NULL);
""")
 @staticmethod
 def load_bundle(path):
  validate_source_ref(str(path))
  try:data=json.loads(Path(path).read_text(encoding="utf-8"))
  except (OSError,json.JSONDecodeError) as exc:raise ContextError("source bundle unavailable or corrupt") from exc
  if data.get("schema")!="darwin.context.source-bundle.v1":raise ContextError("source bundle schema mismatch")
  return data
 @staticmethod
 def rank(fact):return AUTHORITY.get(fact.fact_class,{}).get(fact.source_type,0)
 @classmethod
 def eligible(cls,fact):return fact.status=="CURRENT" and fact.authority in TRUSTED and fact.source_type not in UNTRUSTED_SOURCES and cls.rank(fact)>0 and bool(fact.accepted_at or fact.authority=="AUTHORITATIVE")
 def rebuild(self,bundle):
  sources,facts=bundle.get("sources"),bundle.get("facts")
  if not isinstance(sources,list) or not isinstance(facts,list):raise ContextError("invalid source bundle")
  temporary=self.database.with_name(self.database.name+".rebuild")
  if temporary.exists():temporary.unlink()
  fresh=ContinuityEngine(temporary)
  try:
   with fresh.connect() as db:
    for item in sources:
     validate_source_ref(item["source_ref"]);source_hash=item["source_hash"]
     if not item.get("available",True):raise ContextError("source unavailable")
     if len(source_hash)!=64 or any(ch not in "0123456789abcdef" for ch in source_hash):raise ContextError("invalid registry hash")
     db.execute("INSERT INTO sources VALUES(?,?,?,?,1)",(item["source_ref"],normalized(item["source_ref"]),item["source_type"],source_hash))
    validated=[];identities={}
    for raw in facts:
     fact=ContextFact(**raw).validate();digest=payload_hash(fact.dictionary())
     if fact.fact_id in identities and identities[fact.fact_id]!=digest:raise ContextError("fact_id payload collision")
     identities[fact.fact_id]=digest
     source=db.execute("SELECT source_type,source_hash FROM sources WHERE source_ref=?",(fact.source_ref,)).fetchone()
     if not source or source[0]!=fact.source_type or source[1]!=fact.source_hash:raise ContextError("forged source reference/hash")
     validated.append(fact)
    ids={fact.fact_id for fact in validated}
    for fact in validated:
     if any(prior not in ids for prior in fact.supersedes):raise ContextError("supersedes missing fact")
     db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(fact.fact_id,fact.fact_type,fact.fact_class,fact.subject,canonical_json(fact.value),payload_hash(fact.value),fact.source_type,fact.source_ref,fact.source_hash,fact.observed_at,fact.accepted_at,fact.authority,fact.status,canonical_json(fact.supersedes),fact.superseded_by,fact.confidence,canonical_json(fact.generated_by),fact.schema_version))
    by_id={fact.fact_id:fact for fact in validated}
    for fact in validated:
     if not self.eligible(fact):continue
     for prior_id in fact.supersedes:
      prior=by_id[prior_id]
      if (prior.fact_class,prior.fact_type,normalized(prior.subject))!=(fact.fact_class,fact.fact_type,normalized(fact.subject)):raise ContextError("invalid supersession identity")
      if self.rank(fact)>=self.rank(prior):db.execute("UPDATE facts SET status='SUPERSEDED',superseded_by=? WHERE fact_id=?",(fact.fact_id,prior_id))
    db.execute("INSERT INTO build_meta VALUES(1,?,datetime('now'))",(payload_hash(bundle),));db.commit()
   os.replace(temporary,self.database)
  finally:
   if temporary.exists():temporary.unlink()
 def fact_from_row(self,row):
  return ContextFact(fact_id=row["fact_id"],fact_type=row["fact_type"],fact_class=row["fact_class"],subject=row["subject"],value=json.loads(row["value_json"]),source_type=row["source_type"],source_ref=row["source_ref"],source_hash=row["source_hash"],observed_at=row["observed_at"],accepted_at=row["accepted_at"],authority=row["authority"],status=row["status"],supersedes=json.loads(row["supersedes_json"]),superseded_by=row["superseded_by"],confidence=row["confidence"],generated_by=json.loads(row["generated_by_json"]),schema_version=row["schema_version"])
 def validate_sources(self,probe):
  with self.connect() as db:
   for row in db.execute("SELECT source_ref,source_hash FROM sources"):
    if probe(row[0])!=row[1]:raise ContextError("source disappeared or changed")
 def resolve(self,fact_class,subject):
  with self.connect() as db:rows=db.execute("SELECT * FROM facts WHERE fact_class=? AND lower(subject)=lower(?)",(fact_class,subject)).fetchall()
  facts=[self.fact_from_row(row) for row in rows];eligible=[fact for fact in facts if self.eligible(fact)]
  if not eligible:return Resolution(state="UNKNOWN",value=None,facts=[fact.dictionary() for fact in facts],conflicts=[])
  best=max(self.rank(fact) for fact in eligible);winners=[fact for fact in eligible if self.rank(fact)==best]
  if len({payload_hash(fact.value) for fact in winners})>1:return Resolution(state="CONFLICT",value=None,facts=[fact.dictionary() for fact in winners],conflicts=[fact.fact_id for fact in winners])
  winner=sorted(winners,key=lambda fact:fact.fact_id)[0]
  return Resolution(state="CURRENT",value=winner.value,facts=[winner.dictionary()],conflicts=[])
 def retrieve(self,query,max_records=8,max_chars=4096,max_evidence_refs=8):
  if any(isinstance(v,bool) or not isinstance(v,int) or v<1 for v in (max_records,max_chars,max_evidence_refs)):raise ContextError("invalid retrieval bounds")
  tokens={token for token in re.findall(r"[a-z0-9]+",normalized(query)) if len(token)>1}
  with self.connect() as db:rows=db.execute("SELECT * FROM facts").fetchall()
  scored=[]
  for row in rows:
   fact=self.fact_from_row(row);hay=normalized(f"{fact.fact_type} {fact.subject} {canonical_json(fact.value)}");overlap=sum(token in hay for token in tokens)
   if overlap:scored.append((overlap,self.rank(fact),fact.fact_id,fact))
  scored.sort(key=lambda item:(-item[0],-item[1],item[2]));results=[];chars=refs=0;groups=set()
  for score,rank,_,fact in scored:
   group=(fact.fact_class,normalized(fact.subject))
   if group in groups:continue
   resolution=self.resolve(fact.fact_class,fact.subject);blob=canonical_json(resolution);count=len(resolution.get("facts",[]))
   if len(results)>=max_records or chars+len(blob)>max_chars or refs+count>max_evidence_refs:continue
   groups.add(group);chars+=len(blob);refs+=count;results.append({"fact_class":fact.fact_class,"subject":fact.subject,"resolution":dict(resolution),"score":score,"rationale":f"lexical_overlap={score};authority_rank={rank}","content_role":"data","untrusted":fact.source_type in UNTRUSTED_SOURCES})
  return {"query":query,"results":results,"bounded":True,"max_records":max_records,"max_chars":max_chars,"max_evidence_refs":max_evidence_refs}
 def assemble(self,subjects,max_records=12,max_chars=8192,max_evidence_refs=16):
  records=[];chars=refs=0
  for fact_class,subject in subjects:
   result=self.resolve(fact_class,subject);blob=canonical_json(result);count=len(result.get("facts",[]))
   if len(records)>=max_records or chars+len(blob)>max_chars or refs+count>max_evidence_refs:break
   records.append({"fact_class":fact_class,"subject":subject,"resolution":dict(result)});chars+=len(blob);refs+=count
  return {"layer":"L1_ACTIVE_CONTEXT","records":records,"chars":chars,"evidence_refs":refs}
 def history(self,fact_class,subject):
  with self.connect() as db:rows=db.execute("SELECT * FROM facts WHERE fact_class=? AND lower(subject)=lower(?) ORDER BY observed_at,fact_id",(fact_class,subject)).fetchall()
  return [self.fact_from_row(row).dictionary() for row in rows]
