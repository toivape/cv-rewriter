# CV rewriter

A human-in-the-loop [LangGraph](https://langchain-ai.github.io/langgraph/) agent that learns a CV
formatting style from a reference CV and applies it to another. Both inputs are PDFs; the agent
extracts them to Markdown, generates a reusable formatting prompt, applies it, and iterates with
feedback from both an automated AI reviewer and a human reviewer.

The primary output is **`final_prompt.md`** — a portable, reusable prompt you can apply to any CV
later. The reformatted CV is saved as Markdown; you can optionally export it to PDF with a separate
command (see [Export to PDF](#export-to-pdf)).

## How it works

1. Both PDFs are uploaded to the Anthropic Files API and extracted to Markdown (cached to disk;
   subsequent runs skip this step).
2. Claude analyses the reference CV style and generates an initial formatting prompt.
3. The prompt is applied to your CV.
4. An AI reviewer checks the output for sentence length, filler, vague terms, missing concrete
   claims, AI-generated feel, NDA exposure, and tense consistency. If the reviewer needs specifics
   the model doesn't have (a metric, a technology name), it asks you one question at a time.
5. You review the result and either accept it or describe what's wrong. The agent refines the
   **prompt** (not the CV ad-hoc) and re-applies it. Both AI findings and your feedback feed into
   the refinement.
6. Repeat until satisfied, then press Enter or type `done`.
7. The prompt is generalised and saved to `<output_dir>/final_prompt.md`; the final reformatted CV
   is the Markdown in the last `iteration_NNN/cv.md`.
8. Optionally, export that CV to PDF with a separate command (see [Export to PDF](#export-to-pdf)).

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager
- `ANTHROPIC_API_KEY` environment variable set
- Optional (only for [Export to PDF](#export-to-pdf)): [pandoc](https://pandoc.org/installing.html)
  and [WeasyPrint](https://weasyprint.org/) (`brew install pandoc weasyprint` on macOS) — WeasyPrint
  is the PDF engine, so no LaTeX is needed

## Setup

```bash
uv sync
```

## Run

```bash
# Supply your own reference and target CVs
uv run python main.py --preferred path/to/reference.pdf --cv path/to/your.pdf

# Optional plain-text formatting guidelines
uv run python main.py --preferred ref.pdf --cv mine.pdf --guidelines guidelines.txt

# Custom output directory (default: output-<timestamp>)
uv run python main.py --preferred ref.pdf --cv mine.pdf --output ./my-output
```

## Export to PDF

The main run stops at Markdown and needs no extra tools. To turn the final CV into a PDF, install
the optional dependencies above and run:

```bash
# Defaults the output next to the input, e.g. iteration_002/cv.pdf
uv run python pdf_utils.py output-<timestamp>/iteration_002/cv.md

# Or choose the output path
uv run python pdf_utils.py output-<timestamp>/iteration_002/cv.md final_cv.pdf
```

## Output layout

```
<output_dir>/             # default: output-<timestamp>, or whatever you pass to --output
├── preferred_cv.md       # cached extraction of the reference PDF
├── original_cv.md        # cached extraction of your CV
├── iteration_001/
│   ├── prompt.md         # prompt used in this iteration
│   ├── cv.md             # CV output (for review)
│   └── ai_review.json    # AI reviewer findings
├── iteration_002/
│   └── ...               # the last iteration's cv.md is the final reformatted CV
└── final_prompt.md       # reusable formatting prompt — primary output
```

PDF export is opt-in (see [Export to PDF](#export-to-pdf)) and writes wherever you point it.
