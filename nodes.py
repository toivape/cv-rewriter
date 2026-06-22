import json
import re
import subprocess
from pathlib import Path
from typing import Any

import anthropic
from langgraph.types import interrupt

from pdf_utils import export_to_pdf
from state import CVState

client = anthropic.Anthropic()
MODEL = "claude-opus-4-8"
FILES_BETA = "files-api-2025-04-14"

_EXTRACT_SYSTEM = (
    "You are a document extraction assistant. Extract the content of the CV from the PDF "
    "as clean Markdown, preserving section headings, project titles, dates, and prose paragraphs. "
    "For each Experience entry, include the prose paragraphs exactly as written. "
    "Omit the 'Skills:' line at the end of each entry — do not include it. "
    "Preserve all other sections (Summary, Certifications, Education, Languages, etc.)."
)

_GENERATE_PROMPT_SYSTEM = (
    "You are a CV writing expert. Analyse the formatting style of a reference CV and create "
    "a clear, reusable prompt that an AI model can follow to reformat another consultant's CV "
    "project descriptions to match that style."
)

_APPLY_SYSTEM = (
    "You are a CV writer. Apply the given formatting prompt to rewrite the prose paragraphs of "
    "each Experience entry in the CV. Output the full CV in Markdown. "
    "Do NOT include or generate Skills lines — those are handled separately.\n\n"
    "Do NOT introduce facts that are not in the original CV. Specifically: do not add "
    "certifications, employers, dates, technologies, metrics, awards, or responsibilities "
    "the source does not mention. The preferred CV is a STYLE reference only — never copy "
    "its content. If a field is missing in the original, leave it out rather than inventing it."
)

_REFINE_SYSTEM = (
    "You are a prompt engineer refining a CV formatting prompt based on reviewer feedback. "
    "Update the prompt to address the feedback while preserving what already works. "
    "Output ONLY the revised prompt text."
)

_GENERALIZE_SYSTEM = (
    "You are a prompt engineer finalising a CV formatting prompt for reuse. "
    "Remove any references to specific companies, projects, or individuals from the example CVs "
    "used during development so the prompt is portable and works for any software consultant's CV. "
    "Output ONLY the final prompt text."
)

_AI_REVIEW_SYSTEM = """You are a CV review specialist. You evaluate a CV summary section for problems
that hurt it with BOTH automated screeners (ATS / LLM-based) and human recruiters.

Review the text against each check below. For every issue you find, quote the
exact offending span, name the check it violates, and give a concrete rewrite or
fix. Do not give generic advice. If a check passes, say so briefly and move on.

## Checks

1. SENTENCE LENGTH
   Flag any sentence over ~30 words or with 3+ clauses. Long sentences hurt
   skimming and increase the chance an LLM screener drops a detail when
   summarizing the candidate. For each flagged sentence, propose a split.

2. FILLER / EMPTY PHRASING
   Flag phrases that contain no extractable fact — adjective-heavy language a
   parser gets nothing from and a human skips.
   Examples of filler: "deep technical craftsmanship", "broader enterprise
   landscapes", "passionate about quality", "results-driven professional",
   "leverage synergies".
   For each, either recommend deletion or replacement with a concrete claim
   (a named technology, a measurable outcome, a specific responsibility).

3. VAGUE WHERE SPECIFIC IS POSSIBLE
   Flag generic terms where a precise, searchable equivalent likely exists:
   - "message queue" → name it (Kafka, SQS, RabbitMQ)
   - "cloud" → name it (AWS, GCP, Azure)
   - "various databases" → list them
   - "AI tools" → name them (Claude, OpenAI, Copilot)
   Recommend asking the candidate for the specific term rather than inventing one.

4. MISSING CONCRETE CLAIMS
   Note whether the summary contains at least one concrete outcome (scale handled,
   team size, a before/after improvement, a system replaced). If none exists,
   flag it and prompt for one. Do NOT fabricate metrics.

5. AI-GENERATED FEEL
   Rate how strongly the text reads as LLM-generated (low / medium / high) and
   cite the specific signals. Common tells:
   - triadic lists everywhere ("design, implement and operate")
   - "X who consistently applies Y", "combines X with Y"
   - symmetrical parallel sentence structures in every paragraph
   - abstract closers that restate without adding
   Recommend concrete edits that break the pattern (vary sentence length, use
   plain verbs, cut one item from rhythmic triads).

6. CLIENT / NDA EXPOSURE
   Flag named client companies. On a consultancy CV these may breach NDA. Suggest
   an anonymized but keyword-preserving descriptor (e.g. "a major Nordic bank",
   "a large retail group") that keeps the sector and scale searchable.
   Exception: industry-standard product/protocol names (Click to Pay, RFC 8693,
   OAuth 2.0) are not client identifiers — do not flag these.

7. PERSON & TENSE CONSISTENCY
   Flag mixed first/third person or inconsistent tense.

## Output format
Return a JSON array. One object per issue:
{
  "check": "<check name>",
  "severity": "high | medium | low",
  "span": "<exact quoted text, or null if document-level>",
  "problem": "<one sentence>",
  "fix": "<concrete rewrite or specific action>"
}
If a check is a question for the candidate (e.g. missing metric), set "fix" to the
exact question to ask. Return [] if no issues."""

