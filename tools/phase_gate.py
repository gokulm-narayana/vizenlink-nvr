"""Phase gate execution tool for local validation across all checks (D-30, FND-04, FND-05)."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence


def run_command(
    cmd: Sequence[str],
    desc: str,
    env: dict[str, str] | None = None,
) -> bool:
    """Run a subprocess command with list args and shell=False, printing status."""
    sys.stdout.write(f"==> {desc} ... ")
    sys.stdout.flush()

    res = subprocess.run(  # noqa: S603
        cmd,
        shell=False,
        env=env,
        capture_output=True,
        text=True,
    )

    if res.returncode == 0:
        print("PASS")
        return True

    print("FAIL")
    if res.stdout.strip():
        print("--- stdout ---")
        print(res.stdout.strip())
    if res.stderr.strip():
        print("--- stderr ---")
        print(res.stderr.strip())
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 01 / Phase 02 / Phase 03 local gate verification")
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue running subsequent checks after a failure",
    )
    args = parser.parse_args()

    steps_passed = 0
    total_steps = 10

    # 1. Default pytest suite
    ok1 = run_command(["uv", "run", "pytest", "-q"], "Step 1/10: Default pytest suite")
    if not ok1 and not args.keep_going:
        sys.exit(1)
    if ok1:
        steps_passed += 1

    # 2. Fetch MediaMTX binary
    ok2 = run_command(
        ["uv", "run", "python", "tools/fetch_mediamtx.py"],
        "Step 2/10: Fetch MediaMTX binary",
    )
    if not ok2 and not args.keep_going:
        sys.exit(1)
    if ok2:
        steps_passed += 1

    # 3. MediaMTX integration tests
    ok3 = run_command(
        ["uv", "run", "pytest", "-m", "mediamtx", "-q"],
        "Step 3/10: MediaMTX integration tests",
    )
    if not ok3 and not args.keep_going:
        sys.exit(1)
    if ok3:
        steps_passed += 1

    # 4. Drift check self
    ok4 = run_command(
        ["uv", "run", "python", "tools/drift_check.py", "--self"],
        "Step 4/10: Drift check against camera_api.lock.json",
    )
    if not ok4 and not args.keep_going:
        sys.exit(1)
    if ok4:
        steps_passed += 1

    # 5. Alembic upgrade head and alembic check on temporary database
    tmp_data_dir = tempfile.mkdtemp(prefix="nvr-phase-gate-")
    alembic_env = dict(os.environ)
    alembic_env["NVR_DATA_DIR"] = tmp_data_dir
    alembic_env["NVR_SECRETS_BACKEND"] = "file"

    try:
        ok5_up = run_command(
            ["uv", "run", "alembic", "upgrade", "head"],
            "Step 5/10a: Alembic upgrade head on temporary database",
            env=alembic_env,
        )
        ok5_chk = False
        if ok5_up or args.keep_going:
            ok5_chk = run_command(
                ["uv", "run", "alembic", "check"],
                "Step 5/10b: Alembic schema drift check",
                env=alembic_env,
            )
        ok5 = ok5_up and ok5_chk
    finally:
        shutil.rmtree(tmp_data_dir, ignore_errors=True)

    if not ok5 and not args.keep_going:
        sys.exit(1)
    if ok5:
        steps_passed += 1

    # 6. Headless recording core tracer & CLI password safety check
    ok6 = run_command(
        [
            "uv",
            "run",
            "pytest",
            "tests/integration/test_headless_recording_pipeline.py",
            "tests/integration/test_fmp4_recording.py",
            "tests/unit/test_cli_password_options.py",
            "-q",
        ],
        "Step 6/10: Recording core pipeline tracer & password safety check",
    )
    if not ok6 and not args.keep_going:
        sys.exit(1)
    if ok6:
        steps_passed += 1

    # 7. Ruff check
    ok7 = run_command(
        ["uv", "run", "ruff", "check", "--exclude", "contracts", "."],
        "Step 7/10: Ruff linter check",
    )
    if not ok7 and not args.keep_going:
        sys.exit(1)
    if ok7:
        steps_passed += 1

    # 8. Mypy type check
    ok8 = run_command(["uv", "run", "mypy", "src"], "Step 8/10: Mypy type check")
    if not ok8 and not args.keep_going:
        sys.exit(1)
    if ok8:
        steps_passed += 1

    # 9. OpenAPI 3.1 breaking change detector
    ok9 = run_command(
        ["uv", "run", "python", "tools/check_api_breaking_changes.py"],
        "Step 9/10: OpenAPI 3.1 breaking change guard",
    )
    if not ok9 and not args.keep_going:
        sys.exit(1)
    if ok9:
        steps_passed += 1

    # 10. Phase 3 end-to-end pipeline tracer
    ok10 = run_command(
        ["uv", "run", "pytest", "tests/integration/test_phase3_tracer.py", "-q"],
        "Step 10/10: Phase 3 end-to-end pipeline tracer",
    )
    if not ok10 and not args.keep_going:
        sys.exit(1)
    if ok10:
        steps_passed += 1

    print(f"\nPhase Gate Result: {steps_passed}/{total_steps} steps passed.")
    if steps_passed != total_steps:
        sys.exit(1)


if __name__ == "__main__":
    main()
