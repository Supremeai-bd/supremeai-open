OFFICIAL_PLUGINS = [
    {
        "id": "github",
        "name": "GitHub",
        "description": "Connect your GitHub account to manage repositories, issues, and pull requests.",
        "icon_url": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
        "category": "developer",
        "source": "official",
        "auth_type": "oauth",
        "execution_type": "native_adapter",
        "trust_level": "official",
        "tools_provided": [
            {
                "name": "create_pr",
                "description": "Create a pull request",
                "permissions": ["repo.write"],
            },
            {"name": "list_issues", "description": "List issues", "permissions": ["repo.read"]},
        ],
        "auth_schema": {"type": "oauth2", "scopes": ["repo", "user"]},
        "permission_schema": [
            {"name": "repo.read", "description": "Read repositories"},
            {"name": "repo.write", "description": "Write to repositories"},
        ],
    },
]

# Plugins moved to experimental — capability graph must be honest.
# These were previously in official/ but raised NotImplementedError on first tool call.
# See: backend/core/plugins/experimental/*.py
EXPERIMENTAL_PLUGINS = [
    {
        "id": "notion",
        "name": "Notion",
        "description": "Connect Notion to manage workspace pages and databases. (Experimental — limited tool coverage)",
        "icon_url": "https://upload.wikimedia.org/wikipedia/commons/4/45/Notion_app_logo.png",
        "category": "productivity",
        "source": "experimental",
        "auth_type": "oauth",
        "execution_type": "native_adapter",
        "trust_level": "experimental",
        "lifecycle": "IDEA",
        "tools_provided": [],
        "auth_schema": {"type": "oauth2"},
        "permission_schema": [],
    },
]
