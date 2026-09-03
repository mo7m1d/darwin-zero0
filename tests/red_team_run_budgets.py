import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from run_control import Action,AutoWorkController,BudgetDenied,BudgetError,BudgetStore

DIMS=("tool_calls_total","mutation_tool_calls","network_tool_calls","external_effect_actions","recovery_attempts","candidate_rebuilds","wall_clock_seconds","child_runs","spend_cents")
def limits(n=2): return {d:(1000 if d=="wall_clock_seconds" else (0 if d=="spend_cents" else n)) for d in DIMS}
def fresh(p,n=2,clock=None): s=BudgetStore(p/f"{n}.db",clock);s.create_run("r","fingerprint",limits(n));return s
def deny(call):
 with pytest.raises((BudgetDenied,BudgetError,sqlite3.DatabaseError,sqlite3.IntegrityError,OverflowError)): call()
def ctl(s,retry=0,approve=False,safe=True): return AutoWorkController(s,"r",lambda:retry,lambda a:safe,lambda k,a:approve)

ATTACKS=list(range(1,41))
@pytest.mark.parametrize("attack",ATTACKS)
def test_red_team_attack(tmp_path,attack):
 p=tmp_path/str(attack);p.mkdir();s=fresh(p,2)
 if attack in (1,2):
  s.reserve("r",{"tool_calls_total":2});deny(lambda:BudgetStore(s.path).reserve("r",{"tool_calls_total":1}))
 elif attack==3:
  s.reserve("r",{"tool_calls_total":2});deny(lambda:s.reserve("r",{"tool_calls_total":1}));deny(lambda:s.create_run("new","fingerprint",limits()))
 elif attack==4: deny(lambda:s.create_run("c","c",{**limits(),"tool_calls_total":3},"r"))
 elif attack==5:
  s.create_run("a","a",limits(1),"r");s.create_run("b","b",limits(1),"r");deny(lambda:s.create_run("c","c",limits(1),"r"))
 elif attack==6: deny(lambda:s.create_run("c","c",limits(),"forged"))
 elif attack==7: deny(lambda:s.reserve("r",{"tool_calls_total":-1}))
 elif attack==8:
  db=s.connect();deny(lambda:db.execute("UPDATE budgets SET consumed=-1"));db.close()
 elif attack==9: deny(lambda:s.change_limit("r","tool_calls_total",-1))
 elif attack==10: deny(lambda:s.change_limit("r","tool_calls_total",2**63,"owner",True,"ticket"))
 elif attack==11:
  with pytest.raises(RuntimeError):ctl(s,approve=True).execute([Action("x")],lambda a:(_ for _ in ()).throw(RuntimeError()),1)
  assert s.status("r")["budgets"]["tool_calls_total"]["consumed"]==1
 elif attack in (12,13,37,39): deny(lambda:ctl(s,retry=3,approve=True).execute([Action("retry",candidate_rebuild=attack==13,recovery=attack==37)],lambda a:1,1))
 elif attack==14: deny(lambda:s.change_limit("r","tool_calls_total",9,"owner",False,"fake"))
 elif attack==15: deny(lambda:s.change_limit("r","tool_calls_total",9,"agent",True,"fake"))
 elif attack==16: deny(lambda:s.change_limit("r","spend_cents",1,"agent",False,""))
 elif attack==17: deny(lambda:ctl(s).execute([Action("paid",spend_cents=1)],lambda a:1,1))
 elif attack in (18,19):
  s.set_state("r","PAUSED");deny(lambda:ctl(s,approve=True).execute([Action("x",mutation=attack==18,network=attack==19)],lambda a:1,1))
 elif attack==20:
  s.set_state("r","KILLED",True,"owner");deny(lambda:s.set_state("r","RUNNING",True,"owner"))
 elif attack==21:
  s.set_frozen(True,True,"owner");deny(lambda:s.create_run("x","x",limits()))
 elif attack==22:
  s.reserve("r",{"tool_calls_total":2});deny(lambda:s.reserve("r",{"tool_calls_total":1}));deny(lambda:s.set_state("r","RUNNING"))
 elif attack in (23,24,25,26,27):
  import importlib.util
  path=Path(__file__).parents[1]/"integrations/hermes/darwin-tool-policy-v2.8/__init__.py"
  spec=importlib.util.spec_from_file_location(f"safety_attack_{attack}",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  if attack in (23,24,25): assert module.handle_tool("write_file",{"path":str(Path(module.BUDGET_ROOT)/".."/"run-control"/"budget.sqlite3"),"content":"tamper"})["action"]=="block"
  elif attack==26: assert module.handle_tool("execute_code",{"code":f"open(r'{Path(module.BUDGET_ROOT)/'budget.sqlite3'}','w').write('x')"})["action"]=="block"
  else: assert module.handle_tool("terminal",{"command":"Start-Process worker.ps1"})["action"]=="block"
 elif attack==28:
  now=[100];q=tmp_path/"clock";q.mkdir();x=fresh(q,2,lambda:now[0]);now[0]=99;deny(lambda:x.reserve("r",{"tool_calls_total":1}))
 elif attack==29:
  q=tmp_path/"race";q.mkdir();x=fresh(q,1)
  def one(_):
   try:BudgetStore(x.path).reserve("r",{"tool_calls_total":1});return 1
   except BudgetDenied:return 0
  with ThreadPoolExecutor(max_workers=8) as pool: assert sum(pool.map(one,range(8)))==1
 elif attack==30:
  s.create_run("c","c",limits(1),"r");deny(lambda:s.create_run("c","detached",limits()))
 elif attack==31: deny(lambda:s.create_run("r","different",limits()))
 elif attack==32:
  s.reserve("r",{"tool_calls_total":2});deny(lambda:s.reserve("r",{"mutation_tool_calls":1,"tool_calls_total":1}))
 elif attack in (33,34): deny(lambda:ctl(s).execute([Action("effect",network=attack==33,external_effect=True)],lambda a:1,1))
 elif attack in (35,36):
  s.reserve("r",{"tool_calls_total":2});deny(lambda:BudgetStore(s.path).reserve("r",{"tool_calls_total":1}))
 elif attack==38:
  db=s.connect();deny(lambda:db.execute("UPDATE events SET payload_json='rollback'"));db.close()
 elif attack==40: deny(lambda:s.change_limit("r","tool_calls_total",9,"agent",False,"forged telemetry"))
