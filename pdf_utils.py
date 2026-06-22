import argparse
import subprocess
import sys
from pathlib import Path


def export_to_pdf(markdown_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pandoc", str(markdown_path), "--pdf-engine=weasyprint", "-o", str(output_path)],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Export a Markdown CV to PDF via pandoc (WeasyPrint engine, no LaTeX needed)."
    )
    parser.add_argument("markdown", help="Path to the Markdown CV (e.g. output-.../iteration_002/cv.md)")
    parser.add_argument("output", nargs="?", help="Output PDF path (default: <markdown> with .pdf suffix)")
    args = parser.parse_args()

    md_path = Path(args.markdown)
    if not md_path.is_file():
        sys.exit(f"Error: Markdown file not found: {md_path}")

    pdf_path = Path(args.output) if args.output else md_path.with_suffix(".pdf")
    try:
        export_to_pdf(md_path, pdf_path)
    except FileNotFoundError:
        sys.exit("Error: pandoc not found. Install pandoc and WeasyPrint (see README).")
    except subprocess.CalledProcessError as e:
        sys.exit(f"Error: PDF export failed (pandoc exit {e.returncode}). Is WeasyPrint installed?")
    print(f"PDF exported → {pdf_path}")


if __name__ == "__main__":
    main()
