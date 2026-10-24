import json
import re
import urllib.error
import urllib.request


def fetch_readme():
    url = "https://raw.githubusercontent.com/awesome-selfhosted/awesome-selfhosted/master/README.md"
    try:
        with urllib.request.urlopen(url) as response:
            return response.read().decode('utf-8')
    except urllib.error.URLError as e:
        print(f"Failed to fetch README: {e}")
        return None

def parse_readme(content):
    lines = content.split('\n')
    categories = {}
    current_category = None

    for line in lines:
        # Check for category heading (## Category Name)
        if line.startswith('## '):
            current_category = line[3:].strip()
            categories[current_category] = []
        # Check for list item that looks like: - [name](url) - description
        elif current_category and line.strip().startswith('- ['):
            # Extract the part between - [ and ]
            match = re.match(r'\s*-\s*\[([^\]]+)\]\(([^)]+)\)\s*-\s*(.+)', line.strip())
            if match:
                name, url, description = match.groups()
                categories[current_category].append({
                    "name": name.strip(),
                    "url": url.strip(),
                    "description": description.strip()
                })
            else:
                # Try without description
                match = re.match(r'\s*-\s*\[([^\]]+)\]\(([^)]+)\)', line.strip())
                if match:
                    name, url = match.groups()
                    categories[current_category].append({
                        "name": name.strip(),
                        "url": url.strip(),
                        "description": ""
                    })

    # Remove empty categories
    categories = {k: v for k, v in categories.items() if v}
    return categories

def main():
    print("Fetching awesome-selfhosted README...")
    content = fetch_readme()
    if content is None:
        return

    print("Parsing README...")
    data = parse_readme(content)

    # Save to JSON file
    output_file = "awesome_selfhosted.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Successfully scraped {len(data)} categories.")
    print(f"Data saved to {output_file}")

if __name__ == "__main__":
    main()
