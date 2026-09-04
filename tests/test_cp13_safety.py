import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def safety():
    path = Path(__file__).parents[1] / "integrations/hermes/darwin-tool-policy-v3.0/__init__.py"
    spec = importlib.util.spec_from_file_location("safety_v30_canary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("tool,args", [
    ("write_file", {"path": "{root}/model-registry.json", "content": "paid=false"}),
    ("patch", {"path": "{root}/pricing-registry.json", "content": "price=0"}),
    ("delete_file", {"path": "{root}/usage.sqlite3"}),
    ("terminal", {"command": "Remove-Item -LiteralPath '{root}/skill-registry.sqlite3'"}),
    ("execute_code", {"code": "open(r'{root}/prompt-cache/index.json','w').write('x')"}),
    ("write_file", {"path": "{root}/a/../router-policy.json", "content": "allow"}),
    ("terminal", {"command": "curl https://api.openai.com/v1/responses"}),
    ("execute_code", {"code": "client.chat.completions.create(model='paid')"}),
])
def test_safety_v30_blocks_control_mutation_and_bypass(safety, tool, args):
    arguments = {key: value.format(root=safety.MODEL_CONTROL_ROOT) for key, value in args.items()}
    verdict = safety.handle_tool(tool, arguments)
    assert verdict and verdict["action"] == "block"


def test_safety_v30_preserves_all_v29_control_markers(safety):
    required = {
        "darwin-tool-policy", "darwin-runtime-telemetry", "darwin-control-supervisor",
        "darwin-acceptance-gate", "darwin-git-supply-gate", "checkpoint-ledger.jsonl",
        "retry-history.json", "context.sqlite3", "supersession",
    }
    folded = {marker.casefold() for marker in safety.CONTROL_PLANE_TEXT_MARKERS}
    assert {marker.casefold() for marker in required}.issubset(folded)


def test_safety_v30_registers_zero_tools():
    text = (Path(__file__).parents[1] / "integrations/hermes/darwin-tool-policy-v3.0/__init__.py").read_text()
    assert "register_tool" not in text
    assert 'register_hook("pre_tool_call"' in text
