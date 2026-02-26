# EmbyCoverBuilder (emcob) v1.09

[简体中文](#简体中文) | [English](#english)

---

## 简体中文

**EmbyCoverBuilder (emcob)** 是一个用于为 **Emby/Plex/Jellyfin** 媒体库中的电影合集生成自动海报封面的 Python 脚本工具。它通过扫描视频文件夹中的 `.nfo` 文件获取元数据，并选取已有的海报图片，智能地组合成一张 4 宫格的合集封面图，提升媒体库的视觉管理体验。

### ✨ 核心功能
*   **自动扫描与解析**：递归扫描指定目录，深度可配置，自动解析视频文件对应的 `.nfo` 文件，提取影片标题、年份、所属合集 (`set`) 等信息。
*   **智能海报发现**：为每个影片查找匹配的海报图片，支持 `poster.jpg`、`folder.jpg`、`cover.jpg` 等多种命名格式，并支持智能模糊匹配。
*   **合集识别与交互式选择**：自动识别包含 2 个或以上成员的合集，并提供图形界面 (GUI) 或文本界面 (TUI) 供用户选择需要生成封面的合集列表。
*   **自动合成封面**：
    *   使用 **Pillow (PIL)** 库（如果可用）将选中的 1-4 张独立海报智能裁剪、排列，合成为一张 400x600 像素的标准合集海报。
    *   若 Pillow 不可用，则自动回退到复制文件体积最大的一张海报作为合集封面。
*   **灵活的输出**：生成的合集海报将保存到用户指定的输出目录下的 `collections/<合集名>` 文件夹中。
*   **日志记录**：详细的运行日志会实时输出到控制台，并追加保存到根目录下的 `_J_PROCESSes.log` 文件中，便于追溯。

### 📁 输出结构
运行成功后，会在你指定的输出根目录下生成如下结构：
```
输出根目录/
└── collections/
    ├── 合集A名称/
    │   └── auto_poster_合集A名称.jpg
    ├── 合集B名称/
    │   └── auto_poster_合集B名称.jpg
    └── _csv/ (功能已注释，可启用)
        ├── set_rec.csv
        └── set_rec_sort.csv
```

### 🚀 快速开始
#### 前提条件
1.  **Python 3.x** 环境。
2.  安装可选依赖（推荐）以获得最佳功能：
    ```bash
    pip install pillow
    ```
    *   **`tkinter`**：用于图形界面 (GUI) 模式。通常在 Python 标准库中，Windows/macOS 默认包含。部分 Linux 发行版可能需要单独安装 `python3-tk` 包。
    *   **`Pillow` (PIL)**：用于高质量的图片合成。强烈建议安装。
    *   **`msvcrt`**：仅在 Windows 下用于 `--nogui` 模式下的增强文本交互界面 (TUI)。它是 Python 标准库的一部分。

#### 使用方法
脚本支持多种运行模式：

1.  **图形界面模式 (默认，推荐)**
    ```bash
    python emcob.py
    ```
    运行后，程序会依次弹出文件夹选择对话框，让你选择**媒体库扫描根目录**和**封面输出根目录**。随后扫描并列出所有可生成封面的合集，供你勾选确认。

2.  **命令行模式 (禁用图形界面)**
    ```bash
    python emcob.py --nogui
    ```
    在纯命令行环境下运行，通过文本输入指定路径，并使用键盘交互式选择合集。

3.  **全参数命令行模式**
    ```bash
    python emcob.py --nogui --input "D:\MyMedia\Movies" --output "D:\Output" --depth 4
    ```
    *   `--input`: 指定媒体库扫描的根目录路径。
    *   `--output`: 指定生成文件的输出根目录。
    *   `--depth`: 设置递归扫描的最大深度 (默认: 6)。
    *   `--log`: 指定日志文件 `_J_PROCESSes.log` 的存放目录 (可选)。
    *   `--nogui`: 强制禁用 GUI，使用命令行交互。

### 📄 脚本参数详解
| 参数 | 缩写 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| `--nogui` | 无 | `store_true` | `False` | 禁用图形用户界面，强制使用命令行交互。 |
| `--input` | 无 | `字符串` | 无 | **手动指定**要扫描的媒体库根目录的**绝对路径**。 |
| `--output` | 无 | `字符串` | 无 | **手动指定**生成文件（`collections`文件夹）的**输出根目录**。 |
| `--depth` | 无 | `整数` | `6` | 设置从根目录开始递归扫描文件夹的**最大深度**。 |
| `--log` | 无 | `字符串` | 脚本父目录 | 指定存储运行日志文件 (`_J_PROCESSes.log`) 的目录。 |

### ⚙️ 工作原理
1.  **扫描**：从输入目录开始，递归查找所有支持格式的视频文件 (如 `.mp4`, `.mkv` 等)。
2.  **解析**：为每个视频文件查找同名的 `.nfo` 文件，解析 XML 结构，提取 `title`, `year`, `set` 等关键信息。
3.  **关联海报**：在视频文件所在目录下，通过多种策略寻找匹配的海报图片文件。
4.  **分组**：根据 `set` 字段将影片分组，筛选出成员数 ≥ 2 的"有效合集"。
5.  **选择**：向用户展示"有效合集"列表，供其选择需要生成封面的合集。
6.  **生成**：对每个被选中的合集，从其成员的海报中选取最多4张，使用 Pillow 合成 2x2 网格海报，或回退到复制单张海报。
7.  **输出与记录**：将生成的封面图保存至输出目录，并记录详细日志。

### 📝 备注
*   脚本依赖于影片目录中由 **TinyMediaManager**, **Radarr** 等工具生成的 `.nfo` 文件。确保你的媒体库已正确刮削并包含 `<set>` 信息。
*   生成的合集封面默认命名为 `auto_poster_<合集名>.jpg`。
*   在 v1.09 版本中，修复了 GUI 模式下鼠标滚轮翻页失效的问题。

---

## English

**EmbyCoverBuilder (emcob)** is a Python script tool designed to automatically generate collection poster covers for movie sets in your **Emby/Plex/Jellyfin** media library. It scans `.nfo` files within video directories to retrieve metadata, selects existing poster images, and intelligently composites them into a 2x2 grid collection poster, enhancing the visual management of your library.

### ✨ Core Features
*   **Automated Scanning & Parsing**: Recursively scans a specified directory (with configurable depth) and automatically parses the associated `.nfo` files for video files, extracting information such as movie title, year, and belonging collection (`set`).
*   **Smart Poster Discovery**: Finds matching poster images for each movie, supporting various naming conventions like `poster.jpg`, `folder.jpg`, `cover.jpg`, and includes fuzzy matching logic.
*   **Collection Identification & Interactive Selection**: Automatically identifies collections with 2 or more members and provides a graphical (GUI) or text-based (TUI) interface for users to select which collections to generate covers for.
*   **Automatic Cover Composition**：
    *   Uses the **Pillow (PIL)** library (if available) to intelligently crop and arrange 1-4 selected member posters into a standard 400x600 pixel collection poster.
    *   Falls back to copying the single largest poster file if Pillow is not installed.
*   **Flexible Output**: Generated collection posters are saved to a `collections/<collection_name>` folder under the user-specified output root directory.
*   **Logging**: Detailed runtime logs are output to the console and appended to a `_J_PROCESSes.log` file in the script's parent directory for traceability.

### 📁 Output Structure
Upon successful execution, the following structure will be created under your specified output root:
```
Output_Root/
└── collections/
    ├── CollectionA_Name/
    │   └── auto_poster_CollectionA_Name.jpg
    ├── CollectionB_Name/
    │   └── auto_poster_CollectionB_Name.jpg
    └── _csv/ (feature commented out, can be enabled)
        ├── set_rec.csv
        └── set_rec_sort.csv
```

### 🚀 Quick Start
#### Prerequisites
1.  **Python 3.x** environment.
2.  Install optional dependencies (recommended) for best functionality:
    ```bash
    pip install pillow
    ```
    *   **`tkinter`**: For Graphical User Interface (GUI) mode. Usually included in the Python standard library (Windows/macOS). Some Linux distributions may require installing a separate package like `python3-tk`.
    *   **`Pillow` (PIL)**: For high-quality image composition. Highly recommended.
    *   **`msvcrt`**: Used only on Windows for the enhanced Text-based User Interface (TUI) in `--nogui` mode. Part of the Python standard library.

#### Usage
The script supports multiple run modes:

1.  **Graphical Interface Mode (Default, Recommended)**
    ```bash
    python emcob.py
    ```
    The program will pop up folder selection dialogs for you to choose the **Media Library Scan Root Directory** and the **Cover Output Root Directory**. It will then scan and list all eligible collections for you to select.

2.  **Command-Line Mode (No GUI)**
    ```bash
    python emcob.py --nogui
    ```
    Runs in a pure command-line environment. Paths are specified via text input, and collections are selected via keyboard interaction.

3.  **Full-Parameter Command-Line Mode**
    ```bash
    python emcob.py --nogui --input "D:\MyMedia\Movies" --output "D:\Output" --depth 4
    ```
    *   `--input`: Specifies the absolute path to the root directory of your media library for scanning.
    *   `--output`: Specifies the root directory for generated files.
    *   `--depth`: Sets the maximum recursion depth for scanning (default: 6).
    *   `--log`: Specifies the directory for the log file `_J_PROCESSes.log` (optional).
    *   `--nogui`: Force disables the GUI, using command-line interaction instead.

### 📄 Script Arguments Details
| Argument | Short | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `--nogui` | None | `store_true` | `False` | Disable the Graphical User Interface, force command-line interaction. |
| `--input` | None | `string` | None | **Manually specify** the **absolute path** to the media library root directory to scan. |
| `--output` | None | `string` | None | **Manually specify** the **root directory** for output files (the `collections` folder). |
| `--depth` | None | `integer` | `6` | Set the **maximum depth** for recursive folder scanning from the root. |
| `--log` | None | `string` | Script's parent dir | Specify the directory to store the runtime log file (`_J_PROCESSes.log`). |

### ⚙️ How It Works
1.  **Scan**: Starts from the input directory, recursively finding all video files of supported formats (e.g., `.mp4`, `.mkv`).
2.  **Parse**: For each video file, looks for a corresponding `.nfo` file, parses its XML structure, and extracts key info like `title`, `year`, `set`.
3.  **Associate Poster**: Searches the video file's directory using multiple strategies to find a matching poster image file.
4.  **Group**: Groups movies by their `set` field, filtering for "eligible collections" with ≥ 2 members.
5.  **Select**: Presents the list of "eligible collections" to the user for selection.
6.  **Generate**: For each selected collection, picks up to 4 member posters, composites them into a 2x2 grid poster using Pillow, or falls back to copying a single poster.
7.  **Output & Log**: Saves the generated cover to the output directory and records detailed logs.

### 📝 Notes
*   The script relies on `.nfo` files generated by tools like **TinyMediaManager** or **Radarr** in your movie directories. Ensure your media library is properly scraped and contains `<set>` information.
*   Generated collection posters are named `auto_poster_<collection_name>.jpg` by default.
*   Version v1.09 fixed an issue where the mouse wheel scrolling failed in the GUI mode.
