#!/usr/bin/env python3
"""Build benschomp.com and upload it to DreamHost.

The site is assembled in _site/ from two sources:
  1. The files tracked in this repo (see .gitignore for which pages those are).
  2. The projects listed in projects.json. Each lives in its own repo and is
     cloned at its git_ref (a branch for the latest work, or a tag to pin a
     version), built, and copied to its publish_path (for example Yoshi vs.
     Monsters goes to /yoshi/).

Uploading only ever adds or updates the files in _site/. It never deletes
anything on the server, so the rest of the DreamHost folder is left alone.

Usage:
  python3 deploy.py build                         # assemble _site/ (clones projects from GitHub)
  python3 deploy.py build --use-local-clones      # use your own clones (local_clone_path) instead,
                                                  # to preview work in progress
  python3 -m http.server --directory _site        # preview at http://localhost:8000
  python3 deploy.py upload --dry-run              # list what would change on the server
  python3 deploy.py upload                        # build, then upload

Upload settings come from environment variables:
  DEPLOY_SSH_TARGET   user@host, for example ben@benschomp.com's DreamHost server
  DEPLOY_REMOTE_PATH  folder on the server, for example benschomp.com/
                      (with an rrsync-restricted key, use ./)
  DEPLOY_SSH_KEY_FILE optional private key file for ssh
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT_FOLDER = Path(__file__).resolve().parent
ASSEMBLED_SITE_FOLDER = REPO_ROOT_FOLDER / "_site"
PROJECTS_MANIFEST_FILE = REPO_ROOT_FOLDER / "projects.json"


def run_shell_command(command, working_folder):
    print(f"  $ {command}", flush=True)
    subprocess.run(command, shell=True, cwd=working_folder, check=True)


def list_files_tracked_by_git():
    git_output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT_FOLDER, check=True, capture_output=True
    ).stdout.decode()
    return [relative_path for relative_path in git_output.split("\0") if relative_path]


def copy_tracked_site_files(files_that_are_not_site_pages):
    for relative_path in list_files_tracked_by_git():
        if relative_path in files_that_are_not_site_pages or relative_path.startswith(".github/"):
            continue
        source_path = REPO_ROOT_FOLDER / relative_path
        destination_path = ASSEMBLED_SITE_FOLDER / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_symlink():
            destination_path.symlink_to(os.readlink(source_path))
        else:
            shutil.copy2(source_path, destination_path)


def validate_publish_path(project, tracked_top_level_names):
    publish_path = project["publish_path"]
    if not publish_path or "/" in publish_path or publish_path.startswith(".") or "\\" in publish_path:
        raise ValueError(f'{project["name"]}: publish_path must be one plain folder name, got "{publish_path}"')
    if publish_path in tracked_top_level_names:
        raise ValueError(f'{project["name"]}: publish_path "{publish_path}" collides with a file or folder in this repo')


def build_project(project, use_local_clones, temporary_clones_folder):
    if use_local_clones:
        project_source_folder = Path(project["local_clone_path"]).expanduser()
        if not project_source_folder.is_dir():
            raise FileNotFoundError(f"No local clone at {project_source_folder}")
        print(f"  using local clone {project_source_folder}")
    else:
        project_source_folder = Path(temporary_clones_folder) / Path(project["local_clone_path"]).name
        run_shell_command(
            f'git -c advice.detachedHead=false clone --quiet --depth 1 --branch {project["git_ref"]} {project["git_url"]} "{project_source_folder}"',
            temporary_clones_folder,
        )
    if project.get("install_command"):
        run_shell_command(project["install_command"], project_source_folder)
    if project.get("build_command"):
        run_shell_command(project["build_command"], project_source_folder)
    build_output_folder = project_source_folder / project["build_output_folder"]
    if not build_output_folder.is_dir():
        raise FileNotFoundError(f"Build finished but {build_output_folder} does not exist")
    shutil.copytree(
        build_output_folder,
        ASSEMBLED_SITE_FOLDER / project["publish_path"],
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", ".gitignore"),
    )


def build_site(use_local_clones):
    """Assemble _site/. Returns the names of projects that failed to build."""
    if ASSEMBLED_SITE_FOLDER.exists():
        shutil.rmtree(ASSEMBLED_SITE_FOLDER)
    ASSEMBLED_SITE_FOLDER.mkdir()

    files_that_are_not_site_pages = {".gitignore", "deploy.py", "projects.json", "README.md"}
    copy_tracked_site_files(files_that_are_not_site_pages)
    tracked_top_level_names = {path.split("/")[0] for path in list_files_tracked_by_git()}

    projects = json.loads(PROJECTS_MANIFEST_FILE.read_text())["projects"]
    names_of_failed_projects = []
    with tempfile.TemporaryDirectory(prefix="benschomp-projects-") as temporary_clones_folder:
        for project in projects:
            print(f'\n== {project["name"]} -> /{project["publish_path"]}/', flush=True)
            validate_publish_path(project, tracked_top_level_names)
            try:
                build_project(project, use_local_clones, temporary_clones_folder)
            except (subprocess.CalledProcessError, FileNotFoundError) as build_error:
                print(f"  FAILED, skipping (the live copy stays as it is): {build_error}", flush=True)
                names_of_failed_projects.append(project["name"])
    print(f"\nAssembled site in {ASSEMBLED_SITE_FOLDER}")
    return names_of_failed_projects


def upload_site(dry_run):
    ssh_target = os.environ.get("DEPLOY_SSH_TARGET")
    remote_path = os.environ.get("DEPLOY_REMOTE_PATH")
    if not ssh_target or not remote_path:
        raise SystemExit("Set DEPLOY_SSH_TARGET (user@host) and DEPLOY_REMOTE_PATH (for example benschomp.com/) first.")
    ssh_command = "ssh -o StrictHostKeyChecking=accept-new"
    if os.environ.get("DEPLOY_SSH_KEY_FILE"):
        ssh_command += f' -i {os.environ["DEPLOY_SSH_KEY_FILE"]}'
    rsync_command = [
        "rsync",
        "--recursive", "--links", "--checksum", "--itemize-changes",
        "--chmod=D755,F644",
        "-e", ssh_command,
        # No --delete, ever: files on the server that aren't in _site/ are left alone.
        f"{ASSEMBLED_SITE_FOLDER}/",
        f"{ssh_target}:{remote_path}",
    ]
    if dry_run:
        rsync_command.insert(1, "--dry-run")
        print("Dry run: nothing will be uploaded.")
    subprocess.run(rsync_command, check=True)


def main():
    argument_parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    argument_parser.add_argument("action", choices=["build", "upload"])
    argument_parser.add_argument("--use-local-clones", action="store_true", help="build each project from its local_clone_path instead of cloning it")
    argument_parser.add_argument("--dry-run", action="store_true", help="with upload: show what would change without uploading")
    arguments = argument_parser.parse_args()

    names_of_failed_projects = build_site(arguments.use_local_clones)
    if arguments.action == "upload":
        upload_site(arguments.dry_run)
    if names_of_failed_projects:
        sys.exit("These projects failed to build and were not updated: " + ", ".join(names_of_failed_projects))


if __name__ == "__main__":
    main()
