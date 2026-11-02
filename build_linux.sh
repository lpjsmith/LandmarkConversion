#!/usr/bin/env bash
# Build the Linux apps into dist/linux/:
#   landmark-converter      GUI (drag & drop window; also accepts files as arguments)
#   landmark-convert        command-line converter
# Usage:  bash build_linux.sh            (run from the repo root, in an env with requirements.txt installed)
#         bash build_linux.sh --install  (also add it to your app menu: ~/.local/bin + ~/.local/share/applications)
set -euo pipefail
cd "$(dirname "$0")"
OUT=dist/linux
mkdir -p "$OUT"
cp "$0" "$OUT/"
echo "$(date -Iseconds)  bash $0 $*" >> "$OUT/run_command.txt"

python -m PyInstaller --noconfirm --onefile --windowed --name landmark-converter \
    --collect-all tkinterdnd2 --distpath "$OUT" --workpath build/linux-gui --specpath build/linux-gui \
    landmark_convert_gui.py
python -m PyInstaller --noconfirm --onefile --console --name landmark-convert \
    --distpath "$OUT" --workpath build/linux-cli --specpath build/linux-cli \
    landmark_convert.py
cp landmark_convert.py landmark_convert_gui.py "$OUT/"

if [[ "${1:-}" == "--install" ]]; then
    mkdir -p ~/.local/bin ~/.local/share/applications
    cp "$OUT/landmark-converter" "$OUT/landmark-convert" ~/.local/bin/
    sed "s|@BIN@|$HOME/.local/bin/landmark-converter|" packaging/landmark-converter.desktop \
        > ~/.local/share/applications/landmark-converter.desktop
    update-desktop-database ~/.local/share/applications 2>/dev/null || true
    echo "Installed: ~/.local/bin/landmark-converter (+ app menu entry 'Landmark Converter')"
fi
echo "Built: $OUT/landmark-converter  $OUT/landmark-convert"
