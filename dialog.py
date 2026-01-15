import importlib
import subprocess
import time


def display_dialog(message: str, use_tkinter: bool = True, backend: str = "pyobjc") -> tuple[bool, str]:
    if backend == "pyobjc":
        result = display_dialog_cocoa(message)
        if result is not None:
            return result

    if use_tkinter:
        result = display_dialog_tk(message)
        if result is not None:
            return result
    return display_dialog_osascript(message)


def notify_then_dialog(
    message: str,
    timeout_seconds: int,
    use_tkinter: bool = True,
    backend: str = "pyobjc",
) -> tuple[bool, str, bool]:
    clicked = display_notification_tk(message, timeout_seconds)
    if clicked is None:
        display_notification_osascript(message)
        time.sleep(timeout_seconds)
        return False, "", False

    if not clicked:
        return False, "", False

    sent, text = display_dialog(message, use_tkinter, backend)
    return sent, text, True


def display_dialog_osascript(message: str) -> tuple[bool, str]:
    safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
    applescript = (
        f'set msg to "{safe_message}"\n'
        "try\n"
        'display dialog msg with title "干嘛猫" '
        'default answer "" buttons {"关闭", "发送"} '
        'default button "发送" cancel button "关闭"\n'
        "on error number -128\n"
        'return "button returned:关闭, text returned:"\n'
        "end try"
    )
    try:
        print("🪟 正在唤起弹窗...")
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print("⚠️ 弹窗调用失败（osascript 返回非 0）。")
        print("applescript:", applescript)
        print("stdout:", (exc.stdout or "").strip())
        print("stderr:", (exc.stderr or "").strip())
        return False, ""

    output = result.stdout.strip()
    print("🪟 弹窗返回:", output)
    parts = dict(
        item.split(":", 1) for item in output.split(", ") if ":" in item
    )
    button = parts.get("button returned", "")
    text = parts.get("text returned", "")
    return button == "发送", text


def display_notification_osascript(message: str) -> None:
    safe_message = message.replace("\\", "\\\\").replace('"', '\\"')
    applescript = f'display notification "{safe_message}" with title "干嘛猫"'
    try:
        subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print("⚠️ 通知调用失败（osascript 返回非 0）。")
        print("applescript:", applescript)
        print("stdout:", (exc.stdout or "").strip())
        print("stderr:", (exc.stderr or "").strip())


def display_dialog_tk(message: str) -> tuple[bool, str] | None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        print("⚠️ Tkinter 不可用，回退到 osascript。", exc)
        return None

    root = tk.Tk()
    root.withdraw()

    dialog = tk.Toplevel(root)
    dialog.title("干嘛猫")
    dialog.configure(bg="#f6f6f6")
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)

    width = 420
    height = 220
    x = int((dialog.winfo_screenwidth() - width) / 2)
    y = int((dialog.winfo_screenheight() - height) / 3)
    dialog.geometry(f"{width}x{height}+{x}+{y}")

    style = ttk.Style(dialog)
    try:
        style.theme_use("aqua")
    except Exception:
        pass

    container = ttk.Frame(dialog, padding=16)
    container.pack(fill="both", expand=True)

    label = ttk.Label(container, text=message, wraplength=380, justify="left")
    label.pack(anchor="w")

    entry = ttk.Entry(container)
    entry.pack(fill="x", pady=(12, 8))
    entry.focus_set()

    result = {"sent": False, "text": ""}

    def finish(sent: bool, text: str) -> None:
        result["sent"] = sent
        result["text"] = text
        dialog.destroy()

    def on_send():
        finish(True, entry.get())

    def on_close():
        finish(False, "")

    button_row = ttk.Frame(container)
    button_row.pack(fill="x")
    close_btn = ttk.Button(button_row, text="关闭", command=on_close)
    close_btn.pack(side="right", padx=(8, 0))
    send_btn = ttk.Button(button_row, text="发送", command=on_send)
    send_btn.pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", on_close)
    dialog.update_idletasks()
    dialog.deiconify()
    dialog.lift()
    dialog.focus_force()
    root.wait_window(dialog)
    root.destroy()
    return result["sent"], result["text"]


