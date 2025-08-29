# -*- coding: utf-8 -*-
"""
EmbyCollectionsCoverBuilder.py

特性总览（含本次更新）：
- GUI 交互：选择扫描根目录 → 选择 set（仅显示≥2部）→ 选择输出根目录
- 视频→NFO：同名 .nfo 优先，找不到回退 movie.nfo
- <set> 兼容：支持 <set ...>，优先 <name>；无 <name> 兜底提取
- 封面查找：以“视频文件”为中心优先匹配同名图片；再找预设名；再模糊（含视频名/含 poster/取最大）
- 合集海报：竖版 400×600，2×2 无边框；≥4 随机取 4；==2 时为 A,B,B,A；<2 允许重复补足到 4
- 输出路径：<选择的输出根目录>\collections\<合集名称>\auto_poster_<合集名称>.jpg
- CSV 编码：UTF-8（带 BOM）以便 Excel 直接打开不乱码（encoding="utf-8-sig"）
- 名称清洗：非法字符替换为“空格”，并压缩连续空格（避免下划线）
- 打包安全：日志/输出可写性检测与回退
"""

from __future__ import annotations

import os
import re
import sys
import csv
import time
import shutil
import random
import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 可选：Pillow 用于拼贴；无 Pillow 时复制最大图回退（尺寸不保证 400x600）
try:
    from PIL import Image
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

# -----------------------
# 路径/日志工具
# -----------------------

def get_app_base_dir() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "executable"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_fallback_user_dir() -> str:
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    d = os.path.join(base, "set_rec_outputs")
    os.makedirs(d, exist_ok=True)
    return d

