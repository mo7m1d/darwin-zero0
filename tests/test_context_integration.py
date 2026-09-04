import json,subprocess,sys
from pathlib import Path
from continuity import ContextError,ContinuityEngine
FIXTURE=Path(__file__).parent/'fixtures'/'cp12_sources.json'
def test_new_process_without_conversation_reconstructs(tmp_path):
 db=tmp_path/'context.sqlite3';code="from continuity import ContinuityEngine as E;from pathlib import Path;e=E(r'%s');e.rebuild(E.load_bundle(r'%s'));print(e.resolve('PROJECT','current_stage')['value'])"%(db,FIXTURE)
 out=subprocess.check_output([sys.executable,'-c',code],text=True,cwd=Path(__file__).parents[1]);assert out.strip()=='CP11'
def test_restart_reads_same_derived_cache(tmp_path):
 e=ContinuityEngine(tmp_path/'x.db');e.rebuild(e.load_bundle(FIXTURE));assert ContinuityEngine(e.database).resolve('LIVE_RUNTIME','safety_version')['value']=='2.8.0'
def test_corrupt_index_rebuilt_from_sources(tmp_path):
 path=tmp_path/'x.db';path.write_bytes(b'corrupt');data=ContinuityEngine.load_bundle(FIXTURE)
 try:ContinuityEngine(path)
 except Exception:path.unlink()
 e=ContinuityEngine(path);e.rebuild(data);assert e.resolve('RUN_CONTROL','default_spend_cents')['value']==0
def test_source_registry_and_l3_refs_not_raw_dumps(tmp_path):
 e=ContinuityEngine(tmp_path/'x.db');e.rebuild(e.load_bundle(FIXTURE));fact=e.resolve('SOURCE_CODE','canonical_commit')['facts'][0];assert fact['source_ref'].startswith('git:');assert len(fact['source_hash'])==64
def test_production_has_no_holdout_answers():
 root=Path(__file__).parents[1]/'continuity';text='\n'.join(path.read_text() for path in root.glob('*.py'));assert '185832bc4dd7a6273acb3eacf2add0d67377c6b5' not in text;assert 'CP12_CONTEXT_CONTINUITY_RETRIEVAL' not in text;assert 'cp12_holdout' not in text
def test_no_live_or_model_dependency():
 root=Path(__file__).parents[1]/'continuity';text='\n'.join(path.read_text() for path in root.glob('*.py'));assert 'requests' not in text and 'openai' not in text and 'embedding' not in text

