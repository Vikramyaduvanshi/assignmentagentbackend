from langchain_ollama import ChatOllama

from app.llm.promt import chat_prompt, AssignmentEvaluation
from app.datafetch.githubfetch import githubans
from app.datafetch.drivecontent import drivecontent

base_url = "http://localhost:11434"

# num_ctx tokens me hai. Code ka limit isse thoda kam rakho.
NUM_CTX = 16384
MAX_CODE_CHARS = 40000   # ~10-12k tokens, baaki jagah prompt + output ke liye

llm = ChatOllama(
    base_url=base_url,
    model="qwen2.5-coder:14b",
    temperature=0,
    num_ctx=NUM_CTX,
)

# json_schema method: Ollama output ko schema ke hisaab se force karta hai
structured_llm = llm.with_structured_output(
    AssignmentEvaluation,
    method="json_schema",
)

llmchain = chat_prompt | structured_llm


def lmsLLM(link: str, assignment: str, marks: int = 10) -> AssignmentEvaluation:

    # -----------------------------------------
    # Get code content from link
    # -----------------------------------------
    if "github.com" in link:
        githubcontent = githubans(link)

    elif "drive.google.com" in link or "docs.google.com" in link:
        githubcontent = drivecontent(link)

    else:
        raise ValueError(f"Unsupported link: {link}")

    if not githubcontent:
        raise ValueError(f"Code fetch nahi hua ya repo khali hai: {link}")

    # -----------------------------------------
    # Bade repo ko truncate karo (context overflow se bachne ke liye)
    # -----------------------------------------
    if len(githubcontent) > MAX_CODE_CHARS:
        githubcontent = (
            githubcontent[:MAX_CODE_CHARS]
            + "\n\n[... code truncated due to size ...]"
        )

    # -----------------------------------------
    # Invoke LLM
    # -----------------------------------------
    ans = llmchain.invoke(
        {
            "assignment": str(assignment),
            "marks": marks,
            "assignment_code": githubcontent,
        }
    )

    # safety: marks range ke bahar na jaye
    ans.marks = max(1, min(ans.marks, marks))

    return ans
