from pathlib import Path
from tempfile import TemporaryDirectory
from continuity import ContinuityEngine

fixture=Path(__file__).parent/'fixtures'/'cp12_sources.json'
with TemporaryDirectory(prefix='darwin-cp12-') as temporary:
    database=Path(temporary)/'context.sqlite3'
    engine=ContinuityEngine(database)
    bundle=engine.load_bundle(fixture)
    engine.rebuild(bundle)
    expected={
        ('PROJECT','milestone_cp09'):'COMPLETE',
        ('PROJECT','milestone_cp10'):'COMPLETE',
        ('PROJECT','milestone_cp11'):'COMPLETE',
        ('SOURCE_CODE','canonical_commit'):'185832bc4dd7a6273acb3eacf2add0d67377c6b5',
        ('LIVE_RUNTIME','safety_version'):'2.8.0',
        ('RUN_CONTROL','default_spend_cents'):0,
        ('PROJECT','current_next'):'CP12_CONTEXT_CONTINUITY_RETRIEVAL',
        ('RUN_CONTROL','model_turn_token_accounting'):'DEFERRED_TO_CP13_COST_CONTROLLER',
    }
    for identity,value in expected.items():
        assert engine.resolve(*identity)['value']==value
    database.unlink()
    engine=ContinuityEngine(database)
    engine.rebuild(bundle)
    assert engine.resolve('PROJECT','current_stage')['value']=='CP11'
print('CP12_ISOLATED_CONTINUITY_DRILL=PASS')