_QUESTION_CHECKS = {"VAGUE WHERE SPECIFIC IS POSSIBLE", "MISSING CONCRETE CLAIMS"}


def upload_pdfs(state: CVState) -> dict:
    output_dir = Path(state["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    preferred_cache = Path(state["preferred_cv_path"]).with_suffix(".md")
    original_cache = Path(state["cv_to_improve_path"]).with_suffix(".md")

    if preferred_cache.exists() and original_cache.exists():
        print("Loading extracted CVs from disk cache...")
        return {
            "preferred_cv_markdown": preferred_cache.read_text(),
            "original_cv_markdown": original_cache.read_text(),
            "preferred_file_id": "",
            "cv_file_id": "",
        }

    print("Uploading PDFs to Anthropic Files API...")
    with open(state["preferred_cv_path"], "rb") as f:
        preferred_file = client.beta.files.upload(
            file=(Path(state["preferred_cv_path"]).name, f, "application/pdf"),
        )
    with open(state["cv_to_improve_path"], "rb") as f:
        cv_file = client.beta.files.upload(
            file=(Path(state["cv_to_improve_path"]).name, f, "application/pdf"),
        )

    return {
        "preferred_file_id": preferred_file.id,
        "cv_file_id": cv_file.id,
        "preferred_cv_markdown": "",
        "original_cv_markdown": "",
    }


def extract_content(state: CVState) -> dict:
    print("Extracting CV content with Claude...")

    preferred_md = _extract_pdf(state["preferred_file_id"])
    original_md = _extract_pdf(state["cv_file_id"])

    Path(state["preferred_cv_path"]).with_suffix(".md").write_text(preferred_md)
    Path(state["cv_to_improve_path"]).with_suffix(".md").write_text(original_md)

    # Clean up uploaded files — they're now cached on disk
    for file_id in (state["preferred_file_id"], state["cv_file_id"]):
        try:
            client.beta.files.delete(file_id)
        except anthropic.APIError:
            pass

    return {
        "preferred_cv_markdown": preferred_md,
        "original_cv_markdown": original_md,
    }


def _extract_pdf(file_id: str) -> str:
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=_EXTRACT_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "file", "file_id": file_id},
                },
                {
                    "type": "text",
                    "text": "Extract this CV as Markdown. Omit all Skills lines from Experience entries.",
                },
            ],
        }],
        betas=[FILES_BETA],
    )
    return response.content[0].text


