import sqlite3
import pytest
from owner_ops import AuthError, ControlDispatcher, ControlRequest, NonceStore, OwnerAuthenticator

def req(**u):
    v=dict(action="PAUSE",request_id="r1",owner_user_id="owner",guild_id="guild",
           channel_id="chan",nonce="n1",expires_at=160,target_id="run",payload={})
    v.update(u); return ControlRequest(**v)

def guard(tmp_path):
    s=NonceStore(tmp_path/"nonce.db",clock=lambda:100)
    return OwnerAuthenticator("owner","guild",{"chan"},s),s

def test_owner_guild_channel_and_replay(tmp_path):
    g,_=guard(tmp_path); g.authorize(req())
    with pytest.raises(AuthError): g.authorize(req(request_id="r2"))

@pytest.mark.parametrize("change",[
    {"owner_user_id":"attacker"},{"guild_id":"bad"},{"channel_id":"bad"}
])
def test_identity_mismatch_denied(tmp_path,change):
    g,_=guard(tmp_path)
    with pytest.raises(AuthError): g.authorize(req(**change))

def test_expiry_denied(tmp_path):
    g,_=guard(tmp_path)
    with pytest.raises(AuthError): g.authorize(req(expires_at=99))

def test_nonce_append_only(tmp_path):
    g,s=guard(tmp_path);g.authorize(req())
    with sqlite3.connect(s.path) as db:
        with pytest.raises(sqlite3.DatabaseError): db.execute("DELETE FROM used_nonce")

def test_dispatcher_narrow_callback():
    seen=[]
    d=ControlDispatcher({"PAUSE":lambda r:seen.append(r.target_id) or {"ok":True}})
    out=d.dispatch(req()); assert seen==["run"] and out["status"]=="ACCEPTED_BY_CONTROL_PATH"

def test_arbitrary_shell_rejected():
    with pytest.raises(Exception): req(action="SHELL").validate()
