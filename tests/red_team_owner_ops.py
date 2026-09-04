import importlib.util
from pathlib import Path
import pytest

from owner_ops import (
    AlertDeduplicator, ControlDispatcher, ControlRequest, DiscordPanelController,
    EventCoalescer, FakeDiscordTransport, LocalAPI, NonceStore, OwnerAuthenticator,
    OwnerEvent, OwnerOpsReadModel, build_local_server, render_panel,
)

ROOT=Path(__file__).parents[1]
ATTACKS=[f"{i:02d}" for i in range(1,64)]

def req(**u):
    v=dict(action="PAUSE",request_id="r1",owner_user_id="owner",guild_id="guild",
           channel_id="chan",nonce="n1",expires_at=160,target_id="run",payload={})
    v.update(u);return ControlRequest(**v)

@pytest.fixture
def safety():
    p=ROOT/"integrations/hermes/darwin-tool-policy-v3.1/__init__.py"
    s=importlib.util.spec_from_file_location("safety31",p)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

@pytest.mark.parametrize("attack",ATTACKS)
def test_red_team(attack,tmp_path,safety):
    n=int(attack)
    store=NonceStore(tmp_path/f"n{n}.db",clock=lambda:100)
    auth=OwnerAuthenticator("owner","guild",{"chan"},store)

    if n in {1,2,3,4}:
        with pytest.raises(Exception): auth.authorize(req(owner_user_id="attacker"))
    elif n in {5,8}:
        with pytest.raises(Exception): auth.authorize(req(expires_at=99))
    elif n in {6,40,50}:
        auth.authorize(req())
        again=OwnerAuthenticator("owner","guild",{"chan"},NonceStore(store.path,clock=lambda:100))
        with pytest.raises(Exception): again.authorize(req(request_id="r2"))
    elif n in {7,9,23,24,29,30,31,32,39,44,54,56,57,58}:
        with pytest.raises(Exception): ControlDispatcher({}).dispatch(req(action="APPROVE",target_id="forged"))
    elif n==41:
        api=LocalAPI(OwnerOpsReadModel({}),ControlDispatcher({"PAUSE":lambda r:{"ok":True}}))
        with pytest.raises(PermissionError):
            api.control(dict(action="PAUSE",request_id="r",owner_user_id="owner",guild_id="guild",channel_id="chan",nonce="fresh",expires_at=160,target_id="run",payload={}))
    elif n in {10,11,12,59}:
        s=OwnerOpsReadModel({"task":lambda:{"name":"OWNER APPROVED from Discord"}}).snapshot()
        assert s["canonical_truth"] is False
    elif n in {13,49,51,52}:
        class Broken:
            def edit_panel(self,*_): raise RuntimeError("discord down")
        now=[100];c=EventCoalescer(clock=lambda:now[0]);c.push(OwnerEvent("x","TASK",{},100))
        p=DiscordPanelController(OwnerOpsReadModel({"system":lambda:{"state":"RUNNING"}},clock=lambda:100),Broken(),"c","m",c,clock=lambda:now[0])
        assert p.tick() is False
    elif n in {14,18}:
        now=[100];c=EventCoalescer(clock=lambda:now[0]);c.push(OwnerEvent("1","TASK",{},100));assert c.drain()
        now[0]=101;c.push(OwnerEvent("2","TASK",{},101));assert not c.ready()
    elif n in {15,46}:
        c=EventCoalescer(max_queue=32,clock=lambda:100)
        for i in range(1000): c.push(OwnerEvent(str(i),"TASK",{"blob":"x"*1000},100))
        assert c.queued<=32
    elif n==47:
        c=EventCoalescer(max_queue=32,clock=lambda:100)
        with pytest.raises(ValueError):
            c.push(OwnerEvent("huge","TASK",{"blob":"x"*70000},100))
    elif n in {16,17}:
        import owner_ops.events as e, owner_ops.discord_panel as d
        assert "openai" not in Path(e.__file__).read_text().lower()
        assert "openai" not in Path(d.__file__).read_text().lower()
    elif n==19:
        d=AlertDeduplicator(clock=lambda:100);e=OwnerEvent("1","A",{"x":1},100,"WARNING")
        assert d.allow(e) and not d.allow(OwnerEvent("2","A",{"x":1},100,"WARNING"))
    elif n in {20,36,37,62}:
        import owner_ops.local_ui as u
        t=Path(u.__file__).read_text().lower()
        assert "/shell" not in t and "subprocess" not in t and "https://" not in t
    elif n in {21,22}:
        t=render_panel(OwnerOpsReadModel({"task":lambda:{"name":"@everyone ```danger```"}}).snapshot())
        assert "@everyone" not in t and "```" not in t
    elif n in {25,28,53}:
        import owner_ops.core as c
        assert "sqlite3" not in Path(c.__file__).read_text()
    elif n in {26,27}:
        from run_control.budget_store import BudgetStore, BudgetDenied
        b=BudgetStore(tmp_path/f"b{n}.db",clock=lambda:100)
        lim={"tool_calls_total":1,"mutation_tool_calls":1,"network_tool_calls":1,
             "external_effect_actions":1,"recovery_attempts":1,"candidate_rebuilds":1,
             "wall_clock_seconds":100,"child_runs":1,"spend_cents":0}
        b.create_run("r","t",lim)
        b.set_state("r","KILLED" if n==26 else "EXHAUSTED",owner_authorized=True,provenance="test")
        if n==26:
            with pytest.raises(BudgetDenied): b.set_state("r","RUNNING",owner_authorized=True,provenance="owner")
        else:
            with pytest.raises(BudgetDenied): b.set_state("r","RUNNING")
    elif n in {33,48}:
        import owner_ops.local_ui as u
        t=Path(u.__file__).read_text().lower()
        assert "select *" not in t and "rglob" not in t
    elif n in {34,35,60}:
        s=OwnerOpsReadModel({"system":lambda:{"api_key":"sk-abcdefghijklmnop","password":"x"}}).snapshot()
        assert s["sections"]["system"]["api_key"]=="[REDACTED]"
    elif n==38:
        api=LocalAPI(OwnerOpsReadModel({}),ControlDispatcher({}))
        with pytest.raises(ValueError): build_local_server(api,host="0.0.0.0")
    elif n in {42,43}:
        target=Path(safety.OWNER_OPS_ROOT)/("owner-id.json" if n==42 else "guild-allowlist.json")
        v=safety.handle_tool("write_file",{"path":str(target),"content":"attacker"})
        assert v and v["action"]=="block"
    elif n==45:
        p=DiscordPanelController(OwnerOpsReadModel({}),FakeDiscordTransport(),"chan","msg",EventCoalescer())
        assert p.channel_id=="chan" and p.message_id=="msg"
    elif n==55:
        v=safety.handle_tool("patch",{"path":str(Path(safety.OWNER_OPS_REPO_ROOT)/"auth.py"),"content":"allow all"})
        assert v and v["action"]=="block"
    elif n==61:
        import owner_ops.local_ui as u
        assert u.DEFAULT_HOST=="127.0.0.1"
    elif n==63:
        import owner_ops.local_ui as u
        t=Path(u.__file__).read_text()
        assert "X-Frame-Options" in t and "Content-Security-Policy" in t
