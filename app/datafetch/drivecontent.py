import os
import re
import shutil
import tempfile
import zipfile

import gdown

from pathlib import Path
from pypdf import PdfReader
from docx import Document
from openpyxl import load_workbook


# ============================================================
# CONFIGURATION
# ============================================================

# Maximum size of one file that will be processed
MAX_FILE_SIZE = 5 * 1024 * 1024


# ============================================================
# ALLOWED FILE EXTENSIONS
# ============================================================

ALLOWED_EXTENSIONS = {
    # JavaScript
    ".js", ".jsx", ".mjs", ".cjs",

    # TypeScript
    ".ts", ".tsx",

    # Web
    ".html", ".htm", ".css", ".scss", ".sass", ".less",

    # Data
    ".json", ".xml", ".yaml", ".yml", ".csv",

    # Python
    ".py",

    # PHP
    ".php",

    # C / C++
    ".c", ".h", ".cpp", ".hpp",

    # Java
    ".java",

    # C#
    ".cs",

    # Go
    ".go",

    # Rust
    ".rs",

    # SQL
    ".sql",

    # Markdown / text
    ".md", ".txt",

    # Vue / Svelte
    ".vue", ".svelte",

    # Documents
    ".pdf", ".docx",

    # Excel
    ".xlsx",
}


# ============================================================
# IGNORED DIRECTORIES
# ============================================================

IGNORED_DIRECTORIES = {
    "node_modules", ".git", "dist", "build", "out", "__pycache__",
    ".next", ".nuxt", "venv", ".venv", "env", ".env", "coverage",
    ".cache", ".parcel-cache", ".turbo", ".vercel", "target",
    "vendor", "bin", "obj",
}


# ============================================================
# IGNORED FILES
# ============================================================

IGNORED_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "composer.lock",
    "poetry.lock",
}


# ============================================================
# TEXT ENCODINGS
# ============================================================

TEXT_EXTENSIONS = {
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".html", ".htm",
    ".css", ".scss", ".sass", ".less", ".json", ".xml", ".yaml",
    ".yml", ".csv", ".py", ".php", ".c", ".h", ".cpp", ".hpp",
    ".java", ".cs", ".go", ".rs", ".sql", ".md", ".txt", ".vue",
    ".svelte",
}


# ============================================================
# EXTRACT GOOGLE DRIVE ID
# ============================================================

def extract_drive_id(url: str) -> str:
    """
    Extract Google Drive file/folder ID from common URLs.

    Supported examples:
    https://drive.google.com/file/d/FILE_ID/view
    https://drive.google.com/drive/folders/FOLDER_ID
    https://drive.google.com/open?id=FILE_ID
    https://drive.google.com/uc?id=FILE_ID
    """

    url = url.strip()

    match = re.search(r"/file/d/([^/]+)", url)
    if match:
        return match.group(1)

    match = re.search(r"/folders/([^/?]+)", url)
    if match:
        return match.group(1)

    match = re.search(r"[?&]id=([^&]+)", url)
    if match:
        return match.group(1)

    raise ValueError(
        "Invalid Google Drive URL. Could not extract file/folder ID."
    )


# ============================================================
# CHECK IGNORED PATH
# ============================================================

def should_ignore_path(path: Path) -> bool:

    for part in path.parts:
        if part in IGNORED_DIRECTORIES:
            return True

    filename = path.name.lower()
    if filename in IGNORED_FILES:
        return True

    return False


# ============================================================
# CHECK ALLOWED FILE
# ============================================================

def is_allowed_file(path: Path) -> bool:

    if should_ignore_path(path):
        return False

    extension = path.suffix.lower()
    return extension in ALLOWED_EXTENSIONS


# ============================================================
# CHECK FILE SIZE
# ============================================================

def is_file_size_allowed(path: Path) -> bool:

    try:
        size = path.stat().st_size
    except OSError:
        return False

    if size > MAX_FILE_SIZE:
        print(f"Skipping large file: {path.name} ({size / 1024:.1f} KB)")
        return False

    return True


# ============================================================
# READ TEXT FILE
# ============================================================

def read_text_file(path: Path) -> str:

    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as error:
        print(f"Text read error: {path} -> {error}")
        return ""


# ============================================================
# READ PDF
# ============================================================

def read_pdf_file(path: Path) -> str:

    try:
        reader = PdfReader(str(path))
        pages = []

        for page_number, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
                if text:
                    pages.append(f"\n--- PAGE {page_number + 1} ---\n{text}")
            except Exception as error:
                print(f"PDF page error: {path} page={page_number + 1} -> {error}")

        return "\n".join(pages)

    except Exception as error:
        print(f"PDF read error: {path} -> {error}")
        return ""


