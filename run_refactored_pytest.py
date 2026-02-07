import argparse
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_SRC_PATH = Path("src/pluggy")
REFACTORED_ROOT_PATH = Path("inline_variable_results_gemini-3-pro-preview")
TEST_RESULTS_ROOT = Path("test_results")

ITERATION_PREFIX = "iteration_"
SUMMARY_FILENAME = "test_results.txt"
ITERATION_RESULT_FILENAME = "test_result.txt"


def get_project_structure(project_dir: Path) -> str:
    """Erstellt eine Übersicht der Projektstruktur."""
    structure = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d not in {"__pycache__", "tests", "pathlib2.egg-info"}
        ]
        level = root.replace(str(project_dir), "").count(os.sep)
        indent = " " * 2 * level
        structure.append(f"{indent}{os.path.basename(root)}/")
        subindent = " " * 2 * (level + 1)
        for file in files:
            if file.endswith(".py"):
                structure.append(f"{subindent}{file}")
    return "\n".join(structure)


def backup_project(project_dir: Path, backup_dir: Path) -> None:
    """Erstellt ein Backup des Projekts."""
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(
        project_dir,
        backup_dir,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".git", "test", "tests", "pathlib2.egg-info"
        ),
    )


def restore_project(backup_dir: Path, project_dir: Path) -> None:
    """Stellt das Projekt aus dem Backup wieder her"""
    backup_dir = Path(backup_dir).resolve()
    project_dir = Path(project_dir).resolve()

    if not backup_dir.exists():
        raise FileNotFoundError(f"Backup-Verzeichnis nicht gefunden: {backup_dir}")

    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(backup_dir, project_dir, dirs_exist_ok=True)


def apply_changes(project_dir: Path | str, files: dict[str, str]) -> None:
    """Wendet die Änderungen auf die Dateien an, ignoriert jedoch Dateien im 'tests'-Ordner."""
    project_dir = Path(project_dir).resolve()

    for filename, code in files.items():
        file_rel = Path(filename)

        if any(part == "tests" for part in file_rel.parts):
            continue

        file_path = (project_dir / file_rel).resolve()
        try:
            file_path.relative_to(project_dir)
        except ValueError:
            print(f" {filename} liegt außerhalb von {project_dir}, übersprungen")
            continue

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(code, encoding="utf-8")
            print(f" {filename} aktualisiert")
        except Exception as e:
            print(f" Fehler beim Schreiben von {filename}: {e}")


def run_pytest(cwd: Path, env: dict[str, str] | None = None) -> dict[str, object]:
    """Führt pytest aus und gibt das Ergebnis zurück."""
    try:
        result = subprocess.run(
            ["pytest"],
            capture_output=True,
            text=True,
            cwd=str(cwd),
            env=env,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_iteration_label(iteration_dir_name: str) -> str:
    """
    Converts "iteration_1" / "iteration_01" / "iteration_001" -> "iteration 1"
    Falls back to the directory name if parsing fails.
    """
    if iteration_dir_name.startswith(ITERATION_PREFIX):
        suffix = iteration_dir_name[len(ITERATION_PREFIX) :].strip()
        try:
            n = int(suffix)
            return f"iteration {n}"
        except ValueError:
            pass
    return iteration_dir_name.replace("_", " ")


def format_summary_line(iteration_dir_name: str, success: bool) -> str:
    label = parse_iteration_label(iteration_dir_name)
    return f"{label} {'passed' if success else 'failed'}"


def save_iteration_single_file(
    result_dir: Path, test_result: dict[str, object], status: str, note: str | None = None
) -> None:
    """
    Ensures each iteration folder contains ONLY ONE file: test_result.txt
    The file contains the exact stdout/stderr/returncode plus a status line (and optional note).
    """
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)

    stdout = str(test_result.get("stdout", ""))
    stderr = str(test_result.get("stderr", ""))
    returncode = str(test_result.get("returncode", ""))

    parts: list[str] = []
    parts.append(f"STATUS: {status}")
    parts.append(f"RETURNCODE: {returncode}")
    parts.append(f"TIMESTAMP: {datetime.now().isoformat()}")
    if note:
        parts.append("")
        parts.append(f"NOTE: {note}")
    parts.append("")
    parts.append("=== PYTEST STDOUT ===")
    parts.append(stdout)
    parts.append("")
    parts.append("=== PYTEST STDERR ===")
    parts.append(stderr)
    parts.append("")

    write_text_file(result_dir / ITERATION_RESULT_FILENAME, "\n".join(parts))


