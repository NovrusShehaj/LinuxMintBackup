#! /usr/bin/env python3

import subprocess
import json
import logging
from datetime import datetime
from pathlib import Path
import sys

CONFIG_PATH = Path.home() / "backup/config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def setup_logging(log_file):
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

def run_backup(sources, destination, exclude):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest_path = Path(destination) / timestamp
    dest_path.mkdir(parents=True, exisit_ok=True)


    cmd = [
        "rsync",
        "-aAx",
        "--delete",
        "--numeric-ids",
        "--link-dest", f"{Path(destination)}/latest"
    ]

    for e in exclude:
        cmd.extend(["--exclude", e])

    cmd.extend(source)
    cmd.append(str(dest_path))

    logging.info("Running rsync command")
    logging.info(" ".join(cmd))

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        logging.error(result.stderr)
        sys.exit(1)

    # Update "latest" symlink
    latest = Path(destination) / "latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(dest_path)

    logging.info("Backup completed sucessfully")

def main():
    config = load_config()
    setup_logging(config["log_file"])
    run_backup(
        config["sources"],
        config["destination"],
        config["exclude"]
    )


if __name__ == "__main__":
    main()