# ============================================================
# READ DOCX
# ============================================================

def read_docx_file(path: Path) -> str:

    try:
        document = Document(str(path))
        content = []

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                content.append(text)

        for table in document.tables:
            content.append("\n--- TABLE ---")
            for row in table.rows:
                row_data = [cell.text.strip() for cell in row.cells]
                content.append(" | ".join(row_data))

        return "\n".join(content)

    except Exception as error:
        print(f"DOCX read error: {path} -> {error}")
        return ""


# ============================================================
# READ XLSX
# ============================================================

def read_xlsx_file(path: Path) -> str:

    try:
        workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
        content = []

        for worksheet in workbook.worksheets:
            content.append(f"\n--- SHEET: {worksheet.title} ---")

            for row in worksheet.iter_rows(values_only=True):
                values = [("" if value is None else str(value)) for value in row]
                if any(values):
                    content.append(" | ".join(values))

        workbook.close()
        return "\n".join(content)

    except Exception as error:
        print(f"XLSX read error: {path} -> {error}")
        return ""


# ============================================================
# READ SINGLE FILE (dispatcher)
# ============================================================

def extract_file_content(path: Path) -> str:

    extension = path.suffix.lower()

    if extension in TEXT_EXTENSIONS:
        return read_text_file(path)

    if extension == ".pdf":
        return read_pdf_file(path)

    if extension == ".docx":
        return read_docx_file(path)

    if extension == ".xlsx":
        return read_xlsx_file(path)

    return ""


# ============================================================
# SAFE ZIP EXTRACTION
# ============================================================

def safe_extract_zip(zip_path: Path, destination: Path):

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:

            for member in zip_ref.infolist():

                member_path = destination / member.filename
                resolved_destination = destination.resolve()
                resolved_member = member_path.resolve()

                if not str(resolved_member).startswith(str(resolved_destination)):
                    print(f"Skipping unsafe ZIP path: {member.filename}")
                    continue

                zip_ref.extract(member, destination)

        return True

    except zipfile.BadZipFile:
        print(f"Invalid ZIP file: {zip_path}")
        return False

    except Exception as error:
        print(f"ZIP extraction error: {zip_path} -> {error}")
        return False


# ============================================================
# DOWNLOAD GOOGLE DRIVE
# ============================================================

def download_drive_content(drive_url: str, destination: Path):

    print("\nDownloading from Google Drive...")
    print(f"URL: {drive_url}")

    # --------------------------------------------------------
    # Folder download
    # --------------------------------------------------------
    if "/folders/" in drive_url:
        try:
            result = gdown.download_folder(
                url=drive_url,
                output=str(destination),
                quiet=False,
                use_cookies=False
            )
            if result:
                return True
        except Exception as error:
            print(f"Folder download failed: {error}")

    # --------------------------------------------------------
    # Single file
    # FIX: trailing slash so gdown keeps the ORIGINAL filename
    # and extension (previously it saved as "downloaded_file"
    # with no extension, which is_allowed_file() always rejects)
    #
    # FIX 2: old gdown versions don't accept the `fuzzy` kwarg at
    # all (raises TypeError). Try the modern call first, and if
    # that specific TypeError happens, fall back to building a
    # direct "uc?id=..." URL manually (works on old gdown too).
    # --------------------------------------------------------
    try:
        result = gdown.download(
            url=drive_url,
            output=str(destination) + os.sep,
            quiet=False,
            fuzzy=True
        )
        if result:
            return True

    except TypeError as error:

        if "fuzzy" not in str(error):
            print(f"File download failed: {error}")
            return False

        print("Old gdown version detected (no 'fuzzy' support). "
              "Retrying with direct id-based URL...")

        try:
            file_id = extract_drive_id(drive_url)
            direct_url = f"https://drive.google.com/uc?id={file_id}"

            result = gdown.download(
                url=direct_url,
                output=str(destination) + os.sep,
                quiet=False
            )
            if result:
                return True

        except Exception as fallback_error:
            print(f"Fallback download failed: {fallback_error}")
            return False

    except Exception as error:
        print(f"File download failed: {error}")

    return False


# ============================================================
# FIND DOWNLOADED FILES
# ============================================================

def get_files_from_directory(directory: Path):

    files = []

    for path in directory.rglob("*"):

        if not path.is_file():
            continue

        if should_ignore_path(path):
            continue

        # ZIP files are handled separately
        if path.suffix.lower() == ".zip":
            files.append(path)
            continue

        if not is_allowed_file(path):
            continue

        if not is_file_size_allowed(path):
            continue

        files.append(path)

    return files


