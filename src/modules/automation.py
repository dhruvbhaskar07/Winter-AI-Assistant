import os
import shutil


DOWNLOADS_PATH = os.path.expanduser("~/Downloads")


def _safe_destination_path(dest_folder, filename):
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_folder, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dest_folder, f"{base}_{counter}{ext}")
        counter += 1
    return candidate


def organize_downloads():
    if not os.path.exists(DOWNLOADS_PATH):
        return "Downloads folder not found"

    file_types = {
        "Images": [".png", ".jpg", ".jpeg"],
        "Documents": [".pdf", ".docx", ".txt"],
        "Videos": [".mp4", ".mkv"],
        "Others": [],
    }

    for file in os.listdir(DOWNLOADS_PATH):
        file_path = os.path.join(DOWNLOADS_PATH, file)

        if os.path.isdir(file_path):
            continue

        moved = False

        for folder, extensions in file_types.items():
            if any(file.lower().endswith(ext) for ext in extensions):
                dest_folder = os.path.join(DOWNLOADS_PATH, folder)
                os.makedirs(dest_folder, exist_ok=True)

                shutil.move(file_path, _safe_destination_path(dest_folder, file))
                moved = True
                break

        if not moved:
            dest_folder = os.path.join(DOWNLOADS_PATH, "Others")
            os.makedirs(dest_folder, exist_ok=True)
            shutil.move(file_path, _safe_destination_path(dest_folder, file))

    return "Downloads organized successfully"


def create_folder(folder_name, base_path="."):
    path = os.path.join(base_path, folder_name)
    os.makedirs(path, exist_ok=True)
    return f"Folder created: {path}"


def rename_file(old_name, new_name):
    if not os.path.exists(old_name):
        return "File not found"

    os.rename(old_name, new_name)
    return f"Renamed to {new_name}"
