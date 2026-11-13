"""把最近的聊天记录交给 Claude，拿回一句回复。"""

import anthropic

import config

# 密钥从环境变量 ANTHROPIC_API_KEY 读取，不要写进代码里。
client = anthropic.Anthropic()

SYSTEM_PROMPT = config.PERSONA.replace("{owner}", config.OWNER_NAME)


def make_reply(history):
    """history 是按时间排好的 [(who, text), ...]，who 为 "friend"（对方）或 "me"（自己）。

    返回要发出去的回复文字；不该回复时返回 None。
    """
    messages = []
    for who, text in history:
        role = "user" if who == "friend" else "assistant"
        if not messages and role == "assistant":
            continue  # 发给 Claude 的对话必须从对方的消息开始
        messages.append({"role": role, "content": text})

    if not messages or messages[-1]["role"] != "user":
        return None

    response = client.beta.messages.create(
        model=config.MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=messages,
        output_config={"effort": "low"},
        # 万一模型因为安全原因拒绝回答，自动换一个模型再试一次
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    if response.stop_reason == "refusal":
        return None
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    return text or None