# ============================================================
# PROCESS ZIP
# ============================================================

def process_zip_file(zip_path: Path, temp_directory: Path):

    print(f"\nProcessing ZIP: {zip_path.name}")

    extract_directory = temp_directory / f"zip_{zip_path.stem}"
    extract_directory.mkdir(parents=True, exist_ok=True)

    success = safe_extract_zip(zip_path, extract_directory)

    if not success:
        return []

    return get_files_from_directory(extract_directory)


# ============================================================
# COLLECT + DEDUPE ALL FILES (download + zip-extract + dedupe)
# ============================================================

def _collect_unique_files(drive_url: str, temp_directory: Path):

    success = download_drive_content(
        drive_url=drive_url,
        destination=temp_directory
    )

    if not success:
        print("Could not download Drive content.")
        return []

    downloaded_files = get_files_from_directory(temp_directory)

    all_files = []
    for path in downloaded_files:
        if path.suffix.lower() == ".zip":
            all_files.extend(process_zip_file(path, temp_directory))
        else:
            all_files.append(path)

    unique_files = []
    seen = set()
    for path in all_files:
        absolute_path = str(path.resolve())
        if absolute_path in seen:
            continue
        seen.add(absolute_path)
        unique_files.append(path)

    print(f"\nRelevant files: {len(unique_files)}")
    return unique_files


# ============================================================
# GENERATOR: return each file's content ONE BY ONE
# (This is the one to use inside an agent loop)
# ============================================================

def driveans_stream(drive_url: str):
    """
    Generator that downloads a Google Drive file/folder and yields
    ONE FILE AT A TIME as a dict, instead of one big joined string.

    Usage inside an agent:

        for file_data in driveans_stream(drive_url):
            filename = file_data["filename"]
            content  = file_data["content"]
            # ... feed one file at a time to your agent/LLM call ...

    Yields:
        {
            "filename": str,   # e.g. "main.py"
            "path": str,       # full path in temp dir (deleted after generator ends)
            "extension": str,  # e.g. ".py"
            "content": str,    # extracted text content
        }
    """

    # Validate URL early (raises if invalid)
    drive_id = extract_drive_id(drive_url)
    print(f"Drive ID: {drive_id}")

    temp_directory = Path(tempfile.mkdtemp(prefix="assignment_drive_"))

    try:
        print("\n==============================")
        print("GOOGLE DRIVE FETCH (stream)")
        print("==============================")

        unique_files = _collect_unique_files(drive_url, temp_directory)

        for path in unique_files:
            print(f"Reading: {path}")

            content = extract_file_content(path)

            if not content.strip():
                print(f"Empty/unreadable file: {path}")
                continue

            yield {
                "filename": path.name,
                "path": str(path),
                "extension": path.suffix.lower(),
                "content": content,
            }

    except Exception as error:
        print(f"Drive processing error: {error}")

    finally:
        # Cleanup happens only after the generator is fully consumed
        # (or closed/garbage-collected). If you need files to persist
        # longer, copy them out inside the loop before this runs.
        try:
            shutil.rmtree(temp_directory, ignore_errors=True)
        except Exception:
            pass


# ============================================================
# BATCH VERSION (old behaviour, kept for backwards compatibility)
# Returns everything joined into one big string.
# ============================================================

def driveans(drive_url: str) -> str:
    """
    Non-streaming version. Collects all files and returns one
    combined string (old behaviour). Prefer driveans_stream()
    for agents that process file-by-file.
    """

    parts = []

    try:
        for file_data in driveans_stream(drive_url):
            parts.append(
                f"""
============================================================
FILE: {file_data['filename']}
============================================================

{file_data['content']}

"""
            )
    except Exception as error:
        print(f"Google Drive Error: {error}")
        return ""

    result = "\n".join(parts)
    print(f"\nTotal characters: {len(result)}")
    return result


# ============================================================
# EXAMPLE USAGE
# ============================================================




def drivecontent(url: str) -> str:
    
    parts = []

    for file_data in driveans_stream(url):
        filename = file_data["filename"]
        content = file_data["content"]

        print(f"Processing: {filename}")

        parts.append(
            f"--- FILE: {filename} ---\n{content}\n"
        )

    if not parts:
        return "No readable files found at this Google Drive link."

    return "\n".join(parts)





# link="https://drive.google.com/drive/folders/1wgSG_yFlRDxzNtsLYUS2Aw3n__LjlVLt"
# ans=drivecontent(link)


# print(ans)