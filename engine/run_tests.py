"""Run every engine module's built-in self-test in one shot.

Each engine/*.py module is independently runnable and exits non-zero on a
failed assertion (see the `if __name__ == "__main__":` block in each
file). This script just executes them all as subprocesses and prints a
pass/fail summary -- no test framework dependency.
"""

import os
import subprocess
import sys

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
SKIP = {"run_tests.py", "run_match.py"}


def main():
    modules = sorted(
        f for f in os.listdir(ENGINE_DIR)
        if f.endswith(".py") and f not in SKIP
    )
    failures = []
    for module in modules:
        path = os.path.join(ENGINE_DIR, module)
        result = subprocess.run([sys.executable, path], capture_output=True, text=True)
        status = "PASS" if result.returncode == 0 else "FAIL"
        print(f"[{status}] {module}")
        if result.returncode != 0:
            failures.append(module)
            print(result.stdout[-2000:])
            print(result.stderr[-2000:])

    print()
    if failures:
        print(f"{len(failures)}/{len(modules)} modules FAILED: {', '.join(failures)}")
        sys.exit(1)
    print(f"All {len(modules)} modules passed.")


if __name__ == "__main__":
    main()
