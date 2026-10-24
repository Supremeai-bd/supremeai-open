import csv


def run(data: list, filepath: str):
    """Exports a list of dicts to a CSV file."""
    if not data or not isinstance(data, list):
        return {
            "success": False,
            "error": "Invalid data format. Expected list of dicts.",
        }

    try:
        keys = data[0].keys()
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(data)
        return {"success": True, "filepath": filepath, "rows_exported": len(data)}
    except Exception as e:
        return {"success": False, "error": str(e)}
