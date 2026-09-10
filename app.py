import os
import re
import json
import shutil
import subprocess
import tempfile
import threading
import difflib
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

APP_TITLE = "Campus C Debugger V1.2"
DEFAULT_GCC = shutil.which("gcc") or shutil.which("gcc.exe") or ""

CONFIG_DIR = Path.home() / ".campus_c_debugger"
CONFIG_FILE = CONFIG_DIR / "config.json"

BG = "#f3f3f3"
PANEL = "#f3f3f3"
EDITOR_BG = "#ffffff"
GUTTER_BG = "#f7f7f7"
FG = "#202020"
MUTED = "#686868"
BORDER = "#dedede"
ACCENT = "#202020"
ERROR_BG = "#ffe3e3"
ERROR_FG = "#b42318"
FIX_BG = "#dcf5e3"
FIX_FG = "#176536"

THEMES = {
    "light": {
        "bg": "#f3f3f3", "panel": "#f3f3f3", "editor": "#ffffff",
        "gutter": "#f7f7f7", "fg": "#202020", "muted": "#686868",
        "border": "#dedede", "button": "#ffffff", "button_active": "#e5e5e5",
        "accent": "#202020", "accent_active": "#404040", "select": "#dce5ef",
        "scroll": "#d5d5d5", "trough": "#f5f5f5",
        "preprocessor": "#7040a0", "keyword": "#7040a0", "type": "#176b85",
        "string": "#9b431c", "comment": "#63705b", "number": "#176b60",
        "function": "#805c16", "error_bg": "#ffe3e3", "error_fg": "#b42318",
        "fix_bg": "#dcf5e3", "fix_fg": "#176536",
    },
    "dark": {
        "bg": "#151515", "panel": "#1d1d1d", "editor": "#111111",
        "gutter": "#181818", "fg": "#eeeeee", "muted": "#9a9a9a",
        "border": "#383838", "button": "#292929", "button_active": "#3a3a3a",
        "accent": "#f1f1f1", "accent_active": "#d5d5d5", "select": "#3b4b5b",
        "scroll": "#4a4a4a", "trough": "#232323",
        "preprocessor": "#c99be8", "keyword": "#c99be8", "type": "#6fc5d8",
        "string": "#e5a27a", "comment": "#8ca37e", "number": "#70c2aa",
        "function": "#dbc477", "error_bg": "#562323", "error_fg": "#ff9b91",
        "fix_bg": "#193d28", "fix_fg": "#91d7a7",
    },
}

SAMPLE_CODE = """#include <stdio.h>

int main()
{
    int age;
    int score = 90

    printf("请输入年龄：");
    scanf("%d", age);

    if (age = 18) {
        printf("你已经18岁了\\n");
    }

    printf("分数：%d\\n", score)

    return 0;
}
"""

C_KEYWORDS = {
    "auto","break","case","const","continue","default","do","else","enum","extern",
    "for","goto","if","register","return","sizeof","static","struct","switch","typedef",
    "union","volatile","while","inline","restrict","_Bool","_Complex","_Imaginary"
}
C_TYPES = {
    "char","double","float","int","long","short","signed","unsigned","void",
    "size_t","FILE"
}

def load_config():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_config(data):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        current = load_config()
        current.update(data)
        CONFIG_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def translate_gcc(msg: str) -> str:
    low = msg.lower()
    if "expected ',' or ';' before" in low or "expected ';' before" in low:
        return "缺少分号。"
    if "undeclared" in low:
        return "标识符未声明。"
    if "implicit declaration of function" in low:
        return "函数未声明，请补充对应头文件。"
    if "assignment used as truth value" in low or "suggest parentheses around assignment" in low:
        return "条件中使用了赋值号 =，应检查是否为 ==。"
    if "too few arguments" in low:
        return "函数参数数量不足。"
    if "too many arguments" in low:
        return "函数参数数量过多。"
    if "incompatible" in low and "type" in low:
        return "参数或变量类型不匹配。"
    if "format" in low:
        return "格式字符串与参数不匹配。"
    if "pointer" in low and ("integer" in low or "argument" in low):
        return "参数地址或类型错误。"
    if "expected expression" in low:
        return "表达式不完整。"
    if "expected ')'" in low:
        return "缺少右括号 )。"
    if "expected '}'" in low:
        return "缺少右花括号 }。"
    if "expected '{'" in low:
        return "缺少左花括号 {。"
    return "编译错误：" + msg

