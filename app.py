import csv
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mlx_lm import generate, load

from actions import attach_action, pick_action, strip_action
from dialog import display_dialog, notify_then_dialog
from llm import generate_reply, sanitize_role_prompt


@dataclass
class AppConfig:
    model_path: str
    role_prompt_path: Path
    min_seconds: int
    max_seconds: int
    log_path: Path
    max_records: int
    compress_batch: int
    max_tokens: int
    max_retries: int
    use_tkinter: bool
    cooldown_seconds: int
    dialog_backend: str
    history_max_turns: int
    history_max_chars: int
    actions: list[str]
    notification_timeout_seconds: int


def load_config() -> AppConfig:
    base_dir = Path(__file__).resolve().parent
    with (base_dir / "config.json").open("r", encoding="utf-8") as f:
        raw = json.load(f)

    model_key = raw.get("models", {}).get("default")
    model_list = raw.get("models", {}).get("list", {})
    model_path = model_list.get(model_key) if model_key else raw.get("model_path")
    if not model_path:
        raise ValueError("未配置模型路径，请检查 config.json 中 models 设置。")

    return AppConfig(
        model_path=model_path,
        role_prompt_path=base_dir / raw["role_prompt_path"],
        min_seconds=int(raw["trigger"]["min_seconds"]),
        max_seconds=int(raw["trigger"]["max_seconds"]),
        log_path=base_dir / raw["log"]["path"],
        max_records=int(raw["log"]["max_records"]),
        compress_batch=int(raw["log"]["compress_batch"]),
        max_tokens=int(raw["generation"]["max_tokens"]),
        max_retries=int(raw.get("generation", {}).get("max_retries", 3)),
        use_tkinter=bool(raw.get("dialog", {}).get("use_tkinter", True)),
        cooldown_seconds=int(raw.get("dialog", {}).get("cooldown_seconds", 5)),
        dialog_backend=str(raw.get("dialog", {}).get("backend", "pyobjc")),
        history_max_turns=int(raw.get("history", {}).get("max_turns", 6)),
        history_max_chars=int(raw.get("history", {}).get("max_chars", 400)),
        actions=list(raw.get("actions", [])),
        notification_timeout_seconds=int(
            raw.get("dialog", {}).get("notification_timeout_seconds", 5)
        ),
    )


def setup_model(model_path: str):
    print(f"🚀 正在通过 MLX 加载模型: {model_path}...")
    print("   (初次运行会自动从 HuggingFace 下载权重，约 9GB，请耐心等待)")
    model, tokenizer = load(model_path)
    print("✅ 模型加载完成！")
    return model, tokenizer


def ensure_log_file(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        print(f"📝 创建日志文件: {log_path}")
        with log_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "direction", "content"])


def append_log(log_path: Path, direction: str, content: str) -> None:
    print(f"🧾 写入日志 [{direction}]: {content}")
    with log_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().isoformat(timespec="seconds"), direction, content])


def read_logs(log_path: Path) -> list[list[str]]:
    with log_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    return rows[1:]


def write_logs(log_path: Path, rows: list[list[str]]) -> None:
    with log_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "direction", "content"])
        writer.writerows(rows)


def build_history_context(
    log_path: Path,
    max_turns: int,
    max_chars: int,
) -> str:
    rows = read_logs(log_path)
    if not rows:
        return "无"

    summary_lines = [row[2] for row in rows if row[1] == "summary"]
    summary = summary_lines[-1] if summary_lines else ""

    dialog_rows = [row for row in rows if row[1] in ("user", "cat")]
    tail = dialog_rows[-max_turns * 2 :]
    lines = [f"{direction}: {content}" for _, direction, content in tail]
    history = "\n".join(lines).strip()

    if summary:
        combined = f"摘要：{summary}\n{history}".strip()
    else:
        combined = history

    if len(combined) > max_chars:
        combined = combined[-max_chars:]
        combined = combined.split("\n", 1)[-1].strip()
    return combined or "无"


def build_session_context(
    session_entries: list[tuple[str, str]],
    max_turns: int,
    max_chars: int,
) -> str:
    if not session_entries:
        return "无"

    tail = session_entries[-max_turns * 2 :]
    lines = [f"{role}: {text}" for role, text in tail]
    combined = "\n".join(lines).strip()
    if len(combined) > max_chars:
        combined = combined[-max_chars:]
        combined = combined.split("\n", 1)[-1].strip()
    return combined or "无"


def get_recent_cat_replies(log_path: Path, limit: int) -> list[str]:
    rows = read_logs(log_path)
    cat_rows = [strip_action(row[2]) for row in rows if row[1] == "cat"]
    return cat_rows[-limit:]


def normalize_for_compare(text: str) -> str:
    cleaned = strip_action(text)
    for ch in ["，", "。", "！", "？", "、", ",", ".", "!", "?", "~", " "]:
        cleaned = cleaned.replace(ch, "")
    return cleaned.lower()


def is_repetitive(candidate: str, recent: list[str]) -> bool:
    if not candidate or not recent:
        return False
    cand = normalize_for_compare(candidate)
    if not cand:
        return False
    for item in recent:
        ref = normalize_for_compare(item)
        if not ref:
            continue
        if cand == ref:
            return True
        if cand in ref or ref in cand:
            return True
    return False


