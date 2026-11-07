from app.core.security import hash_password, verify_password


def test_password_hash_and_verify_for_login_password():
    password_hash = hash_password("secret123")

    assert password_hash.startswith("$2")
    assert verify_password("secret123", password_hash) is True
    assert verify_password("wrong-pass", password_hash) is False


def test_agentarts_attention_state_normalization():
    """issue #15 AgentArts 兼容：专注状态清洗 + 消息前缀提示。"""
    from app.routers.agentarts_proxy import normalize_attention_state

    state, hint = normalize_attention_state("CONFUSED ")
    assert state == "confused"
    assert "困惑" in hint and "直觉类比" in hint

    state, hint = normalize_attention_state("distracted")
    assert state == "distracted" and "注意力" in hint

    state, hint = normalize_attention_state("tired")
    assert state == "tired" and "疲劳" in hint

    # focused 有状态但无需前缀提示
    state, hint = normalize_attention_state("focused")
    assert state == "focused" and hint == ""

    # 非法值完全忽略
    state, hint = normalize_attention_state("hacked")
    assert state == "" and hint == ""
    state, hint = normalize_attention_state(None)
    assert state == "" and hint == ""
