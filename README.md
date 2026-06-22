# CV rewriter

A human-in-the-loop [LangGraph](https://langchain-ai.github.io/langgraph/) agent that learns a CV
formatting style from a reference CV and applies it to another. Both inputs are PDFs; the agent
extracts them to Markdown, generates a reusable formatting prompt, applies it, and iterates with
feedback from both an automated AI reviewer and a human reviewer.

The primary output is **`final_prompt.md`** — a portable, reusable prompt you can apply to any CV
later. The reformatted CV is also exported as PDF.

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
7. The prompt is generalised and saved to `output/final_prompt.md`.
8. The final CV is exported to `output/final_cv.pdf` via pandoc.

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager
- [pandoc](https://pandoc.org/installing.html) for PDF export (`brew install pandoc` on macOS)
- `ANTHROPIC_API_KEY` environment variable set

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

## Output layout

```
output/
├── preferred_cv.md       # cached extraction of the reference PDF
├── original_cv.md        # cached extraction of your CV
├── iteration_001/
│   ├── prompt.md         # prompt used in this iteration
│   ├── cv.md             # CV output (for review)
│   └── ai_review.json    # AI reviewer findings
├── iteration_002/
│   └── ...
├── final_prompt.md       # reusable formatting prompt — primary output
└── final_cv.pdf          # final CV reformatted by the prompt
```
