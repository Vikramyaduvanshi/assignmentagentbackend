

import io
import os
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlparse

import requests

# .env file support (optional): pip install python-dotenv

token=os.getenv("token")

# ============================================================
# CONFIGURATION
# ============================================================

GITHUB_API = "https://api.github.com"

# FIX 1: Token environment variable se aayega (code me hardcode nahi)
GITHUB_TOKEN = token

# Files that are useful for assignment evaluation
ALLOWED_EXTENSIONS = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".json",
    ".py",
    ".php",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".java",
    ".sql",
    ".md",
    ".txt",
    ".vue",
    ".svelte"
}


# ============================================================
# DIRECTORIES TO IGNORE
# ============================================================

IGNORED_DIRECTORIES = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "out",
    "__pycache__",
    ".next",
    ".nuxt",
    "venv",
    ".venv",
    "env",
    ".env",
    "coverage",
    ".cache",
    ".parcel-cache",
    ".turbo",
    ".vercel",
    "target",
    "vendor",
    "bin",
    "obj"
}


# ============================================================
# GENERATED / UNNECESSARY FILES TO IGNORE
# ============================================================

IGNORED_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "composer.lock",
}


# ============================================================
# MAXIMUM FILE SIZE
# ============================================================

# 500 KB per file
MAX_FILE_SIZE = 500 * 1024


# ============================================================
# GITHUB SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "Assignment-Evaluator"
})

# FIX 1: Token ho to Authorization header lagao (60 -> 5000 req/hour)
if GITHUB_TOKEN:
    session.headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
else:
    print(
        "WARNING: GITHUB_TOKEN not found. "
        "Unauthenticated limit (60/hour) lagega."
    )


# ============================================================
# PARSE GITHUB URL
# ============================================================

def parse_github_url(github_url):

    github_url = github_url.strip().rstrip("/")

    parsed = urlparse(github_url)

    if parsed.netloc.lower() != "github.com":
        raise ValueError(
            "Only GitHub URLs are supported."
        )

    parts = [
        part
        for part in parsed.path.strip("/").split("/")
        if part
    ]

    if len(parts) < 2:
        raise ValueError(
            "Invalid GitHub repository URL."
        )

    owner = parts[0]

    repo = parts[1]

    # Remove .git
    if repo.endswith(".git"):
        repo = repo[:-4]

    return owner, repo


# ============================================================
# CHECK IGNORED PATH
# ============================================================

def should_ignore_path(path):

    path_obj = PurePosixPath(path)

    # --------------------------------------------------------
    # Check directories
    # --------------------------------------------------------

    for part in path_obj.parts:

        if part in IGNORED_DIRECTORIES:
            return True

    # --------------------------------------------------------
    # Check filename
    # --------------------------------------------------------

    filename = path_obj.name.lower()

    if filename in IGNORED_FILES:
        return True

    return False


# ============================================================
# CHECK ALLOWED FILE
# ============================================================

def is_allowed_file(path):

    if should_ignore_path(path):
        return False

    filename = path.lower()

    return any(
        filename.endswith(extension)
        for extension in ALLOWED_EXTENSIONS
    )


# ============================================================
# GET REPOSITORY CODE  (FIX 2: zipball, sirf 1 request)
# ============================================================

def get_repo_code(repo_url):

    # --------------------------------------------------------
    # Parse repository URL
    # --------------------------------------------------------

    owner, repo = parse_github_url(
        repo_url
    )

    print(
        f"\nRepository: {owner}/{repo}"
    )

    # --------------------------------------------------------
    # Poora repo ek hi zip me (default branch khud milti hai)
    # --------------------------------------------------------

    zip_url = f"{GITHUB_API}/repos/{owner}/{repo}/zipball"

    response = session.get(
        zip_url,
        timeout=120
    )

    response.raise_for_status()

    # --------------------------------------------------------
    # Zip ko RAM me hi read karo (disk pe kuch save nahi hota)
    # --------------------------------------------------------

    repository_content = {}

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:

        for info in zf.infolist():

            if info.is_dir():
                continue

            # Zip ke andar top folder "owner-repo-sha/" hota hai, hata do
            if "/" in info.filename:
                path = info.filename.split("/", 1)[1]
            else:
                path = info.filename

            if not path:
                continue

            if not is_allowed_file(path):
                continue

            if info.file_size > MAX_FILE_SIZE:

                print(
                    f"Skipping large file: {path} "
                    f"({info.file_size / 1024:.1f} KB)"
                )

                continue

            try:

                repository_content[path] = zf.read(info).decode(
                    "utf-8",
                    errors="ignore"
                )

            except Exception as error:

                print(
                    f"Decode error: {path} -> {error}"
                )

    print(
        f"Successfully fetched: "
        f"{len(repository_content)} files"
    )

    return repository_content


# ============================================================
# CONVERT REPOSITORY TO LLM INPUT
# ============================================================

def build_assignment_code(repository_content):

    assignment_code = []

    for path, content in repository_content.items():

        assignment_code.append(
            f"""
============================================================
FILE: {path}
============================================================

{content}

"""
        )

    return "\n".join(assignment_code)


# ============================================================
# MAIN
# ============================================================

def githubans(repo_url: str) -> str:

    try:

        code = get_repo_code(
            repo_url
        )

        assignment_code = build_assignment_code(
            code
        )

        return assignment_code

    except requests.exceptions.HTTPError as error:

        print(
            "GitHub API Error:",
            error
        )

        return ""

    except Exception as error:

        print(
            "Error:",
            error
        )

        return ""