def generate_prompt(state: CVState) -> dict:
    print("Generating initial formatting prompt...")

    guidelines_block = (
        f"\n\nAdditional guidelines from the user:\n{state['guidelines']}"
        if state.get("guidelines")
        else ""
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=[{"type": "text", "text": _GENERATE_PROMPT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Preferred format CV (reference):\n\n{state['preferred_cv_markdown']}"
                    ),
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": (
                        f"CV to be reformatted:\n\n{state['original_cv_markdown']}"
                        f"{guidelines_block}\n\n"
                        "Key observations about what needs to change:\n"
                        "- The preferred format opens each project description with a SERVICE-FIRST paragraph: "
                        "what end users do with the software and why it matters to the client. "
                        "It does NOT start with 'I did X'.\n"
                        "- The second paragraph describes the technical implementation at a high level "
                        "and the candidate's own role.\n"
                        "- The Skills line (e.g. 'Skills: Java, AWS...') is auto-generated by the CMS "
                        "and must NOT appear in the output.\n\n"
                        "Create a clear, reusable formatting prompt that instructs an AI to rewrite "
                        "the prose paragraphs of each Experience entry to match the preferred style. "
                        "The prompt must not reference specific companies or people from these examples. "
                        "The prompt MUST include an explicit rule that the AI may only restate facts "
                        "present in the source CV — no fabricated certifications, employers, dates, "
                        "technologies, metrics, or responsibilities; the preferred CV is a style "
                        "reference only, never a content source. "
                        "Output ONLY the prompt text."
                    ),
                },
            ],
        }],
    )

    return {"current_prompt": response.content[0].text}


def apply_prompt(state: CVState) -> dict:
    iteration = state.get("iteration", 0) + 1
    print(f"Applying prompt (iteration {iteration})...")

    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=[{"type": "text", "text": _APPLY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Preferred format reference:\n\n{state['preferred_cv_markdown']}",
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": f"Original CV:\n\n{state['original_cv_markdown']}",
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": (
                        f"Formatting prompt to apply:\n\n{state['current_prompt']}\n\n"
                        "Apply this prompt to rewrite the prose paragraphs of each Experience entry. "
                        "Do NOT include Skills lines. Output the full reformatted CV."
                    ),
                },
            ],
        }],
    )

    return {"current_cv_markdown": response.content[0].text}


def save_iteration(state: CVState) -> dict:
    iteration = state.get("iteration", 0) + 1
    output_dir = Path(state["output_dir"])
    iter_dir = output_dir / f"iteration_{iteration:03d}"
    iter_dir.mkdir(parents=True, exist_ok=True)

    (iter_dir / "prompt.md").write_text(state["current_prompt"])
    (iter_dir / "cv.md").write_text(state["current_cv_markdown"])

    print(f"Saved iteration {iteration} → {iter_dir}")
    return {"iteration": iteration}


def ai_review(state: CVState) -> dict:
    iteration = state.get("iteration", 1)
    print(f"Running AI review (iteration {iteration})...")

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=_AI_REVIEW_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"CV to review:\n\n{state['current_cv_markdown']}\n\n"
                "Return only the JSON array — no preamble, no markdown fence."
            ),
        }],
    )

    findings = _parse_findings(response.content[0].text)
    questions = [f for f in findings if _is_question_finding(f)]

    iter_dir = Path(state["output_dir"]) / f"iteration_{iteration:03d}"
    (iter_dir / "ai_review.json").write_text(json.dumps(findings, indent=2))

    print(f"AI review found {len(findings)} issue(s); {len(questions)} need user input.")
    return {
        "ai_findings": findings,
        "ai_questions": questions,
        "ai_answers": [],
        "ai_question_idx": 0,
    }