def display_notification_tk(message: str, timeout_seconds: int) -> bool | None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as exc:
        print("⚠️ Tkinter 不可用，回退到系统通知。", exc)
        return None

    root = tk.Tk()
    root.withdraw()

    notify = tk.Toplevel(root)
    notify.title("干嘛猫通知")
    notify.configure(bg="#f6f6f6")
    notify.overrideredirect(True)
    notify.attributes("-topmost", True)
    try:
        notify.attributes("-alpha", 0.96)
    except Exception:
        pass

    width = 320
    height = 90
    x = 16
    y = 24
    notify.geometry(f"{width}x{height}+{x}+{y}")

    container = ttk.Frame(notify, padding=12)
    container.pack(fill="both", expand=True)

    title = ttk.Label(container, text="干嘛猫", font=("Helvetica", 12, "bold"))
    title.pack(anchor="w")

    body = ttk.Label(container, text=message, wraplength=280, justify="left")
    body.pack(anchor="w", pady=(6, 0))

    clicked = {"value": False}
    closed = {"value": False}
    after_id = {"value": None}

    def finish(was_clicked: bool) -> None:
        clicked["value"] = was_clicked
        closed["value"] = not was_clicked
        if after_id["value"] is not None:
            try:
                notify.after_cancel(after_id["value"])
            except Exception:
                pass
        if notify.winfo_exists():
            notify.destroy()
        root.quit()

    def on_click(event=None):
        finish(True)

    def on_close(event=None):
        finish(False)

    notify.bind("<Button-1>", on_click)
    container.bind("<Button-1>", on_click)
    title.bind("<Button-1>", on_click)
    body.bind("<Button-1>", on_click)

    def fade_out(step=10):
        if not notify.winfo_exists():
            return
        try:
            alpha = float(notify.attributes("-alpha"))
        except Exception:
            alpha = 1.0
        alpha -= 0.08
        if alpha <= 0:
            on_close()
            return
        try:
            notify.attributes("-alpha", alpha)
        except Exception:
            on_close()
            return
        after_id["value"] = notify.after(step, fade_out, step)

    notify._on_click = on_click
    notify._on_close = on_close
    notify._fade_out = fade_out

    after_id["value"] = notify.after(max(100, timeout_seconds * 1000), fade_out)
    notify.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    root.destroy()

    if clicked["value"]:
        return True
    if closed["value"]:
        return False
    return False


def display_dialog_cocoa(message: str) -> tuple[bool, str] | None:
    try:
        appkit = importlib.import_module("AppKit")
        foundation = importlib.import_module("Foundation")

        NSAlert = getattr(appkit, "NSAlert")
        NSAlertFirstButtonReturn = getattr(appkit, "NSAlertFirstButtonReturn")
        NSAlertStyleInformational = getattr(appkit, "NSAlertStyleInformational")
        NSApplication = getattr(appkit, "NSApplication")
        NSApplicationActivateIgnoringOtherApps = getattr(
            appkit, "NSApplicationActivateIgnoringOtherApps"
        )
        NSRunningApplication = getattr(appkit, "NSRunningApplication")
        NSTextField = getattr(appkit, "NSTextField")
        NSMakeRect = getattr(foundation, "NSMakeRect")
    except Exception as exc:
        print("⚠️ PyObjC 不可用，回退到其他弹窗。", exc)
        return None

    NSApplication.sharedApplication()
    try:
        NSRunningApplication.currentApplication().activateWithOptions_(
            NSApplicationActivateIgnoringOtherApps
        )
    except Exception:
        pass

    alert = NSAlert.alloc().init()
    alert.setAlertStyle_(NSAlertStyleInformational)
    alert.setMessageText_("干嘛猫")
    alert.setInformativeText_(message)
    alert.addButtonWithTitle_("发送")
    alert.addButtonWithTitle_("关闭")

    input_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 320, 24))
    input_field.setStringValue_("")
    alert.setAccessoryView_(input_field)

    response = alert.runModal()
    sent = response == NSAlertFirstButtonReturn
    text = input_field.stringValue()
    return sent, text
