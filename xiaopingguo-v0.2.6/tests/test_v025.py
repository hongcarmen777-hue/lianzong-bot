from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_ai_capability_prompt_private_ingest():
    text = (ROOT / "xiaopingguo" / "ai.py").read_text(encoding="utf-8")
    assert "骰主通过与小苹果的私聊录入/覆盖" in text
    assert "落库必须回主群" in text
    assert "聊天历史里提到过某个本，不等于它已经入库" in text

def test_new_history_namespace():
    text = (ROOT / "xiaopingguo" / "commands.py").read_text(encoding="utf-8")
    assert "c2c:v025:" in text
    assert "group:v025:" in text
    assert "可以直接在这个私聊里落库" in text
