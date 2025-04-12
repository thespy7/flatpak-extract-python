# flatpak-extract
a CLI app for extracting .flatpak files
```
usage: flatpak-extract [-h] [--outdir OUTDIR] [--tmpdir TMPDIR] filename

Extracts a .flatpak file.

positional arguments:
  filename         Path to the input .flatpak file.

options:
  -h, --help       show this help message and exit
  --outdir OUTDIR  Directory to write the content into. (has default)
  --tmpdir TMPDIR  Temporary directory for the OSTree repository. (has default)
```
