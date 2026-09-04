import pytest
from owner_ops import (
    AlertDeduplicator, ControlDispatcher, DiscordPanelController, EventCoalescer,
    FakeDiscordTransport, LocalAPI, NonceStore, OwnerAuthenticator, OwnerEvent,
    OwnerOpsReadModel, build_local_server, render_panel,
)

def model(clock=lambda:100):
    return OwnerOpsReadModel({
        "system":lambda:{"state":"RUNNING","safety_version":"3.0.0"},
        "task":lambda:{"name":"CP09.5","progress":"50%"},
        "control":lambda:{"state":"RUNNING","approvals_mode":"manual"},
        "budget":lambda:{"spend":"$0","status":"OK"},
        "model":lambda:{"model":"local","router":"OK"},
        "recovery":lambda:{"status":"OK"},"context":lambda:{"status":"OK"},
        "git":lambda:{"commit":"abc","ci":"PASS"},"security":lambda:{"last_alert":"none"},
    },clock=clock)

def test_render_blocks_mentions_and_fences():
    text=render_panel(OwnerOpsReadModel({"task":lambda:{"name":"@everyone ```x```"}}).snapshot())
    assert "@everyone" not in text and "```" not in text

def test_1000_events_one_edit():
    now=[100];c=EventCoalescer(clock=lambda:now[0],max_queue=32);t=FakeDiscordTransport()
    p=DiscordPanelController(model(lambda:now[0]),t,"c","m",c)
    for i in range(1000): p.on_event(OwnerEvent(str(i),"TASK",{"i":i},100))
    assert c.queued==1 and p.tick() and len(t.edits)==1

def test_no_one_second_poll():
    now=[100];c=EventCoalescer(clock=lambda:now[0])
    c.push(OwnerEvent("1","TASK",{},100)); assert c.drain()
    now[0]=101;c.push(OwnerEvent("2","TASK",{},101)); assert not c.ready()

def test_alert_dedup():
    d=AlertDeduplicator(clock=lambda:100)
    assert d.allow(OwnerEvent("1","ALERT",{"x":1},100,"WARNING"))
    assert not d.allow(OwnerEvent("2","ALERT",{"x":1},100,"WARNING"))

def test_rate_limit_backoff_does_not_busy_loop():
    class Broken:
        calls=0
        def edit_panel(self,*_):
            self.calls += 1
            raise RuntimeError("rate limited")
    now=[100]; c=EventCoalescer(clock=lambda:now[0]); c.push(OwnerEvent("1","TASK",{},100))
    t=Broken(); p=DiscordPanelController(model(lambda:now[0]),t,"c","m",c,clock=lambda:now[0])
    assert p.tick() is False and t.calls==1
    now[0]=101
    assert p.tick() is False and t.calls==1

def test_localhost_only(tmp_path):
    api=LocalAPI(model(),ControlDispatcher({}))
    with pytest.raises(ValueError): build_local_server(api,host="0.0.0.0")
    s=build_local_server(api,port=0); assert s.server_address[0]=="127.0.0.1"; s.server_close()
    with pytest.raises(PermissionError):
        api.control(dict(action="PAUSE",request_id="r",owner_user_id="owner",guild_id="g",channel_id="c",nonce="n",expires_at=200,target_id="run",payload={}))