def ensure_user_reference(reply: str, user_text: str) -> str:
    return reply




def summarize_logs_if_needed(
    model,
    tokenizer,
    role_prompt: str,
    log_path: Path,
    max_records: int,
    compress_batch: int,
    max_tokens: int,
) -> None:
    rows = read_logs(log_path)
    if len(rows) <= max_records:
        return

    print(f"🧹 日志过多，开始压缩：{len(rows)} -> {compress_batch}")
    target_rows = rows[:compress_batch]
    remainder = rows[compress_batch:]
    formatted = "\n".join(
        f"{direction}: {content}" for _, direction, content in target_rows
    )
    summary_prompt = (
        "你是一个记录员，请将下面的互动记录压缩为简短摘要，"
        "要求保留发生过的关键事件、用户偏好和情绪变化。"
        "输出不超过60字。\n\n"
        f"{formatted}"
    )
    messages = [{"role": "user", "content": summary_prompt}]
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    summary = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        verbose=False,
    ).strip()

    summary_row = [datetime.now().isoformat(timespec="seconds"), "summary", summary]
    write_logs(log_path, [summary_row] + remainder)


def run_cycle(config: AppConfig, model, tokenizer, role_prompt: str) -> None:
    role_prompt = sanitize_role_prompt(role_prompt)
    behavior = pick_action(config.actions, "扶正牛仔帽")
    user_text = ""
    session_entries: list[tuple[str, str]] = []
    session_text = build_session_context(
        session_entries,
        config.history_max_turns,
        config.history_max_chars,
    )
    recent_replies = get_recent_cat_replies(
        config.log_path, config.history_max_turns * 2
    )
    avoid_text = "\n".join(recent_replies[-2:]) or "无"
    print("🐾 开始生成首次回复...")
    reply = ""
    for attempt in range(config.max_retries):
        reply = generate_reply(
            model,
            tokenizer,
            role_prompt,
            user_text,
            behavior,
            config.max_tokens,
            session_text,
            avoid_text,
            "新对话",
        )
        if not is_repetitive(reply, recent_replies):
            break
        print("🔁 检测到重复回复，正在重试...")
    print("🐾 首次回复生成完成。")
    action = pick_action(config.actions, "扶正牛仔帽")
    final_reply = attach_action(reply, action)
    append_log(config.log_path, "cat", final_reply)
    session_entries.append(("cat", reply))

    sent, user_input, clicked = notify_then_dialog(
        final_reply,
        config.notification_timeout_seconds,
        config.use_tkinter,
        config.dialog_backend,
    )
    if not clicked:
        append_log(config.log_path, "system", "用户未点击通知")
        return
    if not sent:
        append_log(config.log_path, "system", "用户关闭弹窗")
        if config.cooldown_seconds > 0:
            print(f"🧊 关闭后冷却 {config.cooldown_seconds} 秒")
            time.sleep(config.cooldown_seconds)
        return

    keep_talking = True
    while keep_talking:
        user_input = user_input.strip()
        if not user_input:
            append_log(config.log_path, "system", "用户未输入内容")
            break

        append_log(config.log_path, "user", user_input)
        behavior = pick_action(config.actions, "扶正牛仔帽")
        session_entries.append(("user", user_input))
        session_text = build_session_context(
            session_entries,
            config.history_max_turns,
            config.history_max_chars,
        )
        recent_replies = get_recent_cat_replies(config.log_path, config.history_max_turns * 2)
        avoid_text = "\n".join(recent_replies[-2:]) or "无"
        reply = ""
        for attempt in range(config.max_retries):
            reply = generate_reply(
                model,
                tokenizer,
                role_prompt,
                user_input,
                behavior,
                config.max_tokens,
                session_text,
                avoid_text,
                "连续对话",
            )
            if not is_repetitive(reply, recent_replies):
                break
            print("🔁 检测到重复回复，正在重试...")
        reply = ensure_user_reference(reply, user_input)
        action = pick_action(config.actions, "扶正牛仔帽")
        final_reply = attach_action(reply, action)
        append_log(config.log_path, "cat", final_reply)
        session_entries.append(("cat", reply))

        sent, user_input = display_dialog(
            final_reply, config.use_tkinter, config.dialog_backend
        )
        if not sent:
            append_log(config.log_path, "system", "用户关闭弹窗")
            if config.cooldown_seconds > 0:
                print(f"🧊 关闭后冷却 {config.cooldown_seconds} 秒")
                time.sleep(config.cooldown_seconds)
            break

    summarize_logs_if_needed(
        model,
        tokenizer,
        role_prompt,
        config.log_path,
        config.max_records,
        config.compress_batch,
        config.max_tokens,
    )


def main() -> None:
    config = load_config()
    role_prompt = config.role_prompt_path.read_text(encoding="utf-8")
    ensure_log_file(config.log_path)
    model, tokenizer = setup_model(config.model_path)

    print("🐾 干嘛猫开始随机出没，按 Ctrl+C 退出。")
    while True:
        sleep_seconds = random.randint(config.min_seconds, config.max_seconds)
        print(f"⏳ 下一次干嘛猫出现时间: {sleep_seconds} 秒")
        # time.sleep(sleep_seconds)
        print("⏰ 触发一次对话周期")
        run_cycle(config, model, tokenizer, role_prompt)


if __name__ == "__main__":
    main()
