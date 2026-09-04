import json
from pathlib import Path
import pytest
from continuity import ContinuityEngine
ROOT=Path(__file__).parent/'fixtures';HOLDOUT=json.loads((ROOT/'cp12_holdout.json').read_text())['queries']
@pytest.mark.parametrize('case',HOLDOUT)
def test_holdout_critical_queries(case,tmp_path):
 e=ContinuityEngine(tmp_path/'x.db');e.rebuild(e.load_bundle(ROOT/'cp12_sources.json'));result=e.retrieve(case['query'],max_records=8,max_chars=8192,max_evidence_refs=8);values=[item['resolution']['value'] for item in result['results'] if item['resolution']['state']=='CURRENT'];assert case['expected'] in values
def test_holdout_accuracy_is_100_percent(tmp_path):
 e=ContinuityEngine(tmp_path/'x.db');e.rebuild(e.load_bundle(ROOT/'cp12_sources.json'));hits=0
 for case in HOLDOUT:
  values=[item['resolution']['value'] for item in e.retrieve(case['query'])['results'] if item['resolution']['state']=='CURRENT'];hits+=case['expected'] in values
 assert hits==len(HOLDOUT)
