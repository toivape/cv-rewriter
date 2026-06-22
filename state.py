from typing import Annotated, Any, TypedDict
from operator import add


class CVState(TypedDict):
    preferred_cv_path: str
    cv_to_improve_path: str
    guidelines: str
    preferred_file_id: str
    cv_file_id: str
    preferred_cv_markdown: str
    original_cv_markdown: str
    current_cv_markdown: str
    current_prompt: str
    iteration: int
    feedback_history: Annotated[list[str], add]
    output_dir: str
    is_finalized: bool
    last_feedback: str
    ai_findings: list[dict[str, Any]]
    ai_questions: list[dict[str, Any]]
    ai_answers: list[str]
    ai_question_idx: int
