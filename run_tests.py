#!/usr/bin/env python3
"""
Script to run tests for the CMPDI/CIL AI Reporting Platform.
"""
import subprocess
import sys
import os

def run_tests():
    """Run the test suite."""
    print("Running tests for CMPDI/CIL AI Reporting Platform...")

    # Change to the project directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Run pytest with verbose output
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short"
    ], capture_output=True, text=True)

    print("STDOUT:")
    print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    print(f"Return code: {result.returncode}")

    if result.returncode == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")

    return result.returncode

if __name__ == "__main__":
    sys.exit(run_tests())