from __future__ import annotations
import hashlib,json,re,unicodedata
from dataclasses import asdict,dataclass,field
from datetime import datetime
from typing import Any

STATUSES={"CURRENT","SUPERSEDED","CANDIDATE","REJECTED","UNKNOWN"}
FACT_CLASSES={"POLICY","SOURCE_CODE","LIVE_RUNTIME","TASK_STATE","ACCEPTANCE","RECOVERY","RUN_CONTROL","PROJECT","DERIVED","EXTERNAL"}
UNTRUSTED_SOURCES={"external_web","model_text","recovery_knowledge","discord","conversation"}
SECRET_PATH=re.compile(r"(?i)(^|[\\/])(\.env[^\\/]*|credentials?[^\\/]*|secrets?[^\\/]*|tokens?[^\\/]*|id_rsa|id_ed25519|[^\\/]*\.(?:pem|key|p12|pfx))($|[\\/])")
SECRET_VALUE=re.compile(r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:api[_-]?key|password|passwd|access[_-]?token|secret|otp)\s*[:=]\s*\S+|\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,})")
ID_RE=re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$");HASH_RE=re.compile(r"^[0-9a-f]{64}$")
class ContextError(RuntimeError):pass
class SecretRejected(ContextError):pass
def normalized(value):return unicodedata.normalize("NFKC",str(value)).casefold().strip()
def canonical_json(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def payload_hash(value):return hashlib.sha256(canonical_json(value).encode()).hexdigest()
def validate_timestamp(value,name):
 try:
  parsed=datetime.fromisoformat(value.replace("Z","+00:00"));assert parsed.tzinfo is not None
 except (TypeError,ValueError,AssertionError) as exc:raise ContextError(f"invalid {name}") from exc
def validate_source_ref(value):
 if not value or "\x00" in value or SECRET_PATH.search(value):raise SecretRejected("secret-like source reference rejected")
def reject_secret(value):
 text=canonical_json(value)
 if len(text.encode("utf-8"))>32768:raise ContextError("oversized fact rejected")
 if SECRET_VALUE.search(text):raise SecretRejected("secret-like value rejected")

@dataclass
class ContextFact:
 fact_id:str;fact_type:str;fact_class:str;subject:str;value:Any;source_type:str;source_ref:str;source_hash:str;observed_at:str
 accepted_at:str|None=None;authority:str="UNTRUSTED";status:str="CANDIDATE";supersedes:list[str]=field(default_factory=list);superseded_by:str|None=None;confidence:int|None=None;generated_by:dict[str,Any]=field(default_factory=dict);schema_version:str="darwin.context.fact.v1"
 def validate(self):
  self.fact_id=normalized(self.fact_id)
  if not ID_RE.fullmatch(self.fact_id):raise ContextError("invalid fact_id")
  if self.fact_class not in FACT_CLASSES or self.status not in STATUSES:raise ContextError("invalid class/status")
  if not self.fact_type or not self.subject:raise ContextError("fact identity incomplete")
  validate_source_ref(self.source_ref)
  if not HASH_RE.fullmatch(self.source_hash):raise ContextError("invalid source_hash")
  validate_timestamp(self.observed_at,"observed_at")
  if self.accepted_at:validate_timestamp(self.accepted_at,"accepted_at")
  if self.confidence is not None and (isinstance(self.confidence,bool) or not isinstance(self.confidence,int) or not 0<=self.confidence<=100):raise ContextError("invalid confidence")
  self.supersedes=[normalized(item) for item in self.supersedes];reject_secret(self.value)
  if self.source_type in UNTRUSTED_SOURCES:self.authority,self.status,self.accepted_at="UNTRUSTED","CANDIDATE",None
  return self
 def dictionary(self):return asdict(self)
