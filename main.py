import argparse
import time
from datetime import datetime
from pathlib import Path

from langgraph.types import Command

from graph import build_graph


def main():
    parser = argparse.ArgumentParser(
        description="Iteratively refine a CV formatting prompt using human-in-the-loop feedback."
    )
    parser.add_argument(
        "--preferred",
        default="cv/preferred_cv.pdf",
        help="Path to the reference CV that demonstrates the desired format (PDF)",
    )
    parser.add_argument(
        "--cv",
        default="cv/cv.pdf",
        help="Path to the CV to reformat (PDF)",
    )
    parser.add_argument("--guidelines", help="Path to optional plain-text formatting guidelines")
    parser.add_argument("--output", help="Output directory (default: output-<timestamp>)")
    args = parser.parse_args()

    output_dir = args.output or f"output-{datetime.now().strftime('%Y%m%dT%H%M')}"

    guidelines = Path(args.guidelines).read_text() if args.guidelines else ""

    initial_state = {
        "preferred_cv_path": args.preferred,
        "cv_to_improve_path": args.cv,
        "guidelines": guidelines,
        "preferred_file_id": "",
        "cv_file_id": "",
        "preferred_cv_markdown": "",
        "original_cv_markdown": "",
        "current_cv_markdown": "",
        "current_prompt": "",
        "iteration": 0,
        "feedback_history": [],
        "output_dir": output_dir,
        "is_finalized": False,
        "last_feedback": "",
        "ai_findings": [],
        "ai_questions": [],
        "ai_answers": [],
        "ai_question_idx": 0,
    }

    config = {"configurable": {"thread_id": f"cv-session-{int(time.time())}"}}
    graph = build_graph()

    graph.invoke(initial_state, config=config)

    while True:
        state = graph.get_state(config)

        if not state.next:
            print("\nDone.")
            print(f"  Final prompt : {Path(output_dir) / 'final_prompt.md'}")
            print(f"  Final CV PDF : {Path(output_dir) / 'final_cv.pdf'}")
            break

        feedback = input(
            "\nWhat looks wrong? (describe issues, or press Enter / type 'done' to finalise): "
        ).strip()

        graph.invoke(Command(resume=feedback or "done"), config=config)


if __name__ == "__main__":
    main()
