import tkinter as tk
from tkinter import ttk, messagebox
import json
import threading
import ollama
import os
import re
import subprocess
import time
import psutil

SAVE_FILE = "conversations.json"

def is_ollama_running():
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'ollama' in proc.info['name'].lower():
            return True
    return False

def start_ollama():
    try:
        if os.name == 'nt':
            subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
    except Exception as e:
        print(f"Failed to start Ollama: {e}")

if not is_ollama_running():
    print("Ollama not running — starting it...")
    start_ollama()

if os.path.exists(SAVE_FILE):
    with open(SAVE_FILE, "r", encoding="utf-8") as f:
        conversations = json.load(f)
else:
    conversations = {}

current_model = None
current_chat = None
titled = {}

def save_conversations():
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(conversations, f, ensure_ascii=False, indent=2)

def load_models():
    try:
        models_data = ollama.list()
        models = models_data.get("models", [])
        display_to_id = {}
        for m in models:
            model_id = m.get("model")
            if not model_id:
                continue
            display_name = model_id
            display_to_id[display_name] = model_id
        return display_to_id
    except Exception as e:
        print(f"Failed to fetch models: {e}")
        return {}

model_display_to_id = load_models()
if model_display_to_id:
    current_model = list(model_display_to_id.values())[0]

def new_chat():
    global current_chat
    current_chat = f"Chat {len(conversations) + 1}"
    conversations[current_chat] = []
    chat_listbox.insert(tk.END, current_chat)
    chat_listbox.selection_clear(0, tk.END)
    chat_listbox.selection_set(tk.END)
    refresh_chat_view()
    save_conversations()

def delete_chat():
    global current_chat
    selection = chat_listbox.curselection()
    if not selection:
        return
    chat_name = chat_listbox.get(selection[0])
    if messagebox.askyesno("Delete Chat", f"Are you sure you want to delete '{chat_name}'?"):
        conversations.pop(chat_name, None)
        chat_listbox.delete(selection[0])
        current_chat = None
        refresh_chat_view()
        save_conversations()

def ensure_chat_selected():
    global current_chat
    if current_chat is None:
        new_chat()
    return current_chat

def load_conversation(event=None):
    global current_chat
    selection = chat_listbox.curselection()
    if not selection:
        return
    current_chat = chat_listbox.get(selection[0])
    refresh_chat_view()

def refresh_chat_view():
    for widget in chat_frame_inner.winfo_children():
        widget.destroy()
    for is_user, text in conversations.get(current_chat, []):
        add_message(text, is_user=is_user)
    root.after(10, lambda: chat_canvas.yview_moveto(1.0))

