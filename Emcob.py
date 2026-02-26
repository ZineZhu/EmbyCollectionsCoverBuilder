import os
import re
import sys
import csv
import time
import random
import logging
import argparse
import shutil
import io
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

# 版本定义
VERSION = "v1.11"

# 尝试导入 GUI 相关库
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None

# 尝试导入图像处理库
try:
    from PIL import Image
except ImportError:
    Image = None

# Windows 环境下的按键监听 (用于 TUI)
try:
    import msvcrt
except ImportError:
    msvcrt = None

class EmbyCoverBuilder:
    def __init__(self):
        self.args = self.parse_args()
        self.log_stream = io.StringIO() # 用于捕获本次运行的日志
        self.setup_logging()
        self.video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.ts', '.m4v')
        self.image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
        self.records = []
        self.selected_sets = []

    def parse_args(self):
        example_text = f'''
示例:
  python %(prog)s --input "D:\\Movies" --output "E:\\Posters"
  python %(prog)s --nogui --input "\\\\192.168.1.10\\Share" --depth 4
        '''
        parser = argparse.ArgumentParser(
            description=f"EmbyCoverBuilder (emcob) {VERSION} - 合集海报生成工具",
            epilog=example_text,
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        parser.add_argument('--nogui', action='store_true', help="禁用GUI交互模式")
        parser.add_argument('--input', type=str, help="指定扫描根目录路径")
        parser.add_argument('--output', type=str, help="指定输出根目录")
        parser.add_argument('--depth', type=int, default=6, help="最大递归深度 (默认: 6)")
        parser.add_argument('--log', type=str, help="指定日志目录")
        return parser.parse_args()

    def setup_logging(self):
        """初始化日志系统"""
        if self.args.log:
            log_dir = Path(self.args.log)
        else:
            log_dir = Path(sys.argv[0]).parent.parent
        
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / "_J_PROCESSes.log"
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        stream_handler = logging.StreamHandler(self.log_stream)
        stream_handler.setFormatter(formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        self.logger = logging.getLogger("emcob")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(stream_handler)
        self.logger.addHandler(console_handler)

    def finalize_logging(self):
        """将内存中的新日志写入到文件最前端"""
        new_logs = self.log_stream.getvalue()
        if not new_logs: return

        header = f"[合集封面_{datetime.now().strftime('%Y%m%d%H%M%S')}]\n"
        
        existing_content = ""
        if self.log_path.exists():
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
            except: pass

        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write(new_logs)
            if existing_content:
                f.write("\n")
            f.write(existing_content)

    def get_input_dir(self):
        if self.args.input:
            return Path(self.args.input)
        
        if self.args.nogui:
            path = input("请选择要扫描的根目录路径: ").strip()
            if path: return Path(path)
        elif tk:
            root = tk.Tk()
            root.withdraw()
            path = filedialog.askdirectory(title="请选择要扫描的根目录")
            root.destroy()
            if path: return Path(path)
        
        print("错误: 未指定输入目录。")
        sys.exit(2)

    @lru_cache(maxsize=256)
    def parse_nfo_text(self, nfo_path):
        try:
            with open(nfo_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            def extract(tag, text):
                match = re.search(f'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
                if match:
                    res = re.sub('<[^<]+?>', '', match.group(1))
                    return " ".join(res.split())
                return ""

            title = extract('title', content)
            year = extract('year', content)
            any_id = extract('id', content)
            tmdbid = extract('tmdbid', content)
            imdbid = extract('imdbid', content)
            
            set_match = re.search(r'<set>.*<name>(.*?)</name>.*</set>', content, re.DOTALL)
            if not set_match:
                set_match = re.search(r'<set>(.*?)</set>', content, re.DOTALL)
            
            set_name = ""
            if set_match:
                set_name = re.sub('<[^<]+?>', '', set_match.group(1)).strip()
                set_name = " ".join(set_name.split())

            return title, year, set_name, any_id, tmdbid, imdbid
        except Exception:
            return "", "", "", "", "", ""

    def find_poster(self, video_path):
        dir_path = video_path.parent
        base_name = video_path.stem
        for ext in self.image_extensions:
            p = dir_path / f"{base_name}{ext}"
            if p.exists(): return p
        presets = ['poster', 'folder', 'cover']
        for pre in presets:
            for ext in self.image_extensions:
                p = dir_path / f"{pre}{ext}"
                if p.exists(): return p
        clean_name = re.sub(r'(-zh|_zh|1080p|720p|4k|bluray).*', '', base_name, flags=re.IGNORECASE).strip()
        
        try:
            for entry in os.scandir(dir_path):
                if entry.is_file() and any(entry.name.lower().endswith(ext) for ext in self.image_extensions):
                    if clean_name.lower() in entry.name.lower():
                        return Path(entry.path)
        except: pass
        return None

    def _worker_process_single_video(self, v_path):
        nfo_path = v_path.with_suffix('.nfo')
        if not nfo_path.exists():
            nfo_path = v_path.parent / "movie.nfo"
        if not nfo_path.exists():
            return None
        
        title, year, set_name, any_id, tmdbid, imdbid = self.parse_nfo_text(nfo_path)
        poster_path = self.find_poster(v_path)
        
        return [str(nfo_path), title, year, set_name, any_id, tmdbid, imdbid, 
                str(poster_path) if poster_path else "", str(v_path)]

    def scan_and_process(self, root_dir, executor):
        futures = []
        found_count = 0
        
        # v1.11 修改：增强 UNC 路径处理与存在性校验
        root_path = os.path.normpath(str(root_dir))
        
        if not os.path.exists(root_path):
            self.logger.error(f"路径不存在或无法访问: {root_path}")
            self.logger.error("请检查网络连接或 Windows 凭据管理器中的共享权限。")
            return []

        for root, dirs, files in os.walk(root_path):
            rel_path = os.path.relpath(root, root_path)
            depth = 0 if rel_path == "." else len(rel_path.split(os.sep))
            
            if depth > self.args.depth:
                dirs[:] = []
                continue

            dir_name = os.path.basename(root)
            if len(dir_name) > 50: dir_name = dir_name[:47] + "..."
            sys.stdout.write(f"\r当前扫描目录：{dir_name}".ljust(75))
            sys.stdout.flush()

            for file in files:
                if any(file.lower().endswith(ext) for ext in self.video_extensions):
                    v_path = Path(root) / file
                    futures.append(executor.submit(self._worker_process_single_video, v_path))
                    found_count += 1
        
        print("\r" + " " * 75 + "\r", end="") 
        self.logger.info(f"扫描完成，已提交 {found_count} 个解析任务。")
        return futures

    def collect_results(self, futures):
        raw_data = []
        total = len(futures)
        if total == 0: return []

        for i, future in enumerate(as_completed(futures), 1):
            res = future.result()
            if res:
                raw_data.append(res)
            sys.stdout.write(f"\r正在解析元数据：{i}/{total} ({(i/total)*100:.1f}%)".ljust(75))
            sys.stdout.flush()

        print("\r" + " " * 75 + "\r", end="") 
        self.records = sorted(raw_data, key=lambda x: (x[3] or "zzz", x[2] or "9999", x[1] or ""))
        return self.records

    def get_eligible_sets(self):
        set_counts = {}
        set_posters = {}
        for r in self.records:
            s_name = r[3]
            if not s_name: continue
            set_counts[s_name] = set_counts.get(s_name, 0) + 1
            if r[7]:
                if s_name not in set_posters: set_posters[s_name] = []
                set_posters[s_name].append(r[7])
        eligible = [s for s, count in set_counts.items() if count >= 2]
        return eligible, set_posters

    def nogui_select_tui(self, options):
        if not msvcrt: 
            print("\n发现合集列表:")
            for i, name in enumerate(options): print(f"[{i}] {name}")
            return options 

        display_options = ["全选", "取消全选"] + options
        selected = [False] * len(display_options)
        cursor = 0
        
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"--- 合集选择 {VERSION} (上下键移动, 空格选择, 回车确认) ---")
            for i, name in enumerate(display_options):
                mark = "x" if selected[i] else " "
                pointer = " > " if i == cursor else "   "
                if i < 2:
                    print(f"{pointer}[ ] {name}")
                else:
                    print(f"{pointer}[{mark}] {name}")
            
            key = msvcrt.getch()
            if key == b'\r': 
                print("\n再次回车确认生成封面")
                if msvcrt.getch() == b'\r': 
                    break
            elif key == b' ': 
                if cursor == 0: 
                    for i in range(2, len(selected)): selected[i] = True
                elif cursor == 1: 
                    for i in range(2, len(selected)): selected[i] = False
                else: 
                    selected[cursor] = not selected[cursor]
            elif key == b'\x1b': 
                print("\n操作已取消。")
                sys.exit(2)
            elif key == b'\xe0': 
                sub_key = msvcrt.getch()
                if sub_key == b'H': cursor = (cursor - 1) % len(display_options) 
                elif sub_key == b'P': cursor = (cursor + 1) % len(display_options) 
            elif key == b'\x03': 
                raise KeyboardInterrupt
        
        res = [display_options[i] for i, s in enumerate(selected) if s and i >= 2]
        return res if res else options

    def interactive_select_sets(self, eligible_sets):
        if not eligible_sets: return []

        if self.args.nogui:
            return self.nogui_select_tui(eligible_sets)
        else:
            selected = []
            root = tk.Tk()
            root.title(f"选择要生成的合集海报 - {VERSION}")
            root.geometry("450x550")

            vars = []
            all_var = tk.BooleanVar(value=False) 

            def toggle_all():
                for _, v in vars: v.set(all_var.get())

            top_frame = ttk.Frame(root)
            top_frame.pack(fill="x", padx=10, pady=5)
            tk.Checkbutton(top_frame, text="全选 / 取消全选", variable=all_var, command=toggle_all, font=('Helvetica', 10, 'bold')).pack(side="left")

            canvas = tk.Canvas(root)
            scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)
            scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            def _on_mousewheel(event):
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            
            root.bind_all("<MouseWheel>", _on_mousewheel)

            for item in eligible_sets:
                var = tk.BooleanVar(value=False) 
                vars.append((item, var))
                tk.Checkbutton(scrollable_frame, text=item, variable=var).pack(anchor='w', padx=10)

            def on_confirm():
                nonlocal selected
                selected = [name for name, var in vars if var.get()]
                root.unbind_all("<MouseWheel>")
                root.destroy()

            def on_cancel():
                root.unbind_all("<MouseWheel>")
                root.destroy()
                print("用户取消操作，程序终止。")
                sys.exit(2)

            btn_frame = ttk.Frame(root)
            btn_frame.pack(side="bottom", fill="x", pady=10)
            tk.Button(btn_frame, text=" 确认生成 ", command=on_confirm, bg="#0078d7", fg="white", width=12).pack(side="left", padx=50)
            tk.Button(btn_frame, text=" 取消 ", command=on_cancel, width=12).pack(side="right", padx=50)
            
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            root.mainloop()
            return selected if selected else eligible_sets

    def make_set_poster(self, set_name, posters, output_root):
        clean_name = re.sub(r'[\\/:*?"<>|]', ' ', set_name)
        clean_name = " ".join(clean_name.split())
        save_dir = Path(output_root) / "collections" / clean_name
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"auto_poster_{clean_name}.jpg"

        uniq = list(dict.fromkeys([p for p in posters if p and Path(p).exists()]))
        if not uniq: return False

        count = len(uniq)
        if count >= 4: pick = random.sample(uniq, 4)
        elif count == 3:
            pick = uniq[:]
            pick.append(random.choice(uniq))
            random.shuffle(pick)
        elif count == 2: pick = [uniq[0], uniq[1], uniq[1], uniq[0]]
        else: pick = [uniq[0]] * 4

        if Image:
            try:
                canvas = Image.new('RGB', (400, 600), (0, 0, 0))
                positions = [(0, 0), (200, 0), (0, 300), (200, 300)]
                for img_path, pos in zip(pick, positions):
                    with Image.open(img_path) as img:
                        img = img.convert('RGB')
                        target_w, target_h = 200, 300
                        img_ratio = img.width / img.height
                        target_ratio = target_w / target_h
                        if img_ratio > target_ratio:
                            h = target_h
                            w = int(h * img_ratio)
                        else:
                            w = target_w
                            h = int(w / img_ratio)
                        img = img.resize((w, h), Image.Resampling.LANCZOS)
                        left = (w - target_w) / 2
                        top = (h - target_h) / 2
                        img = img.crop((left, top, left + target_w, top + target_h))
                        canvas.paste(img, pos)
                canvas.save(save_path, "JPEG", quality=90)
                self.logger.info(f"已生成海报: {clean_name}")
                return True
            except Exception as e:
                self.logger.error(f"Pillow 生成失败 {set_name}: {e}")
        
        try:
            best_img = max(uniq, key=lambda p: Path(p).stat().st_size)
            shutil.copy2(best_img, save_path)
            return True
        except: return False

    def run(self):
        print(f"\nEmbyCoverBuilder (emcob) {VERSION}")
        print("="*30)
        
        start_time = time.time()
        input_dir = self.get_input_dir()
        
        if self.args.output:
            output_dir = Path(self.args.output)
        elif self.args.nogui:
            output_dir = Path(input("请选择输出根目录路径: ").strip())
        elif tk:
            root = tk.Tk()
            root.withdraw()
            output_dir = Path(filedialog.askdirectory(title="请选择输出根目录"))
            root.destroy()
        
        if not output_dir or not os.access(output_dir, os.W_OK):
            if not self.args.nogui and tk: messagebox.showerror("错误", "输出目录无法写入")
            else: print("错误: 输出目录无法写入")
            sys.exit(2)

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = self.scan_and_process(input_dir, executor)
            self.collect_results(futures)
        
        csv_dir = output_dir / "collections" / "_csv"
        if False:
            csv_dir.mkdir(parents=True, exist_ok=True)
            
        headers = ['path', 'title', 'year', 'set_name', 'id', 'tmdbid', 'imdbid', 'poster_path', 'video_path']
        csv1, csv2 = csv_dir / "set_rec.csv", csv_dir / "set_rec_sort.csv"
        
        if False: 
            with open(csv1, 'w', encoding='utf-8-sig', newline='') as f:
                csv.writer(f).writerow(headers); csv.writer(f).writerows(self.records)
            with open(csv2, 'w', encoding='utf-8-sig', newline='') as f:
                csv.writer(f).writerow(headers); csv.writer(f).writerows(self.records)

        eligible_sets, set_posters = self.get_eligible_sets()
        selected = self.interactive_select_sets(eligible_sets)
        
        success_count = 0
        for s_name in selected:
            if self.make_set_poster(s_name, set_posters[s_name], output_dir):
                success_count += 1
        
        self.logger.info(f"任务完成。共生成 {success_count} 个合集封面。总耗时: {time.time()-start_time:.2f}s")
        self.finalize_logging() 

        print("\n" + "="*50)
        print(f"脚本版本: {VERSION}")
        print(f"日志路径: {self.log_path}")
        print(f"输出目录: {output_dir / 'collections'}")
        print("="*50)
        sys.exit(0)

if __name__ == "__main__":
    try:
        app = EmbyCoverBuilder()
        app.run()
    except KeyboardInterrupt:
        print("\n\n检测到用户中断 (Ctrl+C)，程序已终止。")
        sys.exit(130)