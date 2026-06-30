#!/usr/bin/env python3
"""fenrir — FileChanged: reactive IaC/manifest validation.

Non-blocking. When a watched IaC/Helm/manifest file changes on disk, run a FAST sanity
check (terraform fmt-check for .tf, YAML parse for manifests) and print a one-line result
so drift/typos surface immediately. Degrades silently if the tool isn't installed.
Wire in settings.json FileChanged. NOTE: FileChanged `matcher` takes LITERAL basenames
(pipe-separated, e.g. "main.tf|variables.tf|outputs.tf"), NOT globs — `*.tf` would match
only a file literally named `*.tf`. List the manifest filenames you want watched.
Pure stdlib (+ optional terraform if present).
"""
import json
import os
import subprocess
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    fp = data.get("file_path", "") or ""
    if not fp or not os.path.exists(fp):
        sys.exit(0)
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    if fp.endswith(".tf"):
        try:
            r = subprocess.run(["terraform", "fmt", "-check", "-diff", fp],
                               cwd=root, capture_output=True, text=True, timeout=15)
            if r.returncode != 0 and r.stdout.strip():
                print(f"iac-watch: {fp} is not terraform-fmt clean — run `terraform fmt`.")
        except FileNotFoundError:
            pass
        except Exception:
            pass
    elif fp.endswith((".yaml", ".yml")):
        try:
            import yaml
            with open(fp) as f:
                list(yaml.safe_load_all(f))
        except ImportError:
            pass
        except Exception as e:
            print(f"iac-watch: {fp} has a YAML error: {str(e)[:160]}")
    sys.exit(0)


if __name__ == "__main__":
    main()
