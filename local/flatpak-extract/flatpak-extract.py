#!/usr/bin/env python3

import argparse
import subprocess
import sys
import os
import shutil
import uuid
from pathlib import Path

def run_command(cmd_list, description="command"):
    """Runs a command, checks for errors, and prints output."""
    print(f"⏳ {' '.join(cmd_list)}")
    try:
        result = subprocess.run(
            cmd_list,
            check=True,          # Raise CalledProcessError on non-zero exit
            text=True,           # Decode stdout/stderr as text
            capture_output=True, # Capture stdout/stderr
        )
        if result.stdout:
            print("Stdout:\n", result.stdout.strip())
        if result.stderr:
            print("Stderr:\n", result.stderr.strip())
        return True
    except FileNotFoundError:
        print(f"Error: Command '{cmd_list[0]}' not found.", file=sys.stderr)
        print("Please ensure 'ostree' is installed and in your PATH.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: {description} failed with exit code {e.returncode}", file=sys.stderr)
        if e.stdout:
            print("Stdout:\n", e.stdout.strip(), file=sys.stderr)
        if e.stderr:
            print("Stderr:\n", e.stderr.strip(), file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error occurred while running {description}: {e}", file=sys.stderr)
        return False

def find_commit_hash(repo_dir: Path) -> str | None:
    """
    Finds the commit hash by locating the .commit file in the repo's objects.
    The hash is derived from the parent directory name and the filename (without extension).
    Example: objects/ab/cdef123...commit -> abcdef123...
    """
    objects_dir = repo_dir / "objects"
    if not objects_dir.is_dir():
        print(f"Error: Objects directory not found: {objects_dir}", file=sys.stderr)
        return None

    commit_files = list(objects_dir.rglob('*.commit'))

    if not commit_files:
        print(f"Error: No .commit file found under {objects_dir}", file=sys.stderr)
        return None

    if len(commit_files) > 1:
        print(f"Warning: Found multiple .commit files, using the first one: {commit_files[0]}", file=sys.stderr)

    commit_file_path = commit_files[0]
    commit_filename_stem = commit_file_path.stem # Filename without extension
    parent_dir_name = commit_file_path.parent.name # Immediate parent dir name (e.g., 'ab')

    commit_hash = parent_dir_name + commit_filename_stem
    return commit_hash


def list_files(startpath: Path, prefix: str = ''):
    """Recursively lists directory contents by printing their paths.

    Paths are printed without indentation. If startpath is a directory or
    file located directly within the current working directory (CWD),
    prints paths relative to the CWD, prefixed with './'. Otherwise,
    prints absolute paths.

    Note that startpath should be a full path, not a relative path initially.

    Args:
        startpath (Path): The absolute path to the directory or file to start
                          listing from.
        prefix (str, optional): A string to prepend to every printed line.
                                Defaults to ''.
    """
    try:
        # Resolve the path to get a canonical absolute path and check existence
        # strict=True will raise FileNotFoundError if the path doesn't exist
        startpath = startpath.resolve(strict=True)
        cwd = Path.cwd()
    except FileNotFoundError:
        print(f"{prefix}Error: Start path '{startpath}' not found.")
        return
    except PermissionError:
         print(f"{prefix}Error: Permission denied for start path '{startpath}'.")
         return
    except Exception as e:
        # Catch other potential errors during path resolution
        print(f"{prefix}Error resolving start path '{startpath}': {e}")
        return

    # Determine if startpath is a direct child of the current working directory
    # Note: startpath itself could be the CWD if startpath == cwd
    # We only want relative paths if startpath is *strictly within* CWD's top level.
    use_relative = (startpath.parent == cwd)

    # We can use a stack for an iterative approach or stick to recursion
    # Recursion is often conceptually simpler for directory traversal
    queue = [startpath] # Start with the initial path

    while queue:
        current_path = queue.pop(0) # Process paths in BFS-like order (FIFO)
                                    # Use queue.pop() for DFS-like order (LIFO)

        # Determine the path string representation first
        try:
            if use_relative:
                # Calculate path relative to CWD
                # Check if the path is actually *under* CWD before making relative
                # This handles cases where startpath itself is CWD, but subdirs aren't direct children
                if current_path.is_relative_to(cwd):
                    relative_p = current_path.relative_to(cwd)
                     # Ensure './' prefix only if it's not the CWD itself represented as '.'
                    if str(relative_p) == '.':
                         path_str = '.' # Or perhaps './.' depending on desired style
                    else:
                         path_str = f"./{relative_p}"
                else:
                    # If somehow a path during recursion is outside CWD, print absolute
                    path_str = str(current_path.resolve()) # Ensure absolute if not relative
            else:
                # Use the absolute path
                path_str = str(current_path) # Already resolved earlier

        except Exception as e:
            # Handle errors during path string generation
            print(f"{prefix}Error generating path string for {current_path}: {e}")
            continue # Skip this problematic path

        try:
            # Print the current path with user prefix (NO indentation)
            print(f"{prefix}{path_str}")

            # If it's a directory, add its contents to the queue for processing
            # Check is_dir() *after* printing the directory itself
            if current_path.is_dir():
                try:
                    # Add entries to the beginning of the queue for DFS-like behavior
                    # Add entries to the end of the queue for BFS-like behavior
                    # Sorting ensures consistent order regardless of BFS/DFS choice
                    # Add in reverse sorted order if using pop() for DFS to maintain alpha order processing
                    entries = sorted(current_path.iterdir(), key=lambda p: p.name)
                    # Add to the front for DFS-like processing order similar to recursion
                    queue[0:0] = entries
                    # Alternatively, for BFS-like order:
                    # queue.extend(entries)

                except PermissionError:
                     # Indicate error for this specific directory listing attempt
                     print(f"{prefix}Error: Permission denied listing contents of: {path_str}")
                except Exception as e:
                     print(f"{prefix}Error listing contents of {path_str}: {e}")

        except PermissionError:
             # Handle permission errors checking is_dir or other attributes
             print(f"{prefix}Error: Permission denied accessing properties of: {path_str}")
        except FileNotFoundError:
             # Handle case where file/dir disappears after adding to queue but before processing
             print(f"{prefix}Error: File not found during processing: {path_str}")
        except Exception as e:
            # Catch other potential errors during processing (e.g., is_dir check)
            print(f"{prefix}Error processing {path_str}: {e}")


# --- Main Application Logic ---

def main():
    parser = argparse.ArgumentParser(
        prog = "flatpak-extract",
        description="Extracts a .flatpak file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter # Show defaults in help
    )

    parser.add_argument(
        "filename",
        help="Path to the input .flatpak file.",
        type=str
    )
    parser.add_argument(
        "--outdir",
        help="Directory to write the content into.",
        type=str,
        default="exists" # Default calculated later based on filename
    )
    parser.add_argument(
        "--tmpdir",
        help="Temporary directory for the OSTree repository.",
        type=str,
        default="exists" # Default calculated later
    )

    args = parser.parse_args()

    input_file = Path(args.filename).resolve() # Get absolute path

    if not input_file.is_file():
        print(f"Error: Input file not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    # Calculate default outdir if not provided
    if args.outdir == "exists":
        outdir = Path(f"{input_file.stem}-flatpak").resolve()
    else:
        outdir = Path(args.outdir).resolve()

    # Calculate default tmpdir if not provided
    if args.tmpdir == "exists":
        tmpdir = Path(f"flatpak-extract-{uuid.uuid4()}").resolve()
    else:
        tmpdir = Path(args.tmpdir).resolve()

    # --- Main Processing Steps ---
    commit_hash = None
    success = True

    try:
        if tmpdir.exists():
            print(f"Error: Path for temporary directory already exists: {tmpdir}", file=sys.stderr)
            print("Please remove it or use a different --tmpdir.", file=sys.stderr)
            sys.exit(1)

        if outdir.exists():
            print(f"Error: Path for out directory already exists: {outdir}", file=sys.stderr)
            print("Please remove it or use a different --outdir.", file=sys.stderr)
            sys.exit(1)

        cmd_init = ["ostree", "init", f"--repo={tmpdir}", "--mode=bare-user"]
        if not run_command(cmd_init, "ostree init"):
            success = False; raise SystemExit(1) # Use exception to jump to finally

        cmd_apply = ["ostree", "static-delta", "apply-offline", f"--repo={tmpdir}", str(input_file)]
        if not run_command(cmd_apply, "ostree apply-offline"):
            success = False; raise SystemExit(1)

        commit_hash = find_commit_hash(tmpdir)
        if commit_hash is None:
            print("Error: Could not determine commit hash.", file=sys.stderr)
            success = False; raise SystemExit(1)

        cmd_checkout = ["ostree", "checkout", f"--repo={tmpdir}", "-U", commit_hash, str(outdir)]
        if not run_command(cmd_checkout, "ostree checkout"):
            success = False; raise SystemExit(1)

        # List files in outdir
        print(f"Files extracted:")
        list_files(outdir)
        print("DONE.")

    except SystemExit as e: # Catch SystemExit raised on command failures
         print("\nExtract process failed.", file=sys.stderr)
         sys.exit(e.code) # Propagate the exit code
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        success = False
        sys.exit(1)

    finally:
        # 4. Delete tmpdir (Cleanup)
        if tmpdir.exists():
            try:
                shutil.rmtree(tmpdir)
            except Exception as e:
                print(f"Warning: Failed to remove temporary directory {tmpdir}: {e}", file=sys.stderr)
                print("You may need to remove it manually.", file=sys.stderr)
                if success: # Only exit with error if main process succeeded but cleanup failed
                    sys.exit(1)


if __name__ == "__main__":
    main()

