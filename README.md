# Emby Collections Cover Builder

## Overview

This is a Python script tool designed to scan media libraries and automatically generate collection posters. It analyzes NFO metadata of video files, identifies films belonging to the same collection, and creates professional vertical 2×2 collage posters (400×600 pixels).
The initial development was motivated by Emby's inconsistent ability to generate collection posters for media libraries scraped using [JavSP](https://github.com/Yuukiy/JavSP/).

## Key Features

1. **Automatic Media Library Scanning** - Recursively scans video files in specified directories
2. **NFO Metadata Parsing** - Extracts film titles, release years, collection information, etc.
3. **Smart Poster Detection** - Multiple strategies to find corresponding poster images for each video
4. **Collection Identification & Grouping** - Automatically identifies films belonging to the same collection
5. **Professional Poster Generation** - Creates 2×2 vertical collage posters (400×600 pixels)
6. **CSV Report Generation** - Outputs detailed scan results (UTF-8-BOM encoded, Excel-friendly)

## Usage Instructions

### Basic Usage (GUI Mode)

1. Run the script directly (no parameters required):
python main.py


2. Follow the prompts to select:
- Media library root directory (containing video and NFO files)
- Collections to process (only shows collections with 2+ films)
- Output root directory (results will be saved in the collections subfolder)

### Command Line Mode
python main.py --root <media_library_path> --out-dir <output_path> --no-gui

Optional parameters:
- `--root`: Specify media library root directory
- `--max-depth`: Set scan depth (default: 6 levels)
- `--out-dir`: Specify output directory
- `--log-dir`: Specify log directory
- `--no-gui`: Disable GUI interface (requires both --root and --out-dir parameters)

## Output Results Description

### 1. CSV Report Files

Two CSV files are generated in the output directory's `collections/_csv/` subfolder:

- `set_rec.csv` - Raw scan data
- `set_rec_sort.csv` - Data sorted by collection name, year, and title

CSV columns include:
- path: NFO file path
- title: Film title
- year: Release year
- set_name: Collection name
- id: Film ID
- tmdbid: TMDB ID
- imdbid: IMDB ID
- poster_path: Found poster path
- video_path: Video file path

### 2. Collection Posters

Generated in the output directory's `collections/<collection_name>/` subfolder:

- `auto_poster_<collection_name>.jpg` - 2×2 vertical collage poster (400×600 pixels)

**Poster Generation Rules**:
- ≥4 films: Randomly select 4 different posters
- 3 films: Randomly select 3 posters, one of which is repeated
- 2 films: Use ABAB pattern arrangement (A,B,A,B)
- <2 films: Single poster repeated 4 times

### 3. Log Files

`set_rec.log` is generated in the log directory, recording detailed processing progress and any error messages.

## Technical Requirements

- Python 3.6+
- Recommended to install Pillow library for optimal poster generation:
pip install pillow

- Without Pillow, the tool will fall back to copying the largest poster file (size not guaranteed to be 400×600)

## Important Notes

1. NFO file support: Prefers `<video_filename>.nfo`, falls back to `movie.nfo` if not found
2. Collection identification: Supports `<set>` tags, prioritizes extracting `<name>` sub-tag content
3. Poster detection strategy (in order of priority):
 - Same-name image files
 - Preset names (poster.jpg, folder.jpg, etc.)
 - Images containing video name keywords
 - Images with "poster" in the filename
 - Largest image file in the directory
4. Invalid filename handling: Automatically replaces illegal characters with spaces and compresses consecutive spaces

## Application Scenarios

- Collection management for media servers (Only Emby tested, Plex, Jellyfin, etc should work but no guarantee .)
- Batch organization of series films in media libraries
- Creating unified cover posters for movie collections

- Media library metadata analysis and export