def ask_model(prompt):
    stream = ollama.chat(
        model=current_model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    answer = ""
    for chunk in stream:
        content = chunk["message"]["content"]
        answer += content
    return clean_text(answer)

def clean_text(text):
    text = re.sub(r'^"(.*)"$', r'\1', text.strip())
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return text.strip()

def generate_title(first_user_msg, ai_reply):
    prompt = f"""Make a short descriptive title for this conversation.
User: {first_user_msg}
AI: {ai_reply}
Reply only with the title, no quotes, no punctuation at the end."""
    title = ollama.chat(
        model=current_model,
        messages=[{"role": "user", "content": prompt}]
    )["message"]["content"]
    return clean_text(title)

def add_message(text, is_user=False):
    bg_color = "#a5d6a7" if is_user else "#c8e6c9"
    frame = tk.Frame(chat_frame_inner, bg=bg_color, padx=10, pady=5)
    label = tk.Label(frame, text=text, wraplength=500, justify="left",
                     bg=bg_color, anchor="w", font=("Aptos Display", 11))
    label.pack(fill="x")
    frame.pack(anchor="w" if not is_user else "e", pady=3, padx=5, fill="x")
    def scroll_to_bottom():
        chat_canvas.update_idletasks()
        chat_canvas.yview_moveto(1.0)
    root.after(10, scroll_to_bottom)
    return label

def start_thinking_animation(label, anim_id):
    dots = ["thinking", "thinking.", "thinking..", "thinking..."]
    idx = 0
    def step():
        nonlocal idx
        if anim_id not in anim_running or not anim_running[anim_id]:
            return
        if not label.winfo_exists():
            return
        label.config(text=dots[idx % len(dots)])
        idx += 1
        root.after(500, step)
    anim_running[anim_id] = True
    step()

def stop_thinking_animation(anim_id, final_text):
    anim_running[anim_id] = False
    if anim_id in bubble_widgets and bubble_widgets[anim_id].winfo_exists():
        bubble_widgets[anim_id].config(text=final_text)

def run_query():
    global current_chat
    user_input = input_box.get("1.0", tk.END).strip()
    if not user_input:
        return
    name = ensure_chat_selected()
    conversations[name].append((True, user_input))
    save_conversations()
    add_message(user_input, is_user=True)
    input_box.delete("1.0", tk.END)
    bot_bubble = add_message("thinking", is_user=False)
    anim_id = f"bubble_{name}_{len(conversations[name])}"
    bubble_widgets[anim_id] = bot_bubble
    start_thinking_animation(bot_bubble, anim_id)
    def worker(chat_name=name, first_message=(len(conversations[name]) == 1)):
        answer = ask_model(user_input)
        conversations[chat_name].append((False, answer))
        save_conversations()
        stop_thinking_animation(anim_id, answer)
        if first_message:
            title = generate_title(user_input, answer)
            titled[chat_name] = title
            conversations[title] = conversations.pop(chat_name)
            current_chat = title
            idx = chat_listbox.get(0, tk.END).index(chat_name)
            chat_listbox.delete(idx)
            chat_listbox.insert(idx, title)
            save_conversations()
    threading.Thread(target=worker, daemon=True).start()

def change_model(event):
    global current_model
    display_name = model_var.get()
    current_model = model_display_to_id.get(display_name, current_model)

root = tk.Tk()
root.title("Ollama Wrapper")
root.iconphoto(False, tk.PhotoImage(file="OllamaWrapperIcon.png"))
root.configure(bg="#e8f5e9")

style = ttk.Style()
style.theme_use("clam")
style.configure("TButton", font=("Aptos Display", 12), padding=6, background="#66bb6a", foreground="white")
style.map("TButton", background=[("active", "#4caf50")])
style.configure("TCombobox", font=("Aptos Display", 12), padding=4, fieldbackground="#c8e6c9", background="#a5d6a7")

sidebar = tk.Frame(root, width=200, bg="#81c784")
sidebar.pack(side="left", fill="y")

new_chat_btn = ttk.Button(sidebar, text="➕ New Chat", command=new_chat)
new_chat_btn.pack(fill="x", pady=5, padx=5)

delete_chat_btn = ttk.Button(sidebar, text="🗑 Delete Chat", command=delete_chat)
delete_chat_btn.pack(fill="x", pady=5, padx=5)

chat_listbox = tk.Listbox(sidebar, bg="#c8e6c9", selectbackground="#388e3c", selectforeground="white", font=("Aptos Display", 11))
chat_listbox.pack(fill="both", expand=True, pady=5, padx=5)
chat_listbox.bind("<<ListboxSelect>>", load_conversation)

center_frame = tk.Frame(root, bg="#e8f5e9")
center_frame.pack(side="right", fill="both", expand=True)

max_len = max((len(name) for name in model_display_to_id.keys()), default=20)
model_var = tk.StringVar(value=list(model_display_to_id.keys())[0] if model_display_to_id else "")
model_dropdown = ttk.Combobox(center_frame, textvariable=model_var, state="readonly", values=list(model_display_to_id.keys()), width=max_len)
model_dropdown.grid(row=0, column=0, pady=10, padx=10, sticky="w")
model_dropdown.bind("<<ComboboxSelected>>", change_model)

chat_canvas = tk.Canvas(center_frame, bg="#f1f8e9", highlightthickness=0)
chat_scrollbar = tk.Scrollbar(center_frame, orient="vertical", command=chat_canvas.yview)
chat_frame_inner = tk.Frame(chat_canvas, bg="#f1f8e9")
chat_frame_window = chat_canvas.create_window((0, 0), window=chat_frame_inner, anchor="nw")
chat_canvas.configure(yscrollcommand=chat_scrollbar.set)
chat_canvas.grid(row=1, column=0, sticky="nsew", padx=(10,0))
chat_scrollbar.grid(row=1, column=1, sticky="ns", padx=(0,10))

def on_frame_configure(event):
    chat_canvas.configure(scrollregion=chat_canvas.bbox("all"))

chat_frame_inner.bind("<Configure>", on_frame_configure)

input_box = tk.Text(center_frame, height=3, font=("Aptos Display", 12), bg="#c8e6c9", relief="flat")
input_box.grid(row=2, column=0, pady=10, padx=10, sticky="ew")
send_button = ttk.Button(center_frame, text="Send", command=run_query)
send_button.grid(row=3, column=0, pady=5, padx=10, sticky="e")

center_frame.grid_rowconfigure(1, weight=1)
center_frame.grid_columnconfigure(0, weight=1)

anim_running = {}
bubble_widgets = {}

for title in conversations.keys():
    chat_listbox.insert(tk.END, title)

root.mainloop()
