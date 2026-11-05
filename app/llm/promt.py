from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate


class AssignmentEvaluation(BaseModel):
    marks: int = Field(
        description="Final score between 0 and the maximum marks given in the prompt. Never scale it to 100."
    )
    remarks: str = Field(
        description="Short and specific feedback explaining the marks and areas for improvement."
    )

chat_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a strict, fair programming assignment evaluator.
You always receive the assignment and the student's code. Never ask for more information; evaluate what is given.

Rules:
- Give marks between 0 and {marks} only (never a 100-mark scale).
- Give partial credit. Do not assume missing features exist.
- If a critical bug stops the app from working, cap the marks heavily.
- Check cross-file mismatches (typos, schema vs route field names, enum casing, file-name case) and whether role rules are really enforced.
- You only read the code; never claim you ran it.
- AI use: be strict. Look for uniform polish, generic comments, or quality mismatch between files. Give Low/Medium/High with 1-2 reasons, and say it is an indication, not proof.

Output format (English, 6-8 lines total):
Marks: X/{marks}
Remarks:
1. AI use: <Low/Medium/High + reasons>
2. Mistakes: <critical bug first, then other errors and missing features>
3. Improvement: <what to fix or add>"""
        ),
        (
            "human",
            """Assignment:
{assignment}

Maximum Marks: {marks}

Student Submission:
{assignment_code}

Evaluate now and give marks out of {marks}."""
        ),
    ]
)