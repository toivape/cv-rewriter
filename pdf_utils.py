import argparse
import subprocess
from pathlib import Path


def export_to_pdf(markdown_path: Path, output_path: Path) -> None:
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
    pdf_path = Path(args.output) if args.output else md_path.with_suffix(".pdf")
    export_to_pdf(md_path, pdf_path)
    print(f"PDF exported → {pdf_path}")


if __name__ == "__main__":
    main()