def parse_issues(raw: str, code: str):
    issues = []
    seen = set()
    code_lines = code.splitlines()

    for line in raw.splitlines():
        m = re.search(r"main\.c:(\d+):(\d+):\s+(warning|error|note):\s+(.*)", line, re.I)
        if not m:
            continue

        ln = int(m.group(1))
        col = int(m.group(2))
        level = m.group(3).lower()
        original = m.group(4).strip()
        msg = translate_gcc(original)

        # GCC often points at the next token when the previous line misses ';'.
        if ("expected ',' or ';' before" in original.lower() or "expected ';' before" in original.lower()) and ln > 1:
            prev = code_lines[ln - 2].strip() if ln - 2 < len(code_lines) else ""
            if prev and not prev.endswith((";", "{", "}", ":", ",")) and not prev.startswith("#"):
                ln -= 1
                col = max(1, len(code_lines[ln - 1]) + 1)

        key = (ln, col, level, msg)
        if key not in seen:
            seen.add(key)
            issues.append({
                "line": ln,
                "column": col,   # internal only; never shown in diagnostics
                "level": level,
                "message": msg,
                "raw_message": original
            })
    return issues

def compile_code(code: str, gcc_path: str):
    gcc = (gcc_path or "").strip()
    if not gcc:
        gcc = shutil.which("gcc") or shutil.which("gcc.exe") or ""

    if not gcc or (not os.path.isfile(gcc) and not shutil.which(gcc)):
        return {
            "ok": False,
            "raw": "未配置可用编译器。",
            "issues": [{"line": None, "column": None, "level": "error", "message": "请在设置中配置编译器。"}],
        }

    try:
        with tempfile.TemporaryDirectory() as td:
            cfile = os.path.join(td, "main.c")
            exe = os.path.join(td, "program.exe" if os.name == "nt" else "program")
            with open(cfile, "w", encoding="utf-8", newline="\n") as f:
                f.write(code)

            p = subprocess.run(
                [
                    gcc, "-std=c11", "-Wall", "-Wextra", "-Wpedantic",
                    "-fdiagnostics-color=never", cfile, "-o", exe
                ],
                capture_output=True, text=True, errors="replace", timeout=20,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
            raw = (p.stderr or "") + (p.stdout or "")
            return {"ok": p.returncode == 0, "raw": raw, "issues": parse_issues(raw, code)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "raw": "编译超时。", "issues": [{"line": None, "column": None, "level": "error", "message": "编译超时。"}]}
    except Exception:
        return {"ok": False, "raw": "编译器调用失败。", "issues": [{"line": None, "column": None, "level": "error", "message": "编译器调用失败。"}]}

def safe_fix(code: str):
    fixes = []
    fixed = code

    new = re.sub(
        r"\bif\s*\(\s*([A-Za-z_]\w*)\s*=\s*(-?\d+)\s*\)",
        r"if (\1 == \2)", fixed
    )
    if new != fixed:
        fixes.append("修正 if 条件中的赋值号。")
        fixed = new

    scalars = set(re.findall(
        r"\b(?:signed\s+|unsigned\s+)?(?:char|short|int|long|float|double)\s+([A-Za-z_]\w*)\s*(?:=[^;]*)?;",
        fixed
    ))

    def scanf_repl(m):
        fmt, var = m.group(1), m.group(2)
        if var in scalars:
            fixes.append(f"为 {var} 补充取地址符 &。")
            return f'scanf("{fmt}", &{var});'
        return m.group(0)

    fixed = re.sub(
        r'scanf\s*\(\s*"([^"]*%[diufc][^"]*)"\s*,\s*([A-Za-z_]\w*)\s*\)\s*;',
        scanf_repl, fixed
    )

    out_lines = []
    for idx, line in enumerate(fixed.splitlines(), start=1):
        stripped = line.strip()
        add = False
        if stripped and not stripped.endswith((";", "{", "}", ":", ",")) and not stripped.startswith("#"):
            if re.match(
                r"^(?:signed\s+|unsigned\s+)?(?:char|short|int|long|float|double)\s+[A-Za-z_]\w*(?:\s*=\s*[^;{}]+)?$",
                stripped
            ):
                add = True
            elif re.match(r"^(?:printf|puts|scanf)\s*\(.*\)$", stripped):
                add = True

        if add:
            line += ";"
            fixes.append(f"第 {idx} 行补充分号。")
        out_lines.append(line)

    fixed = "\n".join(out_lines)

    if re.search(r"\b(?:printf|scanf|puts|getchar|putchar)\s*\(", fixed):
        if not re.search(r'^\s*#\s*include\s*[<"]stdio\.h[>"]', fixed, re.M):
            fixed = "#include <stdio.h>\n" + fixed
            fixes.append("补充 stdio.h。")

    return fixed, fixes

def changed_spans(old: str, new: str):
    matcher = difflib.SequenceMatcher(a=old, b=new)
    spans = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            spans.append((j1, j2))
    return spans

class CodeEditor(tk.Frame):
    def __init__(self, master, editable=True):
        super().__init__(master, bg=EDITOR_BG, highlightthickness=1, highlightbackground=BORDER)

        self.code_font = tkfont.Font(family="Consolas", size=13)
        self.gutter = tk.Canvas(self, width=58, takefocus=0, borderwidth=0,
                                highlightthickness=0, background=GUTTER_BG)
        self.gutter.grid(row=0, column=0, sticky="ns")

        self.scroll = ttk.Scrollbar(self, orient="vertical")
        self.scroll.grid(row=0, column=2, sticky="ns")

        self.text = tk.Text(
            self, wrap="none", undo=editable, font=self.code_font,
            background=EDITOR_BG, foreground=FG, insertbackground=FG,
            selectbackground="#dce5ef", selectforeground=FG,
            border=0, highlightthickness=0, padx=12, pady=12,
            yscrollcommand=self._on_text_scroll, relief="flat"
        )
        self.text.grid(row=0, column=1, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.hscroll = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.hscroll.grid(row=1, column=1, sticky="ew")
        self.text.configure(xscrollcommand=self.hscroll.set)
        self.scroll.configure(command=self._on_scrollbar)

        # VS Code-like token colors
        self.text.tag_configure("preprocessor", foreground="#7040a0")
        self.text.tag_configure("keyword", foreground="#7040a0")
        self.text.tag_configure("type", foreground="#176b85")
        self.text.tag_configure("string", foreground="#9b431c")
        self.text.tag_configure("comment", foreground="#63705b")
        self.text.tag_configure("number", foreground="#176b60")
        self.text.tag_configure("function", foreground="#805c16")

        # Error/fix overlays come last and visually dominate syntax highlighting
        self.text.tag_configure("error_span", background=ERROR_BG, foreground=ERROR_FG)
        self.text.tag_configure("fixed_span", background=FIX_BG, foreground=FIX_FG)

        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<Configure>", lambda e: self.refresh_gutter())
        self.text.bind("<KeyRelease>", lambda e: self.schedule_highlight())

        self._highlight_job = None
        self.apply_theme("light")
        self.refresh_gutter()

    def apply_theme(self, mode):
        c = THEMES[mode]
        self.gutter_fg = c["muted"]
        self.configure(bg=c["editor"], highlightbackground=c["border"])
        self.gutter.configure(background=c["gutter"])
        self.text.configure(
            background=c["editor"], foreground=c["fg"], insertbackground=c["fg"],
            selectbackground=c["select"], selectforeground=c["fg"]
        )
        for tag in ("preprocessor", "keyword", "type", "string", "comment", "number", "function"):
            self.text.tag_configure(tag, foreground=c[tag])
        self.text.tag_configure("error_span", background=c["error_bg"], foreground=c["error_fg"])
        self.text.tag_configure("fixed_span", background=c["fix_bg"], foreground=c["fix_fg"])
        self.refresh_gutter()

    def _on_text_scroll(self, first, last):
        self.scroll.set(first, last)
        self.refresh_gutter()

    def _on_scrollbar(self, *args):
        self.text.yview(*args)
        self.refresh_gutter()

    def _on_modified(self, event=None):
        if self.text.edit_modified():
            self.refresh_gutter()
            self.schedule_highlight()
            self.text.edit_modified(False)

    def refresh_gutter(self):
        count = int(self.text.index("end-1c").split(".")[0])
        width = self.code_font.measure("9" * max(3, len(str(count)))) + 24
        self.gutter.configure(width=width)
        self.gutter.delete("all")
        index = self.text.index("@0,0 linestart")
        ascent = self.code_font.metrics("ascent")
        while True:
            info = self.text.dlineinfo(index)
            if info is None:
                break
            # Use the actual text baseline, including mixed Chinese/Latin fonts.
            self.gutter.create_text(width - 12, info[1] + info[4] - ascent,
                                    anchor="ne", text=index.split(".")[0],
                                    fill=self.gutter_fg, font=self.code_font)
            index = self.text.index(f"{index}+1line")

    def schedule_highlight(self):
        if self._highlight_job:
            try:
                self.after_cancel(self._highlight_job)
            except Exception:
                pass
        self._highlight_job = self.after(120, self.apply_syntax_highlight)

    def get(self):
        return self.text.get("1.0", "end-1c")

    def set(self, value):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.refresh_gutter()
        self.apply_syntax_highlight()

    def clear_overlays(self):
        self.text.tag_remove("error_span", "1.0", "end")
        self.text.tag_remove("fixed_span", "1.0", "end")

    def apply_syntax_highlight(self):
        content = self.get()
        for tag in ("preprocessor","keyword","type","string","comment","number","function"):
            self.text.tag_remove(tag, "1.0", "end")

        # comments
        for m in re.finditer(r"//.*?$|/\*.*?\*/", content, re.M | re.S):
            self._tag_abs("comment", m.start(), m.end())

        # strings/chars
        for m in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', content):
            self._tag_abs("string", m.start(), m.end())

        # preprocessor lines
        for m in re.finditer(r"^[ \t]*#.*$", content, re.M):
            self._tag_abs("preprocessor", m.start(), m.end())

        # numbers
        for m in re.finditer(r"\b(?:0x[0-9A-Fa-f]+|\d+(?:\.\d+)?)\b", content):
            self._tag_abs("number", m.start(), m.end())

        # identifiers: keyword/type/function
        for m in re.finditer(r"\b[A-Za-z_]\w*\b", content):
            word = m.group(0)
            if word in C_KEYWORDS:
                self._tag_abs("keyword", m.start(), m.end())
            elif word in C_TYPES:
                self._tag_abs("type", m.start(), m.end())
            else:
                tail = content[m.end():]
                if re.match(r"\s*\(", tail):
                    self._tag_abs("function", m.start(), m.end())

        self.text.tag_raise("error_span")
        self.text.tag_raise("fixed_span")

    def _tag_abs(self, tag, start, end):
        if end <= start:
            return
        self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")

    def highlight_issue(self, line, column, raw_message=""):
        if not line:
            return

        content = self.get()
        lines = content.splitlines(True)
        if line > len(lines):
            return

        line_start_abs = sum(len(x) for x in lines[:line-1])
        line_text = lines[line-1].rstrip("\r\n")
        col0 = max(0, min(len(line_text), (column or 1) - 1))

        # Missing semicolon: mark a compact end-of-line area, not the whole line.
        low = (raw_message or "").lower()
        if "expected ';' before" in low or "expected ',' or ';' before" in low:
            if line_text:
                start = line_start_abs + max(0, len(line_text) - 1)
                end = line_start_abs + len(line_text)
            else:
                start = line_start_abs
                end = line_start_abs + 1
            self._tag_abs("error_span", start, end)
            return

        # Highlight the token around GCC's internal column.
        token_re = re.compile(r"[A-Za-z_]\w*|==|!=|<=|>=|=|[^\s]")
        chosen = None
        for m in token_re.finditer(line_text):
            if m.start() <= col0 < m.end() or m.start() >= col0:
                chosen = m
                break
        if chosen is None:
            start = line_start_abs + max(0, min(col0, len(line_text)-1))
            end = min(line_start_abs + len(line_text), start + 1)
        else:
            start = line_start_abs + chosen.start()
            end = line_start_abs + chosen.end()

        self._tag_abs("error_span", start, end)
        self.text.tag_raise("error_span")

    def highlight_fixed_spans(self, old, new):
        self.text.tag_remove("fixed_span", "1.0", "end")
        for start, end in changed_spans(old, new):
            if end > start:
                self._tag_abs("fixed_span", start, end)
        self.text.tag_raise("fixed_span")

class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("1450x900")
        root.minsize(1100, 720)
        root.configure(bg=BG)

        config = load_config()
        self.theme_mode = config.get("theme", "light")
        if self.theme_mode not in THEMES:
            self.theme_mode = "light"
        self.gcc_var = tk.StringVar(value=config.get("gcc_path") or DEFAULT_GCC)
        self.status_var = tk.StringVar(value="就绪")

        style = ttk.Style()
        self.style = style
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=PANEL, foreground=FG, font=("Microsoft YaHei", 11))
        style.configure("TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=FG)
        style.configure("TButton", background="#ffffff", foreground=FG, padding=(14,9), relief="flat", borderwidth=1)
        style.map("TButton", background=[("active","#e5e5e5")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
        style.map("Accent.TButton", background=[("active","#404040")])
        style.configure("TEntry", fieldbackground="#ffffff", foreground=FG)
        style.configure("TScrollbar", background="#d5d5d5", troughcolor="#f5f5f5", borderwidth=0, arrowsize=14)

        top = ttk.Frame(root, padding=(10, 8))
        self.top = top
        top.pack(fill="x")

        ttk.Label(
            top, text="Campus C Debugger",
            font=("Microsoft YaHei", 15, "bold")
        ).pack(side="left", padx=(4, 18))

        ttk.Button(top, text="检测", style="Accent.TButton", command=self.analyze).pack(side="left", padx=4)
        ttk.Button(top, text="自动修复", command=self.fix_and_verify).pack(side="left", padx=4)
        ttk.Button(top, text="复制修复", command=self.copy_fixed).pack(side="left", padx=4)
        ttk.Button(top, text="一键清空", command=self.clear_all).pack(side="left", padx=4)

        ttk.Button(top, text="设置", command=self.open_settings).pack(side="right", padx=4)
        self.theme_button = ttk.Button(top, command=self.toggle_theme)
        self.theme_button.pack(side="right", padx=4)
        ttk.Label(top, textvariable=self.status_var, foreground=MUTED).pack(side="right", padx=(0, 12))

        main = tk.Frame(root, bg=BG)
        self.main = main
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        editors = tk.PanedWindow(
            main, orient="horizontal", sashwidth=4, bg=BORDER,
            bd=0, relief="flat"
        )
        self.editors = editors
        editors.pack(fill="both", expand=True)

        left_wrap = tk.Frame(editors, bg=PANEL)
        right_wrap = tk.Frame(editors, bg=PANEL)
        self.left_wrap, self.right_wrap = left_wrap, right_wrap
        editors.add(left_wrap, stretch="always", minsize=450)
        editors.add(right_wrap, stretch="always", minsize=450)

        # Thin, unobtrusive headers like editor tabs
        left_head = tk.Frame(left_wrap, bg=PANEL, height=28)
        left_head.pack(fill="x")
        tk.Label(left_head, text="原始", bg=PANEL, fg=FG,
                 font=("Microsoft YaHei", 10)).pack(side="left", padx=10, pady=4)

        right_head = tk.Frame(right_wrap, bg=PANEL, height=28)
        right_head.pack(fill="x")
        tk.Label(right_head, text="修复后", bg=PANEL, fg=FG,
                 font=("Microsoft YaHei", 10)).pack(side="left", padx=10, pady=4)

        self.code = CodeEditor(left_wrap)
        self.code.pack(fill="both", expand=True)
        self.code.set(SAMPLE_CODE)

        self.fixed = CodeEditor(right_wrap)
        self.fixed.pack(fill="both", expand=True)

        diag_wrap = tk.Frame(main, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        self.diag_wrap = diag_wrap
        # Keep diagnostics directly below the toolbar so results never require
        # scrolling down to find them.
        diag_wrap.pack(fill="x", pady=(0, 6), before=editors)

        diag_head = tk.Frame(diag_wrap, bg=PANEL)
        diag_head.pack(fill="x")
        tk.Label(diag_head, text="问题", bg=PANEL, fg=FG,
                 font=("Microsoft YaHei", 10)).pack(side="left", padx=10, pady=5)

        self.diag = tk.Text(
            diag_wrap, height=5, wrap="word",
            font=("Microsoft YaHei", 10),
            background=EDITOR_BG, foreground=FG, insertbackground=FG,
            border=0, padx=10, pady=8, state="disabled"
        )
        self.diag.pack(fill="x")

        self.apply_theme(self.theme_mode)
        self.check_gcc(silent=True)

    def apply_theme(self, mode):
        self.theme_mode = mode
        c = THEMES[mode]
        self.root.configure(bg=c["bg"])
        self.style.configure(".", background=c["panel"], foreground=c["fg"],
                             font=("Microsoft YaHei", 10))
        self.style.configure("TFrame", background=c["panel"])
        self.style.configure("TLabel", background=c["panel"], foreground=c["fg"])
        self.style.configure("TButton", background=c["button"], foreground=c["fg"],
                             padding=(12, 7), relief="flat", borderwidth=1)
        self.style.map("TButton", background=[("active", c["button_active"])])
        self.style.configure("Accent.TButton", background=c["accent"],
                             foreground=c["editor"])
        self.style.map("Accent.TButton", background=[("active", c["accent_active"])])
        self.style.configure("TEntry", fieldbackground=c["editor"], foreground=c["fg"])
        self.style.configure("TScrollbar", background=c["scroll"],
                             troughcolor=c["trough"], borderwidth=0, arrowsize=13)

        def recolor(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.PanedWindow):
                    child.configure(bg=c["border"])
                elif isinstance(child, tk.Frame) and not isinstance(child, CodeEditor):
                    child.configure(bg=c["panel"])
                elif isinstance(child, tk.Label):
                    child.configure(bg=c["panel"], fg=c["fg"])
                recolor(child)

        self.main.configure(bg=c["bg"])
        recolor(self.root)
        self.diag_wrap.configure(highlightbackground=c["border"])
        self.diag.configure(background=c["editor"], foreground=c["fg"],
                            insertbackground=c["fg"], selectbackground=c["select"])
        self.code.apply_theme(mode)
        self.fixed.apply_theme(mode)
        self.theme_button.configure(text="日间模式" if mode == "dark" else "夜间模式")
        save_config({"theme": mode})

    def toggle_theme(self):
        self.apply_theme("dark" if self.theme_mode == "light" else "light")

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("690x250")
        win.resizable(False, False)
        win.configure(bg=THEMES[self.theme_mode]["panel"])
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="编译器设置", font=("Microsoft YaHei", 13, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 16)
        )
        ttk.Label(frame, text="GCC 路径").grid(row=1, column=0, sticky="w")

        ttk.Entry(frame, textvariable=self.gcc_var, width=58).grid(
            row=1, column=1, sticky="ew", padx=8
        )
        ttk.Button(frame, text="选择 gcc.exe", command=self.choose_gcc).grid(row=1, column=2)

        self.settings_status = tk.StringVar(value="尚未检测")
        ttk.Label(frame, textvariable=self.settings_status).grid(
            row=2, column=1, sticky="w", padx=8, pady=(12, 0)
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=3, sticky="e", pady=(24, 0))
        ttk.Button(
            buttons, text="检测编译器",
            command=lambda: self.check_gcc(silent=False, settings=True)
        ).pack(side="left")
        ttk.Button(buttons, text="保存", command=lambda: self.save_settings(win)).pack(side="left", padx=8)
        ttk.Button(buttons, text="关闭", command=win.destroy).pack(side="left")

        frame.columnconfigure(1, weight=1)

    def save_settings(self, win=None):
        save_config({"gcc_path": self.gcc_var.get().strip()})
        if win:
            win.destroy()

    def choose_gcc(self):
        path = filedialog.askopenfilename(
            title="选择 gcc.exe",
            filetypes=[("GCC", "gcc.exe"), ("EXE", "*.exe"), ("所有文件", "*.*")]
        )
        if path:
            self.gcc_var.set(path)
            save_config({"gcc_path": path})
            if hasattr(self, "settings_status"):
                self.settings_status.set("已选择，点击“检测编译器”确认。")

    def check_gcc(self, silent=False, settings=False):
        gcc = self.gcc_var.get().strip() or shutil.which("gcc") or shutil.which("gcc.exe") or ""
        if gcc:
            try:
                p = subprocess.run(
                    [gcc, "--version"], capture_output=True, text=True, errors="replace",
                    timeout=8, creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                )
                if p.returncode == 0:
                    first = (p.stdout or "").splitlines()[0] if (p.stdout or "").splitlines() else gcc
                    save_config({"gcc_path": gcc})
                    if settings and hasattr(self, "settings_status"):
                        self.settings_status.set("检测成功：" + first)
                    return True
            except Exception:
                pass

        if settings and hasattr(self, "settings_status"):
            self.settings_status.set("未检测到可用编译器。")
        if not silent and not settings:
            messagebox.showwarning("未检测到编译器", "请在设置中选择 gcc.exe。")
        return False

    def set_diag(self, text):
        self.diag.configure(state="normal")
        self.diag.delete("1.0", "end")
        self.diag.insert("1.0", text)
        self.diag.configure(state="disabled")
        # Always reveal the beginning of the latest result immediately.
        self.diag.yview_moveto(0.0)
        self.diag.see("1.0")
        self.diag_wrap.lift()

    def show_result(self, result, prefix=""):
        lines = []
        if prefix:
            lines.append(prefix)

        if result.get("ok"):
            lines.append("✓ 编译通过")
        else:
            issues = result.get("issues", [])
            if not issues:
                lines.append("编译未通过")
            else:
                for issue in issues:
                    if issue.get("line"):
                        lines.append(f"第 {issue['line']} 行  {issue.get('message','')}")
                    else:
                        lines.append(issue.get("message",""))

        self.set_diag("\n".join(lines))

    def run_async(self, fn):
        self.status_var.set("处理中…")
        def worker():
            try:
                fn()
            finally:
                self.root.after(0, lambda: self.status_var.set("就绪"))
        threading.Thread(target=worker, daemon=True).start()

    def analyze(self):
        code = self.code.get()
        gcc = self.gcc_var.get().strip()
        self.code.clear_overlays()

        def job():
            result = compile_code(code, gcc)
            def update():
                self.show_result(result)
                for issue in result.get("issues", []):
                    self.code.highlight_issue(
                        issue.get("line"),
                        issue.get("column"),
                        issue.get("raw_message","")
                    )
            self.root.after(0, update)
        self.run_async(job)

    def fix_and_verify(self):
        original = self.code.get()
        gcc = self.gcc_var.get().strip()

        def job():
            fixed, fixes = safe_fix(original)
            after = compile_code(fixed, gcc)

            def update():
                self.fixed.set(fixed)
                self.fixed.clear_overlays()
                self.fixed.highlight_fixed_spans(original, fixed)

                # Keep original side marked with original compiler errors.
                before = compile_code(original, gcc)
                self.code.clear_overlays()
                for issue in before.get("issues", []):
                    self.code.highlight_issue(
                        issue.get("line"),
                        issue.get("column"),
                        issue.get("raw_message","")
                    )

                prefix = "已修复  " + ("；".join(fixes) if fixes else "无可自动修复项")
                prefix += "\n重新验证  " + ("通过" if after.get("ok") else "仍有错误")
                self.show_result(after, prefix)

            self.root.after(0, update)

        self.run_async(job)

    def copy_fixed(self):
        text = self.fixed.get()
        if not text:
            text = self.code.get()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("已复制")

    def clear_all(self):
        self.code.set("")
        self.fixed.set("")
        self.code.clear_overlays()
        self.fixed.clear_overlays()
        self.set_diag("")
        self.status_var.set("已清空")

def main():
    # Must run before Tk creates any window; avoid Windows bitmap stretching.
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