def should_skip_snapshot_path(relative_path: Path) -> bool:
    for part in relative_path.parts:
        if "test" in part.lower():
            return True
    return False


def collect_snapshot_files(code_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for root, dirs, filenames in os.walk(code_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            file_path = Path(root) / filename
            relative_path = file_path.relative_to(code_dir)
            if should_skip_snapshot_path(relative_path):
                continue
            try:
                files[str(relative_path)] = file_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"Fehler beim Lesen von {file_path}: {e}")
    return files


def find_iteration_dirs(refactored_root: Path) -> list[Path]:
    iteration_dirs: list[Path] = []
    for root, dirs, _files in os.walk(refactored_root):
        for directory in dirs:
            if directory.startswith(ITERATION_PREFIX):
                iteration_dirs.append(Path(root) / directory)
    iteration_dirs.sort()
    return iteration_dirs


def ensure_within_root(root: Path, target: Path) -> Path:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Ungültiger Ergebnis-Pfad außerhalb von {root_resolved}") from exc
    return target_resolved


def resolve_pytest_cwd(project_src: Path) -> Path:
    if (project_src / "pyproject.toml").exists() or (project_src / "tox.ini").exists():
        return project_src
    if (project_src.parent / "pyproject.toml").exists() or (
        project_src.parent / "tox.ini"
    ).exists():
        return project_src.parent
    return project_src


def process_iteration(
    iteration_dir: Path,
    project_src: Path,
    results_root: Path,
    backup_dir: Path,
) -> tuple[bool, str]:
    code_dir = iteration_dir / "code"
    result_dir = ensure_within_root(results_root, results_root / iteration_dir.name)

    if not code_dir.exists():
        test_result = {"stdout": "", "stderr": "", "returncode": -1, "success": False}
        save_iteration_single_file(
            result_dir,
            test_result,
            "FAILURE",
            note=f"Code-Verzeichnis fehlt: {code_dir}",
        )
        return False, format_summary_line(iteration_dir.name, False)

    snapshot_files = collect_snapshot_files(code_dir)
    if not snapshot_files:
        test_result = {"stdout": "", "stderr": "", "returncode": -1, "success": False}
        save_iteration_single_file(
            result_dir,
            test_result,
            "FAILURE",
            note=f"Keine Python-Dateien in {code_dir}",
        )
        return False, format_summary_line(iteration_dir.name, False)

    backup_project(project_src, backup_dir)
    try:
        apply_changes(project_src, snapshot_files)
        pytest_cwd = resolve_pytest_cwd(project_src)
        test_result = run_pytest(pytest_cwd)
    finally:
        restore_project(backup_dir, project_src)

    success = bool(test_result.get("success"))
    status = "SUCCESS" if success else "FAILURE"
    save_iteration_single_file(result_dir, test_result, status)
    return success, format_summary_line(iteration_dir.name, success)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pytest for refactored snapshots")
    parser.add_argument(
        "--project-src",
        type=Path,
        default=PROJECT_SRC_PATH,
        help="Pfad zum Projekt-Quellverzeichnis mit Tests",
    )
    parser.add_argument(
        "--refactored-root",
        type=Path,
        default=REFACTORED_ROOT_PATH,
        help="Pfad zum Ordner mit iteration_XX Verzeichnissen",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=TEST_RESULTS_ROOT,
        help="Pfad zum Ausgabeordner test_results",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_src = args.project_src.resolve()
    refactored_root = args.refactored_root.resolve()
    results_root = args.results_root.resolve()

    results_root.mkdir(parents=True, exist_ok=True)
    backup_dir = ensure_within_root(results_root, results_root / "_backup")

    iteration_dirs = find_iteration_dirs(refactored_root)
    if not iteration_dirs:
        write_text_file(
            ensure_within_root(results_root, results_root / SUMMARY_FILENAME),
            f"Keine iteration_XX Ordner gefunden in {refactored_root}\n",
        )
        return

    summary_lines: list[str] = []
    for iteration_dir in iteration_dirs:
        _success, line = process_iteration(iteration_dir, project_src, results_root, backup_dir)
        summary_lines.append(line)

    write_text_file(
        ensure_within_root(results_root, results_root / SUMMARY_FILENAME),
        "\n".join(summary_lines) + "\n",
    )


if __name__ == "__main__":
    main()
