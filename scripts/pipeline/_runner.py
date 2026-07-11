"""Shared script execution engine for pipelines."""

import json
import os
import subprocess
import sys

# pipeline/_runner.py -> pipeline/ -> scripts/
SCRIPTS_DIR = os.path.dirname(os.path.dirname(__file__))


def _run_script(script_path, args_list, timeout=60):
	"""Run a child CLI and preserve its JSON document even on exit code 1."""
	full_path = os.path.join(SCRIPTS_DIR, script_path)
	cmd = [sys.executable, full_path] + args_list

	try:
		result = subprocess.run(
			cmd,
			capture_output=True,
			text=True,
			timeout=timeout,
			cwd=SCRIPTS_DIR,
		)
		stdout = result.stdout.strip()
		if stdout:
			try:
				payload = json.loads(stdout)
			except json.JSONDecodeError:
				return {
					"error": "Invalid JSON output from script",
					"exit_code": result.returncode,
					"stderr": result.stderr.strip() or None,
				}
			# A valid child JSON document is the contract, even on exit 1. Returning
			# it byte-for-structure preserves nested errors and source provenance.
			return payload
		return {
			"error": result.stderr.strip() or "Script returned no output",
			"exit_code": result.returncode,
		}
	except subprocess.TimeoutExpired:
		return {"error": f"Script timed out ({timeout}s)"}
	except Exception as e:
		return {"error": str(e)}
