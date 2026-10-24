"""
Main script to run all resource collection scrapers for SupremeAI
"""

import sys
from pathlib import Path

# Add the current directory to sys.path to import the scrapers
sys.path.append(str(Path(__file__).parent))


def main():
    """Main function to run all scrapers"""
    print("Starting SupremeAI resource collection...")

    # Import and run each scraper
    scrapers = [
        ("awesome-selfhosted", "awesome_selfhosted"),
        ("awesome-go", "awesome_go"),
        ("awesome-python", "awesome_python")
    ]

    results = []

    for name, module_name in scrapers:
        print(f"\n{'='*50}")
        print(f"Running {name} scraper...")
        print(f"{'='*50}")

        try:
            # Import the module dynamically
            module = __import__(module_name)
            # Call the main function and capture the return code
            result = module.main()
            results.append((name, result))

            if result == 0:
                print(f"[SUCCESS] {name} scraper completed successfully")
            else:
                print(f"[ERROR] {name} scraper failed with exit code {result}")

        except Exception as e:
            print(f"[ERROR] {name} scraper failed with exception: {e}")
            results.append((name, 1))

    # Summary
    print(f"\n{'='*50}")
    print("SCRAPING SUMMARY")
    print(f"{'='*50}")

    successful = sum(1 for _, result in results if result == 0)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result == 0 else "[FAIL]"
        print(f"{status}: {name}")

    print(f"\nTotal: {successful}/{total} scrapers successful")

    if successful == total:
        print("SUCCESS: All scrapers completed successfully!")
        return 0
    else:
        print("ERROR: Some scrapers failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
