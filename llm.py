from mlx_lm import generate

from actions import strip_action


def sanitize_role_prompt(role_prompt: str) -> str:
    if "scenarios = [" not in role_prompt:
        return role_prompt
    lines = role_prompt.splitlines()
    cleaned_lines: list[str] = []
    skip = False
    for line in lines:
        if line.strip().startswith("scenarios = ["):
            skip = True
            cleaned_lines.append("动作示例：从场景中任选一句进行括号描写。")
            continue
        if skip and line.strip().startswith("]"):
            skip = False
            continue
        if not skip:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def build_chat_prompt(
    tokenizer,
    role_prompt: str,
    user_text: str,
    behavior: str,
    history_text: str,
    avoid_text: str,
    stage: str,
) -> str:
    shown_user_text = user_text.strip() or "无"
    prompt_content = (
        f"{role_prompt}\n\n"
        "你现在要进行一次弹窗互动回应。\n"
        f"对话阶段：{stage}\n"
        f"当前行为：{behavior}\n"
        f"用户输入：{shown_user_text}\n\n"
        f"最近对话（供参考，避免重复）：\n{history_text}\n\n"
        f"不要复用以下句子或近似表达：\n{avoid_text}\n\n"
        "要求：\n"
        "1) 只输出一句话，不要加角色名、不要加前缀。\n"
        "2) 必须使用小猫视角，包含“干嘛”或“干嘛？”。\n"
        "3) 输出不超过50字，短句口语化。\n"
        "5) 必须回应用户输入，语气要贴合对话。\n"
        "6) 若是连续对话，必须明确回应用户的话，最好复述用户输入中的关键词。\n"
        "7) 不要讲道理，不要专业分析。\n\n"
        "示例（仅作格式参考，禁止照抄）：\n"
        "干嘛呀……本喵抱着冰红茶发呆喵~\n"
        "干嘛叫我，我又穷又笨嘛~\n\n"
        "请输出一句话作为弹窗内容。"
    )
    messages = [{"role": "user", "content": prompt_content}]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )


def generate_reply(
    model,
    tokenizer,
    role_prompt: str,
    user_text: str,
    behavior: str,
    max_tokens: int,
    history_text: str,
    avoid_text: str,
    stage: str,
) -> str:
    prompt = build_chat_prompt(
        tokenizer,
        role_prompt,
        user_text,
        behavior,
        history_text,
        avoid_text,
        stage,
    )
    print("🧠 提示词输入:\n", prompt)
    response = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        verbose=False,
    )
    return clean_reply(response)


def clean_reply(text: str) -> str:
    cleaned = text.strip()
    for token in ("<|im_end|>", "<|im_start|>", "<|endoftext|>"):
        cleaned = cleaned.replace(token, "")
    for prefix in ("cat,", "cat:", "猫,", "猫:", "干嘛猫:", "干嘛猫,"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    cleaned = cleaned.replace("`(", "(").replace(")`", ")")
    cleaned = strip_action(cleaned).strip(" \n\r\t\"'")
    if "干嘛" not in cleaned:
        cleaned = f"干嘛呀……{cleaned}"
    if len(cleaned) > 50:
        cleaned = cleaned[:50]
    return cleaned
