import os
import shutil

from core.logging_config import logger


class PlanSorter:
    def __init__(self, admin_plan_dir: str | None = None, output_dir: str | None = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.admin_plan_dir = admin_plan_dir or os.path.join(base_dir, "document", "admin's_plan")
        self.output_dir = output_dir or os.path.join(base_dir, "document")
        os.makedirs(self.admin_plan_dir, exist_ok=True)

    def sort_and_organize_plans(self) -> dict[str, list[str]]:
        """Scans the inbox folder and categorizes plans based on keywords."""
        categorized: dict[str, list[str]] = {"Urgent": [], "Feature": [], "Bug": []}

        if not os.path.exists(self.admin_plan_dir):
            return categorized

        for filename in os.listdir(self.admin_plan_dir):
            file_path = os.path.join(self.admin_plan_dir, filename)
            if os.path.isfile(file_path) and filename.endswith(".md"):
                try:
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read().lower()

                    # Determine category
                    if "urgent" in content or "critical" in content or "asap" in content:
                        category = "Urgent"
                    elif "bug" in content or "fix" in content or "error" in content:
                        category = "Bug"
                    else:
                        category = "Feature"

                    categorized[category].append(filename)

                    # Move to appropriate subfolder (e.g. status_and_tracking or plans_and_guides)
                    dest_subfolder = (
                        "status_and_tracking"
                        if category in ("Urgent", "Bug")
                        else "plans_and_guides"
                    )
                    dest_dir = os.path.join(self.output_dir, dest_subfolder)
                    os.makedirs(dest_dir, exist_ok=True)

                    # Copy to structured folder while keeping original in admin's_plan intact per rules
                    shutil.copy(
                        file_path,
                        os.path.join(dest_dir, f"sorted_{category.lower()}_{filename}"),
                    )
                    logger.info(f"Organized plan '{filename}' as {category} -> {dest_subfolder}")
                except Exception as e:
                    logger.error(f"Failed to process plan file '{filename}': {e}")

        return categorized
