import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from run_control import Action,AutoWorkController,BudgetDenied,BudgetError,BudgetStore

def limits(n=20, seconds=1000):
 return {"tool_calls_total":n,"mutation_tool_calls":n,"network_tool_calls":n,"external_effect_actions":n,"recovery_attempts":n,"candidate_rebuilds":n,"wall_clock_seconds":seconds,"child_runs":n,"spend_cents":0}
def fresh(path,n=20,clock=None):
 s=BudgetStore(path/'budget.sqlite3',clock);s.create_run('root','task',limits(n));return s
def denied(call):
 with pytest.raises((BudgetDenied,BudgetError,sqlite3.DatabaseError,sqlite3.IntegrityError)):call()
def controller(store,retry=0,approve=True,safe=True): return AutoWorkController(store,'root',lambda:retry,lambda a:safe,lambda k,a:approve)

def test_states_defaults_and_status(tmp_path):
 s=fresh(tmp_path);assert s.status('root')['state']=='RUNNING';assert s.status('root')['budgets']['spend_cents']['limit']==0
def test_restart_persistence(tmp_path):
 s=fresh(tmp_path);s.reserve('root',{'tool_calls_total':1});assert BudgetStore(s.path).status('root')['budgets']['tool_calls_total']['consumed']==1
def test_failed_action_consumed(tmp_path):
 s=fresh(tmp_path);c=controller(s)
 with pytest.raises(RuntimeError):c.execute([Action('x')],lambda a:(_ for _ in ()).throw(RuntimeError()),1)
 assert s.status('root')['budgets']['tool_calls_total']['consumed']==1
def test_parent_child_aggregate(tmp_path):
 s=fresh(tmp_path,2);s.create_run('child','child-task',limits(2),'root');s.reserve('child',{'tool_calls_total':2});assert s.status('root')['budgets']['tool_calls_total']['consumed']==2;denied(lambda:s.reserve('child',{'tool_calls_total':1}))
def test_concurrent_reservation(tmp_path):
 s=fresh(tmp_path,10)
 def one(_):
  try:BudgetStore(s.path).reserve('root',{'tool_calls_total':1});return 1
  except BudgetDenied:return 0
 with ThreadPoolExecutor(max_workers=20) as pool:assert sum(pool.map(one,range(30)))==10
 assert s.status('root')['budgets']['tool_calls_total']['consumed']==10
def test_pause_kill_freeze(tmp_path):
 s=fresh(tmp_path);s.set_state('root','PAUSED');denied(lambda:s.reserve('root',{'tool_calls_total':1}));s.set_state('root','RUNNING',True,'owner');s.set_state('root','KILLED',True,'owner');denied(lambda:s.set_state('root','RUNNING',True,'owner'))
def test_global_freeze(tmp_path):
 s=fresh(tmp_path);s.set_frozen(True,True,'owner');denied(lambda:s.create_run('x','x',limits()));denied(lambda:s.reserve('root',{'tool_calls_total':1}))
def test_owner_override_and_reduction(tmp_path):
 s=fresh(tmp_path,1);denied(lambda:s.change_limit('root','tool_calls_total',2));s.change_limit('root','tool_calls_total',2,'owner',True,'ticket');s.change_limit('root','tool_calls_total',1);assert s.status('root')['budgets']['tool_calls_total']['limit']==1
def test_clock_regression(tmp_path):
 now=[100];s=fresh(tmp_path,clock=lambda:now[0]);now[0]=99;denied(lambda:s.reserve('root',{'tool_calls_total':1}));assert s.status('root')['state']=='EXHAUSTED'
def test_bounded_zero_spend_drill(tmp_path):
 s=fresh(tmp_path);c=controller(s);assert c.execute([Action('read')]*4,lambda a:a.name,2)==['read','read'];denied(lambda:controller(s,approve=False).execute([Action('paid',spend_cents=1)],lambda a:1,1))
def test_retry_and_safety_boundaries(tmp_path):
 s=fresh(tmp_path);denied(lambda:controller(s,retry=3).execute([Action('x')],lambda a:1,1));denied(lambda:controller(s,safe=False).execute([Action('x')],lambda a:1,1))
def test_hash_chain(tmp_path):
 s=fresh(tmp_path);s.reserve('root',{'tool_calls_total':1});assert s.verify_ledger()

def test_safety_v28_executable_canaries():
 import importlib.util
 from pathlib import Path
 path=Path(__file__).parents[1]/'integrations/hermes/darwin-tool-policy-v2.8/__init__.py'
 spec=importlib.util.spec_from_file_location('safety_v28_candidate',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 assert module.handle_tool('terminal',{'command':'Start-Process worker.ps1'})['action']=='block'
 assert module.handle_tool('execute_code',{'code':'import os; os.system("nohup worker &")'})['action']=='block'
 assert module.handle_tool('write_file',{'path':str(Path(module.BUDGET_ROOT)/'budget.sqlite3'),'content':'tamper'})['action']=='block'
