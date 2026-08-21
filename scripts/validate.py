import compileall
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_command(
    command: list[str],
    name: str,
) -> bool:

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
    )

    if result.returncode == 0:
        print(f"      ✓ {name}")
        return True

    print(f"      ✗ {name}")
    return False


def main():

    print()
    print("=" * 60)
    print("             MyImpact AI Build Validation")
    print("=" * 60)
    print()

    # --------------------------------------------------
    # 1. Python Syntax
    # --------------------------------------------------

    print("[1/4] Python Syntax")

    success = compileall.compile_dir(
        str(PROJECT_ROOT / "app"),
        quiet=1,
    )

    if not success:
        print("      ✗ Python syntax validation failed")
        print()
        print("❌ BUILD FAILED")
        sys.exit(1)

    print("      ✓ All Python files compiled successfully")
    print()

    # --------------------------------------------------
    # 2. Static Analysis
    # --------------------------------------------------

    print("[2/4] Static Analysis")

    ruff_command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "app",
        "tests",
    ]

    result = subprocess.run(
        ruff_command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:

        print("      ⚠ Ruff issues detected")
        print("      🔧 Attempting automatic fixes...")

        fix_command = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "app",
            "tests",
            "--fix",
        ]

        subprocess.run(
            fix_command,
            cwd=PROJECT_ROOT,
        )

        result = subprocess.run(
            ruff_command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:

        print("      ✗ Static analysis failed")

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        print()
        print("❌ BUILD FAILED")
        sys.exit(1)

    print("      ✓ Ruff lint checks passed")
    print("      ✓ Import checks passed")
    print("      ✓ Undefined-name checks passed")
    print("      ✓ Code-quality checks passed")
    print()

    # --------------------------------------------------
    # 3. Application Import
    # --------------------------------------------------

    print("[3/4] Application Import")

    import_command = [
        sys.executable,
        "-c",
        "from app.main import app",
    ]

    result = subprocess.run(
        import_command,
        cwd=PROJECT_ROOT,
    )

    if result.returncode != 0:

        print("      ✗ FastAPI application import failed")
        print()
        print("❌ BUILD FAILED")
        sys.exit(1)

    print("      ✓ FastAPI application loaded successfully")
    print()

    # --------------------------------------------------
    # 4. Build Status
    # --------------------------------------------------

    print("[4/4] Build Status")
    print("      ✓ BUILD PASSED")
    print()

    print("=" * 60)
    print("           MyImpact AI BUILD SUCCESSFUL")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()