def _parse_findings(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    payload = fence.group(1).strip() if fence else text
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", payload, re.DOTALL)
        if not match:
            print("Warning: could not parse AI review JSON; treating as empty.")
            return []
        data = json.loads(match.group(0))
    return data if isinstance(data, list) else []


def _is_question_finding(finding: dict[str, Any]) -> bool:
    check = (finding.get("check") or "").strip().upper()
    if check in _QUESTION_CHECKS:
        return True
    fix = (finding.get("fix") or "").strip()
    return fix.endswith("?")


def ask_ai_question(state: CVState) -> dict:
    idx = state["ai_question_idx"]
    questions = state["ai_questions"]
    finding = questions[idx]

    prompt_lines = [
        f"AI review question {idx + 1}/{len(questions)} — {finding.get('check', '')}",
    ]
    if finding.get("span"):
        prompt_lines.append(f"Context: \"{finding['span']}\"")
    prompt_lines.append(finding.get("fix") or finding.get("problem") or "")
    prompt_lines.append("(Answer with the specific detail, or type 'skip' to leave as-is.)")

    answer = interrupt("\n".join(prompt_lines))
    return {
        "ai_answers": [*state["ai_answers"], answer],
        "ai_question_idx": idx + 1,
    }


def human_review(state: CVState) -> dict:
    iteration = state.get("iteration", 1)
    output_dir = Path(state["output_dir"])
    iter_dir = output_dir / f"iteration_{iteration:03d}"

    print(f"\n{'='*70}")
    print(f"ITERATION {iteration}  —  REFORMATTED CV")
    print("="*70)
    print(state["current_cv_markdown"])
    print("="*70)

    findings = state.get("ai_findings") or []
    if findings:
        print("AI REVIEW FINDINGS")
        print("-" * 70)
        for f in findings:
            check = f.get("check", "?")
            severity = f.get("severity", "?")
            problem = f.get("problem", "")
            fix = f.get("fix", "")
            print(f"[{severity}] {check}: {problem}")
            if f.get("span"):
                print(f"  span: \"{f['span']}\"")
            print(f"  fix:  {fix}")
        print("-" * 70)

    print(f"Prompt → {iter_dir / 'prompt.md'}")
    print(f"CV     → {iter_dir / 'cv.md'}")
    if findings:
        print(f"AI rev → {iter_dir / 'ai_review.json'}")

    feedback = interrupt(
        "What looks wrong in this output? (describe issues, or press Enter / type 'done' to finalise)"
    )
    return {"last_feedback": feedback}


def refine_prompt(state: CVState) -> dict:
    print("Refining prompt based on feedback...")

    history = state.get("feedback_history", [])
    history_block = (
        "\n\nPrevious feedback rounds:\n" + "\n".join(f"- {f}" for f in history)
        if history
        else ""
    )

    ai_block = _format_ai_feedback(state)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=[{"type": "text", "text": _REFINE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Preferred format reference:\n\n{state['preferred_cv_markdown']}",
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": (
                        f"Current prompt:\n\n{state['current_prompt']}"
                        f"{history_block}"
                        f"{ai_block}\n\n"
                        f"Latest human feedback:\n{state['last_feedback']}\n\n"
                        "Revise the prompt to address ALL of the above. Output ONLY the revised prompt."
                    ),
                },
            ],
        }],
    )

    return {
        "current_prompt": response.content[0].text,
        "feedback_history": [state["last_feedback"]],
    }


def _format_ai_feedback(state: CVState) -> str:
    findings = state.get("ai_findings") or []
    if not findings:
        return ""

    pending_answers = list(state.get("ai_answers") or [])
    lines = ["\n\nAI review findings (apply these as prompt-level rules, not one-off edits):"]
    for f in findings:
        check = f.get("check", "?")
        severity = f.get("severity", "?")
        problem = f.get("problem", "")
        fix = f.get("fix", "")
        span = f.get("span")
        lines.append(f"- [{severity}] {check}: {problem}")
        if span:
            lines.append(f"  span: \"{span}\"")
        lines.append(f"  fix: {fix}")
        if _is_question_finding(f) and pending_answers:
            ans = pending_answers.pop(0)
            lines.append(f"  candidate answer: {ans}")
    return "\n".join(lines)


def generalize_prompt(state: CVState) -> dict:
    print("Finalising and generalising the prompt...")

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=_GENERALIZE_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Here is the prompt developed over {state.get('iteration', 1)} iteration(s):\n\n"
                f"{state['current_prompt']}\n\n"
                "Generalise it for reuse with any software consultant's CV. "
                "Output ONLY the final prompt."
            ),
        }],
    )

    final_prompt = response.content[0].text
    output_dir = Path(state["output_dir"])
    (output_dir / "final_prompt.md").write_text(final_prompt)
    print(f"Final prompt → {output_dir / 'final_prompt.md'}")

    return {"current_prompt": final_prompt, "is_finalized": True}


def export_pdf(state: CVState) -> dict:
    output_dir = Path(state["output_dir"])
    iteration = state.get("iteration", 1)
    cv_md = output_dir / f"iteration_{iteration:03d}" / "cv.md"
    pdf_path = output_dir / "final_cv.pdf"

    print(f"Exporting final CV to PDF: {pdf_path}")
    try:
        export_to_pdf(cv_md, pdf_path)
        print(f"PDF exported → {pdf_path}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Warning: pandoc export failed ({e}). The Markdown CV is at {cv_md}")

    return {}