def is_writable_dir(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        testfile = os.path.join(path, ".write_test.tmp")
        with open(testfile, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(testfile)
        return True
    except Exception:
        return False

def ensure_writable_dir(preferred: str) -> str:
    return preferred if is_writable_dir(preferred) else get_fallback_user_dir()

def setup_logging(log_base_dir: Optional[str]) -> Tuple[logging.Logger, str, str]:
    app_base = get_app_base_dir()
    if not log_base_dir:
        log_base_dir = os.path.join(app_base, "logs")
    log_dir = ensure_writable_dir(log_base_dir)
    log_file = os.path.join(log_dir, "set_rec.log")

    logger = logging.getLogger("set_rec")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info("=" * 72)
    logger.info("程序启动：build_collections_poster_from_nfo_log.py")
    logger.info("日志目录：%s", log_dir)
    if not HAVE_PIL:
        logger.info("未检测到 Pillow，合集海报将采用“复制最大图”回退（尺寸可能不为 400x600）。")
        logger.info("如需竖版 2x2 拼贴，请安装：pip install pillow")
    logger.info("=" * 72)
    return logger, log_dir, log_file

# -----------------------
# GUI
# -----------------------

def pick_directory_gui(title: str) -> Optional[str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askdirectory(title=title, mustexist=True)
        root.destroy()
        return path or None
    except Exception:
        return None

def pick_sets_gui(all_sets: List[str]) -> Optional[List[str]]:
    """Tk 列表框多选 set；取消/关闭返回 None（视作全选）。传入 all_sets 已过滤为“影片数≥2”"""
    try:
        import tkinter as tk

        selected: List[str] = []

        def on_ok():
            sel = [lb.get(i) for i in lb.curselection()]
            selected.clear()
            selected.extend(sel)
            win.destroy()

        def on_cancel():
            win.destroy()

        win = tk.Tk()
        win.title("请选择要处理的合集（不选=全部；仅显示≥2部的合集）")
        win.geometry("520x460")

        tk.Label(win, text="Ctrl/Shift 可多选：").pack(pady=6)

        fr = tk.Frame(win)
        fr.pack(fill="both", expand=True, padx=10, pady=6)

        sb = tk.Scrollbar(fr)
        sb.pack(side="right", fill="y")
        lb = tk.Listbox(fr, selectmode="extended")
        lb.pack(side="left", fill="both", expand=True)
        lb.config(yscrollcommand=sb.set)
        sb.config(command=lb.yview)

        for s in all_sets:
            lb.insert("end", s)

        btn_fr = tk.Frame(win)
        btn_fr.pack(pady=8)
        tk.Button(btn_fr, text="确定", width=10, command=on_ok).pack(side="left", padx=8)
        tk.Button(btn_fr, text="取消（全部）", width=14, command=on_cancel).pack(side="left", padx=8)

        win.mainloop()
        return selected if selected else None
    except Exception:
        return None

# -----------------------
# 扫描
# -----------------------

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".ts", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PRESET_POSTER_NAMES = [
    "poster.jpg", "folder.jpg", "cover.jpg", "fanart.jpg",
    "poster.png", "folder.png", "cover.png", "fanart.png",
]

def iter_video_files(root: str, max_depth: int = 6) -> List[str]:
    results: List[str] = []
    root = os.path.abspath(root)
    root_depth = len(Path(root).parts)
    for dirpath, _, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - root_depth
        if depth > max_depth:
            continue
        for name in filenames:
            if os.path.splitext(name)[1].lower() in VIDEO_EXTS:
                results.append(os.path.join(dirpath, name))
    return results

# -----------------------
# NFO 解析（含 <set> 兼容）
# -----------------------

TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)
YEAR_RE = re.compile(r"<year>\s*(\d{4})\s*</year>", re.IGNORECASE)
ID_RE = re.compile(r"<id>\s*(.*?)\s*</id>", re.IGNORECASE | re.DOTALL)
TMDB_RE = re.compile(r"<tmdbid>\s*(\d+)\s*</tmdbid>", re.IGNORECASE)
IMDB_RE = re.compile(r"<imdbid>\s*(tt\d+)\s*</imdbid>", re.IGNORECASE)

# <set> 带属性 & 兜底
SET_WITH_NAME_RE = re.compile(
    r"<set\b[^>]*>\s*<name>\s*(.*?)\s*</name>.*?</set>",
    re.IGNORECASE | re.DOTALL
)
SET_TEXT_FALLBACK_RE = re.compile(
    r"<set\b[^>]*>\s*(.*?)\s*</set>",
    re.IGNORECASE | re.DOTALL
)

def _clean_xml_text(s: str) -> str:
    if not s:
        return ""
    s_no_tags = re.sub(r"<[^>]+>", " ", s)
    s_clean = re.sub(r"\s+", " ", s_no_tags).strip()
    return s_clean

def parse_set_name(text: str) -> Optional[str]:
    m = SET_WITH_NAME_RE.search(text)
    if m:
        val = _clean_xml_text(m.group(1))
        return val or None
    m2 = SET_TEXT_FALLBACK_RE.search(text)
    if m2:
        val = _clean_xml_text(m2.group(1))
        return val or None
    return None

def parse_nfo_text(text: str) -> Dict[str, Optional[str]]:
    def first_or_none(m: Optional[re.Match]) -> Optional[str]:
        if not m:
            return None
        return re.sub(r"\s+", " ", m.group(1).strip())
    return {
        "title": first_or_none(TITLE_RE.search(text)),
        "year": first_or_none(YEAR_RE.search(text)),
        "id": first_or_none(ID_RE.search(text)),
        "tmdbid": first_or_none(TMDB_RE.search(text)),
        "imdbid": first_or_none(IMDB_RE.search(text)),
        "set_name": parse_set_name(text),
    }

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

# -----------------------
# 视频→NFO 与 视频→Poster
# -----------------------

def find_nfo_for_video(video_path: str, logger: Optional[logging.Logger] = None) -> Optional[str]:
    """同名 .nfo 优先；否则 movie.nfo；否则 None"""
    d = os.path.dirname(video_path)
    base = os.path.splitext(os.path.basename(video_path))[0].lower()
    try:
        names = os.listdir(d)
    except Exception as e:
        if logger:
            logger.warning("读取目录失败：%s —— %s", d, e)
        return None
    lower_map = {name.lower(): name for name in names}

    same_nfo_lower = f"{base}.nfo"
    if same_nfo_lower in lower_map:
        p = os.path.join(d, lower_map[same_nfo_lower])
        if os.path.isfile(p):
            if logger:
                logger.info("视频匹配同名 NFO：%s -> %s", video_path, p)
            return p
    if "movie.nfo" in lower_map:
        p = os.path.join(d, lower_map["movie.nfo"])
        if os.path.isfile(p):
            if logger:
                logger.info("视频使用 movie.nfo：%s -> %s", video_path, p)
            return p
    if logger:
        logger.info("未找到可用 NFO：%s", video_path)
    return None

def find_poster_for_video(video_path: str, logger: Optional[logging.Logger] = None) -> Optional[str]:
    """
    依据“视频文件”优先查找封面（返回绝对路径）：
    1) 同名图片：<video_stem>.(jpg/png/webp/bmp)
    2) 预设固定名：poster.jpg/folder.jpg/...（忽略大小写）
    3) 模糊：文件名包含视频名关键词（去常见语言/质量后缀）
    4) 模糊：名称包含 'poster'
    5) 兜底：目录下最大图片
    """
    d = os.path.dirname(video_path)
    if not os.path.isdir(d):
        return None

    base = os.path.splitext(os.path.basename(video_path))[0]
    files = os.listdir(d)
    lower_map = {name.lower(): name for name in files}

    # 1) 同名图片
    for ext in IMAGE_EXTS:
        cand = f"{base}{ext}"
        if cand.lower() in lower_map:
            p = os.path.join(d, lower_map[cand.lower()])
            if os.path.isfile(p):
                if logger: logger.info("命中同名海报：%s", p)
                return p

    # 2) 预设固定名
    for preset in PRESET_POSTER_NAMES:
        if preset.lower() in lower_map:
            p = os.path.join(d, lower_map[preset.lower()])
            if os.path.isfile(p):
                if logger: logger.info("命中预设海报：%s", p)
                return p

    # 3) 模糊：包含视频名关键词
    def normalize(s: str) -> str:
        s = s.lower()
        for token in ["-zh", "_zh", "zh-cn", "zh-hans", "ja-jp", "cn", "chs", "cht", "1080p", "720p"]:
            s = s.replace(token, "")
        return re.sub(r"\s+", "", s)

    norm_base = normalize(base)
    fuzzy = []
    for name in files:
        stem, ext = os.path.splitext(name)
        if ext.lower() in IMAGE_EXTS and norm_base and normalize(stem).find(norm_base) >= 0:
            full = os.path.join(d, name)
            try:
                size = os.path.getsize(full)
            except Exception:
                size = 0
            fuzzy.append((size, full))
    if fuzzy:
        fuzzy.sort(reverse=True)
        if logger: logger.info("模糊命中（含视频名关键词）：%s", fuzzy[0][1])
        return fuzzy[0][1]

    # 4) 名称包含 'poster'
    poster_like = []
    for name in files:
        stem, ext = os.path.splitext(name)
        if ext.lower() in IMAGE_EXTS and "poster" in name.lower():
            full = os.path.join(d, name)
            try:
                size = os.path.getsize(full)
            except Exception:
                size = 0
            poster_like.append((size, full))
    if poster_like:
        poster_like.sort(reverse=True)
        if logger: logger.info("模糊命中（含 poster）：%s", poster_like[0][1])
        return poster_like[0][1]

    # 5) 兜底：最大图片
    any_imgs = []
    for name in files:
        stem, ext = os.path.splitext(name)
        if ext.lower() in IMAGE_EXTS:
            full = os.path.join(d, name)
            try:
                size = os.path.getsize(full)
            except Exception:
                size = 0
            any_imgs.append((size, full))
    if any_imgs:
        any_imgs.sort(reverse=True)
        if logger: logger.info("兜底最大图片：%s", any_imgs[0][1])
        return any_imgs[0][1]

    if logger: logger.info("未找到海报：%s", video_path)
    return None

# -----------------------
# CSV 输出（UTF-8 with BOM）
# -----------------------

def write_csv_rows(csv_path: str, rows: List[List[str]], header: List[str], logger: logging.Logger) -> None:
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    # 关键改动：使用 utf-8-sig，Excel 直接识别为 UTF-8
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    logger.info("写入 CSV：%s（%d 行）", csv_path, len(rows))

# -----------------------
# 名称清洗（特殊字符→空格，压缩多空格）
# -----------------------

def _clean_spaces(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", " ", name)  # 非法字符替换为空格
    name = re.sub(r"\s+", " ", name).strip()     # 压缩多空格
    return name

def safe_folder_name(name: str) -> str:
    cleaned = _clean_spaces(name)
    return cleaned or "Unnamed Set"

def safe_file_name(name: str) -> str:
    cleaned = _clean_spaces(name)
    return cleaned or "Unnamed"

# -----------------------
# 竖版 2×2 拼贴（400×600，无边框）
# -----------------------

def make_collage_2x2_400x600(output_path: str, image_paths: List[str]) -> None:
    """
    竖版：画布 400x600；2x2 无边框；每格 200x300；cover 裁剪铺满（不留边）。
    """
    canvas_w, canvas_h = 400, 600
    tile_w, tile_h = 200, 300

    canvas = Image.new("RGB", (canvas_w, canvas_h), color=(0, 0, 0))

    def cover_fit(img: Image.Image, tw: int, th: int) -> Image.Image:
        iw, ih = img.size
        if iw == 0 or ih == 0:
            return Image.new("RGB", (tw, th), (0, 0, 0))
        scale = max(tw / iw, th / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        img_resized = img.resize((nw, nh), Image.LANCZOS)
        # 居中裁剪
        left = (nw - tw) // 2
        top = (nh - th) // 2
        right = left + tw
        bottom = top + th
        return img_resized.crop((left, top, right, bottom))

    # 顺序：上左、上右、下左、下右（竖版坐标）
    positions = [(0, 0), (200, 0), (0, 300), (200, 300)]

    for idx, p in enumerate(image_paths[:4]):
        with Image.open(p) as im:
            im = im.convert("RGB")
            tile = cover_fit(im, tile_w, tile_h)
            x, y = positions[idx]
            canvas.paste(tile, (x, y))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.save(output_path, "JPEG", quality=90)

def make_set_poster(set_name: str, poster_paths: List[str], collections_root: str, logger: logging.Logger) -> Optional[str]:
    """
    生成 2x2 竖版 400x600 合集海报：
    - ≥4：随机取 4 张；
    - ==2：保证两张各出现两次（A, B, A, B）；
    - <2 ：允许重复随机补足到 4 张
    - 输出：<out_root>\collections\<合集名>\auto_poster_<合集名>.jpg
    """
    # 过滤无效并去重
    uniq = []
    seen = set()
    for p in poster_paths:
        if p and os.path.isfile(p):
            ab = os.path.abspath(p)
            if ab not in seen:
                seen.add(ab)
                uniq.append(ab)
    if not uniq:
        logger.info("合集无可用海报，跳过：%s", set_name)
        return None

    # 选择要拼的 4 张（加入 ==2 的 ABAB 特殊处理）
    if len(uniq) >= 4:
        pick = random.sample(uniq, 4)
    elif len(uniq) == 3:
    # 恰好 3 张：随机取 3 张，再随机重复其中一张补满 4
        pick = random.sample(uniq, 3)
        pick.append(random.choice(pick))
        random.shuffle(pick)
    elif len(uniq) == 2:
        a, b = uniq[0], uniq[1]
        pick = [a, b, b, a]  # 或按需随机起始：if random.random()<.5: [a,b,a,b] else: [b,a,b,a]
    else:
        pick = [uniq[0]] * 4

    # 输出路径
    set_dirname = safe_folder_name(set_name)
    collections_dir = os.path.join(collections_root, "collections", set_dirname)
    out_name = f"auto_poster_{safe_file_name(set_name)}.jpg"
    out_poster = os.path.join(collections_dir, out_name)

    if HAVE_PIL:
        try:
            make_collage_2x2_400x600(out_poster, pick)
            logger.info("已生成合集拼贴海报（2x2 竖版 400x600）：%s", out_poster)
            return out_poster
        except Exception as e:
            logger.warning("拼贴失败，将回退复制最大图：%s —— %s", set_name, e)

    # 回退：复制最大一张（尺寸不保证 400x600）
    try:
        largest = max(uniq, key=lambda p: os.path.getsize(p))
        os.makedirs(os.path.dirname(out_poster), exist_ok=True)
        shutil.copyfile(largest, out_poster)
        logger.info("已生成合集海报（回退复制）：%s", out_poster)
        return out_poster
    except Exception as e:
        logger.warning("复制海报失败：%s —— %s", out_poster, e)
        return None

# -----------------------
# 主处理
# -----------------------

def process_by_videos(video_paths: List[str], logger: logging.Logger) -> Tuple[List[List[str]], List[List[str]]]:
    """
    以“视频→NFO”的方式处理，返回两份 CSV 数据：
    列：path(nfo_path), title, year, set_name, id, tmdbid, imdbid, poster_path, video_path
    """
    rec: List[List[str]] = []
    for v in video_paths:
        nfo = find_nfo_for_video(v, logger)
        if not nfo:
            continue
        try:
            txt = load_text(nfo)
            meta = parse_nfo_text(txt)
            title = meta.get("title") or ""
            year = meta.get("year") or ""
            any_id = meta.get("id") or ""
            tmdbid = meta.get("tmdbid") or ""
            imdbid = meta.get("imdbid") or ""
            set_name = meta.get("set_name") or ""

            # 以“视频”为中心找封面，避免多片集聚到同一张 poster.jpg
            poster_path = find_poster_for_video(v, logger) or ""

            rec.append([
                nfo,           # NFO 路径
                title,
                year,
                set_name,
                any_id,
                tmdbid,
                imdbid,
                poster_path,
                v,             # 视频路径
            ])
        except Exception as e:
            logger.warning("解析失败：%s  —— %s", nfo, e)

    rows_raw = rec

    def sort_key(row: List[str]):
        set_name, year, title = row[3], row[2], row[1]
        try:
            y = int(year)
        except Exception:
            y = 0
        return (set_name or "", y, title or "")

    rows_sorted = sorted(rec, key=sort_key)
    return rows_raw, rows_sorted

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="扫描媒体库：视频优先 NFO → 选择 set（过滤单片）→ 生成 CSV(UTF-8-BOM) 与竖版 2x2 合集海报（400x600）"
    )
    parser.add_argument("--root", help="扫描根目录（不提供则弹窗选择）", default=None)
    parser.add_argument("--max-depth", type=int, default=6, help="最大递归深度（默认 6）")
    parser.add_argument("--log-dir", default=os.getenv("SET_REC_LOG_DIR"), help="日志目录（可覆盖默认）")
    parser.add_argument("--out-dir", default=None, help="输出根目录（不提供则弹窗选择；最终写入 .\\collections\\合集名称）")
    parser.add_argument("--no-gui", action="store_true", help="禁用 GUI（需要提供 --root 与 --out-dir）")
    args = parser.parse_args(argv)

    logger, log_dir, log_file = setup_logging(args.log_dir)

    # 1) 扫描根目录
    scan_root = args.root
    if not scan_root:
        if args.no_gui:
            logger.error("未提供 --root 且禁用 GUI，无法选择扫描目录。")
            print("错误：未提供 --root 且禁用 GUI。")
            print(f"日志位置：{log_file}")
            return 2
        scan_root = pick_directory_gui("请选择要扫描的根目录（包含媒体文件与 NFO）")
    if not scan_root or not os.path.isdir(scan_root):
        logger.error("无效的扫描目录：%s", scan_root)
        print("错误：未选择或目录无效。")
        print(f"日志位置：{log_file}")
        return 2
    logger.info("扫描根目录：%s", scan_root)

    # 扫描视频
    t0 = time.time()
    video_files = iter_video_files(scan_root, max_depth=args.max_depth)
    logger.info("发现视频文件：%d 个", len(video_files))

    # 解析
    rows_raw, rows_sorted = process_by_videos(video_files, logger)

    # 按 set 分组统计：影片数 & 可用海报
    set_to_posters: Dict[str, List[str]] = {}
    set_to_count: Dict[str, int] = {}
    for row in rows_raw:
        sname = row[3] or ""
        if not sname:
            continue
        set_to_count[sname] = set_to_count.get(sname, 0) + 1
        poster = row[7] or ""
        if poster and os.path.isfile(poster):
            set_to_posters.setdefault(sname, []).append(os.path.abspath(poster))
        else:
            set_to_posters.setdefault(sname, [])

    # 仅保留“影片数 ≥ 2”的合集供交互选择
    eligible_sets = sorted([s for s, c in set_to_count.items() if c >= 2], key=lambda x: x.lower())
    logger.info("可选合集（影片数≥2）数量：%d（单片合集已过滤）", len(eligible_sets))

    # 2) 选择 set（GUI；无 GUI 默认全选 eligible）
    if args.no_gui:
        selected_sets = eligible_sets[:]
    else:
        selected_sets = pick_sets_gui(eligible_sets) or eligible_sets[:]
    logger.info("将处理合集：%s", ", ".join(selected_sets) if selected_sets else "(无)")

    # 3) 选择输出根目录
    out_dir = args.out_dir
    if not out_dir:
        if args.no_gui:
            logger.error("未提供 --out-dir 且禁用 GUI，无法选择输出目录。")
            print("错误：未提供 --out-dir 且禁用 GUI。")
            print(f"日志位置：{log_file}")
            return 2
        out_dir = pick_directory_gui("请选择输出根目录（最终写入 .\\collections\\合集名称）")
    if not out_dir:
        logger.error("未选择输出目录。")
        print("错误：未选择输出目录。")
        print(f"日志位置：{log_file}")
        return 2
    out_dir = ensure_writable_dir(out_dir)
    logger.info("输出根目录：%s（合集将写入其中的 .\\collections 子目录）", out_dir)

    # 写 CSV（UTF-8 with BOM）
    csv_dir = os.path.join(out_dir, "collections", "_csv")
    os.makedirs(csv_dir, exist_ok=True)
    csv1 = os.path.join(csv_dir, "set_rec.csv")
    csv2 = os.path.join(csv_dir, "set_rec_sort.csv")
    headers = ["path", "title", "year", "set_name", "id", "tmdbid", "imdbid", "poster_path", "video_path"]
    write_csv_rows(csv1, rows_raw, headers, logger)
    write_csv_rows(csv2, rows_sorted, headers, logger)

    # 生成每个选中 set 的竖版 2×2 合集 poster（400×600）
    made_count = 0
    for set_name in selected_sets:
        posters = set_to_posters.get(set_name, [])
        out_poster = make_set_poster(set_name, posters, out_dir, logger)
        if out_poster:
            made_count += 1

    elapsed = time.time() - t0
    logger.info("合集海报生成完成：%d 个；总耗时：%.2f 秒", made_count, elapsed)
    logger.info("日志文件：%s", log_file)
    logger.info("CSV 输出：%s, %s", csv1, csv2)

    print("=" * 64)
    print("处理完成：")
    print(f"  日志：{log_file}")
    print(f"  CSV ：{csv1}")
    print(f"        {csv2}")
    print(f"  合集海报根目录：{os.path.join(out_dir, 'collections')}")
    print("=" * 64)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中断。")
        sys.exit(130)

