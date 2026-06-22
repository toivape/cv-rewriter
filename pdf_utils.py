import subprocess
from pathlib import Path


def export_to_pdf(markdown_path: Path, output_path: Path) -> None:
    subprocess.run(
        ["pandoc", str(markdown_path), "-o", str(output_path)],
        check=True,
    )
