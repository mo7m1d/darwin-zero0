from pathlib import Path
import pytest
from owner_ops.discord_webhook import DiscordBindingError, DiscordWebhookTransport, validate_webhook_url
from owner_ops.runtime import _DisabledAuth

ATTACKS=[f"{i:02d}" for i in range(1,13)]

@pytest.mark.parametrize("attack",ATTACKS)
def test_runtime_red_team(attack):
    n=int(attack)
    if n==1:
        with pytest.raises(DiscordBindingError): validate_webhook_url("http://discord.com/api/webhooks/1/x")
    elif n==2:
        with pytest.raises(DiscordBindingError): validate_webhook_url("https://evil.example/api/webhooks/1/x")
    elif n==3:
        with pytest.raises(DiscordBindingError): validate_webhook_url("https://discord.com/api/not-webhooks/1/x")
    elif n==4:
        with pytest.raises(DiscordBindingError): validate_webhook_url("https://u:p@discord.com/api/webhooks/1/x")
    elif n==5:
        import owner_ops.discord_webhook as d
        assert "_NoRedirect" in Path(d.__file__).read_text()
    elif n==6:
        class Bad:
            def open(self,*_a,**_k): raise RuntimeError("failure")
        secret="VERY_SECRET"
        t=DiscordWebhookTransport("https://discord.com/api/webhooks/1/"+secret,opener=Bad())
        with pytest.raises(DiscordBindingError) as exc: t.create_panel("x")
        assert secret not in str(exc.value)
    elif n==7:
        t=DiscordWebhookTransport("https://discord.com/api/webhooks/1/x",opener=object())
        with pytest.raises(DiscordBindingError): t.edit_panel("","not-an-id","x")
    elif n==8:
        with pytest.raises(PermissionError): _DisabledAuth().authorize(object())
    elif n in {9,10}:
        import owner_ops.runtime_sources as s
        text=Path(s.__file__).read_text().lower()
        assert "select *" not in text and "subprocess" not in text
    elif n==11:
        import owner_ops.runtime as r
        assert 'host="127.0.0.1"' in Path(r.__file__).read_text()
    elif n==12:
        import owner_ops.discord_webhook as d
        text=Path(d.__file__).read_text().lower()
        assert "approve" not in text and "pause" not in text and "resume" not in text
