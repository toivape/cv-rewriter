from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from nodes import (
    ai_review,
    apply_prompt,
    ask_ai_question,
    export_pdf,
    extract_content,
    generalize_prompt,
    generate_prompt,
    human_review,
    refine_prompt,
    save_iteration,
    upload_pdfs,
)
from state import CVState


def _should_extract(state: CVState) -> str:
    if state.get("preferred_cv_markdown") and state.get("original_cv_markdown"):
        return "generate_prompt"
    return "extract_content"


def _route_after_ai_review(state: CVState) -> str:
    if state.get("ai_questions"):
        return "ask_ai_question"
    return "human_review"


def _route_after_ai_question(state: CVState) -> str:
    if state["ai_question_idx"] < len(state["ai_questions"]):
        return "ask_ai_question"
    return "human_review"


def _route_after_review(state: CVState) -> str:
    feedback = (state.get("last_feedback") or "").strip().lower()
    if not feedback or feedback == "done":
        return "generalize_prompt"
    return "refine_prompt"


def build_graph():
    builder = StateGraph(CVState)

    builder.add_node("upload_pdfs", upload_pdfs)
    builder.add_node("extract_content", extract_content)
    builder.add_node("generate_prompt", generate_prompt)
    builder.add_node("apply_prompt", apply_prompt)
    builder.add_node("save_iteration", save_iteration)
    builder.add_node("ai_review", ai_review)
    builder.add_node("ask_ai_question", ask_ai_question)
    builder.add_node("human_review", human_review)
    builder.add_node("refine_prompt", refine_prompt)
    builder.add_node("generalize_prompt", generalize_prompt)
    builder.add_node("export_pdf", export_pdf)

    builder.add_edge(START, "upload_pdfs")
    builder.add_conditional_edges("upload_pdfs", _should_extract)
    builder.add_edge("extract_content", "generate_prompt")
    builder.add_edge("generate_prompt", "apply_prompt")
    builder.add_edge("apply_prompt", "save_iteration")
    builder.add_edge("save_iteration", "ai_review")
    builder.add_conditional_edges("ai_review", _route_after_ai_review)
    builder.add_conditional_edges("ask_ai_question", _route_after_ai_question)
    builder.add_conditional_edges("human_review", _route_after_review)
    builder.add_edge("refine_prompt", "apply_prompt")
    builder.add_edge("generalize_prompt", "export_pdf")
    builder.add_edge("export_pdf", END)

    return builder.compile(checkpointer=MemorySaver())
