#!/usr/bin/env python3
"""Recheck recorded CLI outcomes and generate derived simulation charts."""
import argparse
import json
from pathlib import Path

from experiment_data import load_run, sha256, write_analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists() or args.out.is_symlink():
        parser.error("output exists; choose a new directory")
    source = args.run.resolve()
    if args.out.resolve() == source or source in args.out.resolve().parents:
        parser.error("derived output must be outside the recorded run")
    try:
        _, records = load_run(source)
        write_analysis(records, args.out)
        (args.out / "provenance.json").write_text(json.dumps({
            "input_run": source.name,
            "metadata_sha256": sha256(source / "metadata.json"),
            "records_sha256": sha256(source / "records.json"),
            "analysis_unit": "deterministic policy outcome for one fixed workload/options tuple",
            "host_runtime_measured": False
        }, indent=2) + "\n")
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(f"Revalidated 116 simulated cases; wrote {args.out}")


if __name__ == "__main__":
    main()
