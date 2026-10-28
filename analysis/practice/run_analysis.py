"""Execute the practice notebook and export a browser-readable HTML copy."""

import os
from pathlib import Path
import tempfile
import time

import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter


def main():
    folder = Path(__file__).resolve().parent
    notebook_path = folder / "practice_analysis.ipynb"
    notebook = nbformat.read(notebook_path, as_version=4)
    started = time.monotonic()

    def progress(cell, cell_index, **kwargs):
        if cell.cell_type == "code":
            print(f"Executed cell {cell_index + 1}/{len(notebook.cells)}", flush=True)

    with tempfile.TemporaryDirectory(prefix="practice-analysis-") as temporary:
        # These settings are inherited by the kernel, not written to user configuration.
        for key, subfolder in {
            "MPLCONFIGDIR": "matplotlib",
            "JUPYTER_RUNTIME_DIR": "jupyter",
            "IPYTHONDIR": "ipython",
        }.items():
            os.environ.setdefault(key, str(Path(temporary) / subfolder))
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        client = NotebookClient(
            notebook,
            timeout=240,
            kernel_name="python3",
            resources={"metadata": {"path": str(folder)}},
            on_cell_executed=progress,
        )
        client.execute()

    nbformat.validate(notebook)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert all(cell.execution_count is not None for cell in code_cells)
    assert not any(
        output.output_type == "error"
        for cell in code_cells
        for output in cell.outputs
    )
    nbformat.write(notebook, notebook_path)
    exporter = HTMLExporter(template_name="lab")
    exporter.exclude_input_prompt = True
    exporter.exclude_output_prompt = True
    html, _ = exporter.from_notebook_node(notebook)
    html_path = notebook_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    print(f"Completed {len(code_cells)} code cells in {time.monotonic() - started:.1f}s.")
    print(f"Notebook: {notebook_path}")
    print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
