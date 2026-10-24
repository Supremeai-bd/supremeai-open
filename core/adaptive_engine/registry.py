import datetime
from dataclasses import dataclass, field

# বাংলা মন্তব্য: টাইমজোন-অ্যাওয়ার টেম্পোরাল ডিফল্ট ব্যবহার করলে Python-ভিত্তিক কমপ্যাটিবিলিটি ও প্রোডাকশন লগিং আরও স্থিতিশীল হয়।


@dataclass
class PlatformProfile:
    name: str
    display_name: str
    category: str  # "git", "hosting", "cloud", "database"
    auth_methods: list[str]
    capabilities: list[str]
    deploy_methods: list[str]
    sdk_code: str = ""
    api_endpoints: dict = field(default_factory=dict)
    rate_limits: dict = field(default_factory=dict)
    pricing_tier: str = "free"
    docs_url: str = ""
    status: str = "active"  # "active", "beta", "deprecated"
    learned_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    last_updated: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )
    success_rate: float = 1.0


class PlatformRegistry:
    def __init__(self):
        self._platforms: dict[str, PlatformProfile] = {}
        self._load_preloaded_platforms()

    def register_platform(self, profile: PlatformProfile):
        self._platforms[profile.name.lower()] = profile

    def get_platform(self, name: str) -> PlatformProfile | None:
        return self._platforms.get(name.lower())

    def list_platforms(self) -> list[PlatformProfile]:
        return list(self._platforms.values())

    def _load_preloaded_platforms(self):
        # GitHub
        self.register_platform(
            PlatformProfile(
                name="github",
                display_name="GitHub",
                category="git",
                auth_methods=["oauth2", "pat", "ssh_key"],
                capabilities=[
                    "repo_create",
                    "pages_deploy",
                    "actions_ci",
                    "secret_management",
                ],
                deploy_methods=["git_push", "api_upload"],
                docs_url="https://docs.github.com",
                pricing_tier="free/paid",
            )
        )

        # GitLab
        self.register_platform(
            PlatformProfile(
                name="gitlab",
                display_name="GitLab",
                category="git",
                auth_methods=["oauth2", "pat"],
                capabilities=["repo_create", "ci_cd", "registry", "pages"],
                deploy_methods=["git_push", "container_push"],
                docs_url="https://docs.gitlab.com",
            )
        )

        # Firebase
        self.register_platform(
            PlatformProfile(
                name="firebase",
                display_name="Firebase",
                category="hosting",
                auth_methods=["service_account", "api_key"],
                capabilities=[
                    "hosting_deploy",
                    "functions_deploy",
                    "database",
                    "auth",
                    "storage",
                ],
                deploy_methods=["cli_deploy"],
                docs_url="https://firebase.google.com/docs",
            )
        )

        # Vercel
        self.register_platform(
            PlatformProfile(
                name="vercel",
                display_name="Vercel",
                category="hosting",
                auth_methods=["oauth2"],
                capabilities=["static_deploy", "serverless", "edge", "preview"],
                deploy_methods=["api_upload", "git_push"],
                docs_url="https://vercel.com/docs",
            )
        )

        # Netlify
        self.register_platform(
            PlatformProfile(
                name="netlify",
                display_name="Netlify",
                category="hosting",
                auth_methods=["oauth2"],
                capabilities=["static_deploy", "forms", "functions", "identity"],
                deploy_methods=["api_upload", "git_push"],
                docs_url="https://docs.netlify.com",
            )
        )

        # AWS
        self.register_platform(
            PlatformProfile(
                name="aws",
                display_name="Amazon Web Services",
                category="cloud",
                auth_methods=["service_account"],
                capabilities=["ec2", "lambda", "s3", "rds", "cloudfront"],
                deploy_methods=["cli_deploy", "container_push"],
                docs_url="https://docs.aws.amazon.com",
            )
        )

        # GCP
        self.register_platform(
            PlatformProfile(
                name="gcp",
                display_name="Google Cloud Platform",
                category="cloud",
                auth_methods=["service_account"],
                capabilities=["cloud_run", "cloud_storage", "firestore", "pubsub"],
                deploy_methods=["cli_deploy", "container_push"],
                docs_url="https://cloud.google.com/docs",
            )
        )

        # Supabase
        self.register_platform(
            PlatformProfile(
                name="supabase",
                display_name="Supabase",
                category="database",
                auth_methods=["api_key"],
                capabilities=[
                    "postgres",
                    "auth",
                    "storage",
                    "realtime",
                    "edge_functions",
                ],
                deploy_methods=["api_upload"],
                docs_url="https://supabase.com/docs",
            )
        )

        # Railway
        self.register_platform(
            PlatformProfile(
                name="railway",
                display_name="Railway",
                category="hosting",
                auth_methods=["oauth2"],
                capabilities=["auto_deploy", "databases", "metrics"],
                deploy_methods=["git_push", "api_upload"],
                docs_url="https://docs.railway.app",
            )
        )

        # Render
        self.register_platform(
            PlatformProfile(
                name="render",
                display_name="Render",
                category="hosting",
                auth_methods=["oauth2"],
                capabilities=["web_services", "static_sites", "databases"],
                deploy_methods=["git_push", "api_upload"],
                docs_url="https://render.com/docs",
            )
        )
