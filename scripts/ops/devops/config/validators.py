import os
import re
from datetime import datetime
from pathlib import Path

try:
    from models import ConfigValidationReport, Severity, ValidationResult
    from rules import ENV_SCHEMA, URL_PATTERNS
except ImportError:
    from scripts.devops.config.models import ConfigValidationReport, Severity, ValidationResult
    from scripts.devops.config.rules import ENV_SCHEMA, URL_PATTERNS


class SuperAIConfigValidator:
    """
    Comprehensive configuration validator.
    
    Checks all aspects of SuperAI configuration for:
    - Missing or invalid values
    - Security vulnerabilities
    - Best practice violations
    - Deployment readiness
    """
    
    def __init__(
        self,
        project_root: Path | None = None,
        security_only: bool = False,
        env_only: bool = False,
        auto_fix: bool = False,
        verbose: bool = False
    ):
        self.project_root = project_root or self._detect_project_root()
        self.security_only = security_only
        self.env_only = env_only
        self.auto_fix = auto_fix
        self.verbose = verbose
        
        self.report = ConfigValidationReport()
        self.fixes_applied: list[str] = []
        
        # Load environment from .env if exists
        self._load_env_file()
    
    def _detect_project_root(self) -> Path:
        """Detect project root directory."""
        current = Path.cwd()
        indicators = ['package.json', '.env', 'backend/main.py']
        
        for parent in [current] + list(current.parents):
            if any((parent / ind).exists() for ind in indicators):
                return parent
        
        return current
    
    def _load_env_file(self):
        """Load environment variables from .env file."""
        env_files = [
            self.project_root / '.env',
            self.project_root / '.env.local',
            self.project_root / '.env.production'
        ]
        
        for env_file in env_files:
            if env_file.exists():
                self._parse_env_file(env_file)
    
    def _parse_env_file(self, env_path: Path):
        """Parse .env file and set environment variables."""
        try:
            content = env_path.read_text()
            
            for line in content.splitlines():
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    
                    # Don't override existing env vars unless empty
                    if key not in os.environ or not os.environ.get(key):
                        os.environ[key] = value
                        
        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not parse {env_path}: {e}")
    
    def add_result(self, result: ValidationResult):
        """Add a validation result."""
        self.report.results.append(result)
        
        icons = {
            Severity.INFO: "ℹ️",
            Severity.WARNING: "⚠️",
            Severity.ERROR: "❌",
            Severity.CRITICAL: "🚨"
        }
        
        icon = icons.get(result.severity, "•")
        print(f"{icon} [{result.category}] {result.check_name}: {result.message}")
    
    def run_all_validations(self) -> ConfigValidationReport:
        """Run all validation checks."""
        print("\n" + "="*60)
        print("🔍 SuperAI Config Validator")
        print("="*60)
        print(f"Project Root: {self.project_root}")
        print(f"Mode: {'Security Only' if self.security_only else ('Env Only' if self.env_only else 'Full')}")
        print()
        
        validations = [
            ("environment", self._validate_environment),
            ("security", self._validate_security),
            ("urls", self._validate_urls),
            ("database", self._validate_database_config),
            ("redis", self._validate_redis_config),
            ("llm_providers", self._validate_llm_providers),
            ("nextjs", self._validate_nextjs_config),
            ("files", self._validate_config_files),
        ]
        
        # Filter based on mode
        if self.security_only:
            validations = [("security", self._validate_security)]
        elif self.env_only:
            validations = [("environment", self._validate_environment)]
        
        # Run validations
        for category_name, validation_func in validations:
            print(f"\n--- {category_name.upper()} ---")
            try:
                results = validation_func()
                if isinstance(results, list):
                    for r in results:
                        self.add_result(r)
                elif results:
                    self.add_result(results)
            except Exception as e:
                self.add_result(ValidationResult(
                    category=category_name,
                    check_name="validation_error",
                    severity=Severity.ERROR,
                    message=f"Validation failed: {e!s}"
                ))
        
        self.report.end_time = datetime.now()
        
        # Auto-fix if requested
        if self.auto_fix:
            self._apply_auto_fixes()
        
        return self.report
    
    def _validate_environment(self) -> list[ValidationResult]:
        """Validate environment variables."""
        results = []
        
        # Check required variables
        for var_name, description, pattern in ENV_SCHEMA['required']:
            value = os.environ.get(var_name)
            
            if not value:
                results.append(ValidationResult(
                    category="environment",
                    check_name=f"Required: {var_name}",
                    severity=Severity.ERROR,
                    message=f"Missing required variable: {var_name} ({description})",
                    expected=f"Set {var_name} in .env",
                    fix_suggestion=f"Add {var_name}=<your_value> to .env file",
                    auto_fixable=False
                ))
            else:
                # Validate format
                if pattern and not re.match(pattern, value):
                    results.append(ValidationResult(
                        category="environment",
                        check_name=f"Format: {var_name}",
                        severity=Severity.WARNING,
                        message=f"Invalid format for {var_name}",
                        value=self._mask_value(var_name, value),
                        expected=pattern,
                        fix_suggestion=f"Check the format of {var_name}"
                    ))
                else:
                    results.append(ValidationResult(
                        category="environment",
                        check_name=f"Required: {var_name}",
                        severity=Severity.INFO,
                        message=f"✅ {var_name} is set",
                        value=self._mask_value(var_name, value)
                    ))
        
        # Check at least one LLM provider
        for provider_group in ENV_SCHEMA['at_least_one']:
            found_any = any(os.environ.get(p) for p in provider_group)
            
            if not found_any:
                results.append(ValidationResult(
                    category="environment",
                    check_name="LLM Provider API Key",
                    severity=Severity.ERROR,
                    message="No LLM provider API key configured",
                    expected=f"At least one of: {', '.join(provider_group)}",
                    fix_suggestion="Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY"
                ))
            else:
                found_keys = [p for p in provider_group if os.environ.get(p)]
                results.append(ValidationResult(
                    category="environment",
                    check_name="LLM Provider API Keys",
                    severity=Severity.INFO,
                    message=f"LLM providers configured: {', '.join(found_keys)}"
                ))
        
        # Check recommended variables
        for var_name, description, pattern in ENV_SCHEMA['recommended']:
            value = os.environ.get(var_name)
            
            if not value:
                results.append(ValidationResult(
                    category="environment",
                    check_name=f"Recommended: {var_name}",
                    severity=Severity.WARNING,
                    message=f"Missing recommended variable: {var_name} ({description})",
                    fix_suggestion=f"Consider setting {var_name} for full functionality"
                ))
            elif pattern and not re.match(pattern, value):
                results.append(ValidationResult(
                    category="environment",
                    check_name=f"Value: {var_name}",
                    severity=Severity.WARNING,
                    message=f"Unexpected value for {var_name}",
                    value=value,
                    expected=pattern
                ))
        
        # Check NODE_ENV
        node_env = os.environ.get('NODE_ENV', 'development')
        if node_env == 'production':
            # In production, warn about development settings
            results.extend(self._check_production_readiness())
        
        return results
    
    def _validate_security(self) -> list[ValidationResult]:
        """Security-focused validation."""
        results = []
        
        # Check for exposed secrets in code
        secret_patterns = [
            (r'sk-[a-zA-Z0-9]{20,}', 'OpenAI API key'),
            (r'sk-ant-api03-[a-zA-Z0-9_-]{20,}', 'Anthropic API key'),
            (r'AIza[a-zA-Z0-9_-]{35}', 'Google API key'),
            (r'password\s*=\s*["\'][^"\']+["\']', 'Hardcoded password'),
            (r'secret\s*=\s*["\'][^"\']+["\']', 'Hardcoded secret'),
        ]
        
        # Scan source files
        source_dirs = [
            self.project_root / 'backend',
            self.project_root / 'src',
            self.project_root / 'lib',
            self.project_root / 'app',
        ]
        
        secrets_found = []
        
        for source_dir in source_dirs:
            if not source_dir.exists():
                continue
            
            for file_path in source_dir.rglob('*.*'):
                if file_path.suffix in ['.py', '.js', '.ts', '.tsx', '.jsx', '.json']:
                    try:
                        content = file_path.read_text()
                        
                        for pattern, name in secret_patterns:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            if matches:
                                rel_path = file_path.relative_to(self.project_root)
                                secrets_found.append((str(rel_path), name, len(matches)))
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception(f"Silenced error: {e}")
        
        if secrets_found:
            for file_path, secret_type, count in secrets_found[:10]:  # Limit output
                results.append(ValidationResult(
                    category="security",
                    check_name="Exposed Secret",
                    severity=Severity.CRITICAL,
                    message=f"Potential {secret_type} found in {file_path}",
                    fix_suggestion="Move secrets to environment variables, add to .gitignore"
                ))
        else:
            results.append(ValidationResult(
                category="security",
                check_name="Secret Scanning",
                severity=Severity.INFO,
                message="No exposed secrets detected in source code"
            ))
        
        # Check .gitignore
        gitignore = self.project_root / '.gitignore'
        should_ignore = ['.env', '*.env', '__pycache__', 'node_modules', '.next']
        
        if gitignore.exists():
            gitignore_content = gitignore.read_text()
            
            for item in should_ignore:
                if item not in gitignore_content:
                    results.append(ValidationResult(
                        category="security",
                        check_name=".gitignore",
                        severity=Severity.WARNING,
                        message=f"'{item}' missing from .gitignore",
                        fix_suggestion=f"Add '{item}' to .gitignore",
                        auto_fixable=True
                    ))
        else:
            results.append(ValidationResult(
                category="security",
                check_name=".gitignore",
                severity=Severity.ERROR,
                message=".gitignore file missing!",
                fix_suggestion="Create .gitignore with proper exclusions",
                auto_fixable=True
            ))
        
        # Check for weak/default values
        weak_defaults = {
            'NEXTAUTH_SECRET': ['secret', 'password', 'changeme', 'default', 'dev'],
            'DATABASE_URL': ['localhost', '127.0.0.1'],  # OK for dev, warn for prod  # is_local()
        }
        
        for var_name, weak_values in weak_defaults.items():
            value = os.environ.get(var_name, '').lower()
            
            if any(wv in value for wv in weak_values):
                results.append(ValidationResult(
                    category="security",
                    check_name=f"Weak Value: {var_name}",
                    severity=Severity.WARNING if var_name != 'NEXTAUTH_SECRET' else Severity.CRITICAL,
                    message=f"{var_name} appears to use a weak/default value",
                    fix_suggestion=f"Generate a strong random value for {var_name}"
                ))
        
        # Check CORS settings
        cors_origin = os.environ.get('ALLOWED_ORIGINS', '*')
        if cors_origin == '*':
            results.append(ValidationResult(
                category="security",
                check_name="CORS Configuration",
                severity=Severity.WARNING if os.environ.get('NODE_ENV') == 'production' else Severity.INFO,
                message="CORS allows all origins (*)",
                value=cors_origin,
                expected="Specific origins in production",
                fix_suggestion="Set ALLOWED_ORIGINS to specific URLs in production"
            ))
        
        # Check HTTPS enforcement
        nextauth_url = os.environ.get('NEXTAUTH_URL', '')
        if nextauth_url and not nextauth_url.startswith('https://'):
            if os.environ.get('NODE_ENV') == 'production':
                results.append(ValidationResult(
                    category="security",
                    check_name="HTTPS Enforcement",
                    severity=Severity.ERROR,
                    message="NEXTAUTH_URL should use HTTPS in production",
                    value=nextauth_url,
                    expected="https://...",
                    fix_suggestion="Use HTTPS URL for NEXTAUTH_URL in production"
                ))
        
        return results
    
    def _validate_urls(self) -> list[ValidationResult]:
        """Validate URL configurations."""
        results = []
        
        url_vars = {
            'SUPABASE_URL': ('Supabase URL', URL_PATTERNS['supabase_url']),
            'NEXTAUTH_URL': ('App URL', URL_PATTERNS['valid_url']),
        }
        
        for var_name, (description, pattern) in url_vars.items():
            value = os.environ.get(var_name)
            
            if value:
                if not pattern.match(value):
                    results.append(ValidationResult(
                        category="urls",
                        check_name=f"URL Format: {var_name}",
                        severity=Severity.ERROR,
                        message=f"Invalid {description} format",
                        value=value,
                        fix_suggestion=f"Check {var_name} format"
                    ))
                
                # Check for localhost in production
                if 'localhost' in value or '127.0.0.1' in value:  # is_local()
                    if os.environ.get('NODE_ENV') == 'production':
                        results.append(ValidationResult(
                            category="urls",
                            check_name=f"Production URL: {var_name}",
                            severity=Severity.ERROR,
                            message=f"{var_name} points to localhost in production",
                            value=value,
                            fix_suggestion="Use production URL"
                        ))
        
        return results
    
    def _validate_database_config(self) -> list[ValidationResult]:
        """Validate database configuration."""
        results = []
        
        db_url = os.environ.get('DATABASE_URL', '')
        
        if db_url:
            # Check for SSL requirement
            if '?sslmode=' not in db_url and os.environ.get('NODE_ENV') == 'production':
                results.append(ValidationResult(
                    category="database",
                    check_name="Database SSL",
                    severity=Severity.WARNING,
                    message="Database connection may not be using SSL",
                    fix_suggestion="Add ?sslmode=require to DATABASE_URL"
                ))
            
            # Check for connection pooling
            pool_size = os.environ.get('DATABASE_POOL_SIZE')
            if not pool_size and os.environ.get('NODE_ENV') == 'production':
                results.append(ValidationResult(
                    category="database",
                    check_name="Connection Pooling",
                    severity=Severity.INFO,
                    message="Consider setting DATABASE_POOL_SIZE for production",
                    fix_suggestion="Set DATABASE_POOL_SIZE=10-20 based on load"
                ))
            
            # Warn about superuser in production
            if 'postgres://postgres:' in db_url:
                results.append(ValidationResult(
                    category="database",
                    check_name="Database User",
                    severity=Severity.WARNING,
                    message="Using postgres superuser account",
                    fix_suggestion="Create a dedicated application user with limited permissions"
                ))
        
        return results
    
    def _validate_redis_config(self) -> list[ValidationResult]:
        """Validate Redis configuration."""
        results = []
        
        redis_url = os.environ.get('REDIS_URL') or os.environ.get('UPSTASH_REDIS_REST_URL')
        
        if redis_url:
            # Check for password
            if ':@' not in redis_url and 'redis://' in redis_url:
                results.append(ValidationResult(
                    category="redis",
                    check_name="Redis Authentication",
                    severity=Severity.WARNING,
                    message="Redis URL may not include authentication",
                    fix_suggestion="Ensure Redis requires password authentication"
                ))
            
            # Check for TLS
            if redis_url.startswith('redis://') and not redis_url.startswith('rediss://'):
                if os.environ.get('NODE_ENV') == 'production':
                    results.append(ValidationResult(
                        category="redis",
                        check_name="Redis TLS",
                        severity=Severity.WARNING,
                        message="Redis connection not using TLS",
                        fix_suggestion="Use rediss:// for encrypted connection"
                    ))
        else:
            results.append(ValidationResult(
                category="redis",
                check_name="Redis Configuration",
                severity=Severity.INFO,
                message="Redis not configured (caching/rate-limiting disabled)",
                fix_suggestion="Configure REDIS_URL for full functionality"
            ))
        
        return results
    
    def _validate_llm_providers(self) -> list[ValidationResult]:
        """Validate LLM provider configurations."""
        results = []
        
        # OpenAI
        openai_key = os.environ.get('OPENAI_API_KEY', '')
        if openai_key:
            if not openai_key.startswith('sk-'):
                results.append(ValidationResult(
                    category="llm_providers",
                    check_name="OpenAI API Key Format",
                    severity=Severity.WARNING,
                    message="OpenAI API key may have invalid format"
                ))
            elif len(openai_key) < 48:
                results.append(ValidationResult(
                    category="llm_providers",
                    check_name="OpenAI API Key Length",
                    severity=Severity.WARNING,
                    message="OpenAI API key seems too short"
                ))
        
        # Anthropic
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if anthropic_key and not anthropic_key.startswith('sk-ant-'):
            results.append(ValidationResult(
                category="llm_providers",
                check_name="Anthropic API Key Format",
                severity=Severity.WARNING,
                message="Anthropic API key may have invalid format"
            ))
        
        # Model configurations
        default_model = os.environ.get('DEFAULT_LLM_MODEL', 'gpt-3.5-turbo')
        valid_models = [
            'gpt-4', 'gpt-4-turbo', 'gpt-4o', 'gpt-3.5-turbo',
            'claude-3-opus-20240229', 'claude-3-sonnet-20240229', 'claude-3-haiku-20240307',
            'gemini-pro', 'gemini-1.5-pro'
        ]
        
        if default_model not in valid_models:
            results.append(ValidationResult(
                category="llm_providers",
                check_name="Default LLM Model",
                severity=Severity.INFO,
                message=f"Custom model configured: {default_model}",
                fix_suggestion=f"Valid models: {', '.join(valid_models[:5])}..."
            ))
        
        # Cost optimization check
        providers_configured = sum(bool(os.environ.get(k)) for k in 
                                    ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY'])
        
        if providers_configured >= 2:
            results.append(ValidationResult(
                category="llm_providers",
                check_name="Cost Optimization Ready",
                severity=Severity.INFO,
                message=f"Multiple providers ({providers_configured}) enable smart routing & cost optimization"
            ))
        elif providers_configured == 1:
            results.append(ValidationResult(
                category="llm_providers",
                check_name="Cost Optimization",
                severity=Severity.INFO,
                message="Single provider configured - add more for cost optimization via Smart Router"
            ))
        
        return results
    
    def _validate_nextjs_config(self) -> list[ValidationResult]:
        """Validate Next.js specific configuration."""
        results = []
        
        # Check next.config.js
        next_config = self.project_root / 'next.config.js'
        if next_config.exists():
            try:
                config_content = next_config.read_text()
                
                # Check for image domains
                if 'images' in config_content:
                    results.append(ValidationResult(
                        category="nextjs",
                        check_name="Image Configuration",
                        severity=Severity.INFO,
                        message="Image optimization configured"
                    ))
                
                # Check for headers/security
                if 'headers' in config_content:
                    results.append(ValidationResult(
                        category="nextjs",
                        check_name="Security Headers",
                        severity=Severity.INFO,
                        message="Custom headers configured"
                    ))
                else:
                    results.append(ValidationResult(
                        category="nextjs",
                        check_name="Security Headers",
                        severity=Severity.WARNING,
                        message="No custom headers in next.config.js",
                        fix_suggestion="Add security headers (CSP, X-Frame-Options, etc.)"
                    ))
                    
            except Exception as e:
                results.append(ValidationResult(
                    category="nextjs",
                    check_name="Config File Read",
                    severity=Severity.WARNING,
                    message=f"Could not read next.config.js: {e}"
                ))
        else:
            results.append(ValidationResult(
                category="nextjs",
                check_name="Next.js Config",
                severity=Severity.ERROR,
                message="next.config.js not found",
                fix_suggestion="Create next.config.js with proper configuration"
            ))
        
        return results
    
    def _validate_config_files(self) -> list[ValidationResult]:
        """Validate configuration files exist and are valid."""
        results = []
        
        required_files = {
            'package.json': 'Node.js project config',
            'tsconfig.json': 'TypeScript configuration',
            'tailwind.config.ts': 'Tailwind CSS config',
            '.env.example': 'Environment template',
        }
        
        optional_files = {
            '.eslintrc.json': 'ESLint configuration',
            '.prettierrc': 'Prettier formatting config',
            'docker-compose.yml': 'Docker compose config',
            'Dockerfile': 'Docker build config',
            'vercel.json': 'Vercel deployment config',
            '.github/workflows/ci.yml': 'CI/CD workflow',
        }
        
        # Check required files
        for filename, description in required_files.items():
            filepath = self.project_root / filename
            if filepath.exists():
                results.append(ValidationResult(
                    category="files",
                    check_name=description,
                    severity=Severity.INFO,
                    message=f"✅ {filename} present"
                ))
            else:
                results.append(ValidationResult(
                    category="files",
                    check_name=description,
                    severity=Severity.ERROR if filename != '.env.example' else Severity.WARNING,
                    message=f"Missing: {filename}",
                    fix_suggestion=f"Create {filename}"
                ))
        
        # Check optional files
        for filename, description in optional_files.items():
            filepath = self.project_root / filename
            if filepath.exists():
                results.append(ValidationResult(
                    category="files",
                    check_name=description,
                    severity=Severity.INFO,
                    message=f"✅ {filename} present"
                ))
        
        return results
    
    def _check_production_readiness(self) -> list[ValidationResult]:
        """Check settings that matter specifically for production."""
        results = []
        
        # Debug mode
        debug_mode = os.environ.get('DEBUG', '').lower() in ['true', '1', 'yes']
        if debug_mode:
            results.append(ValidationResult(
                category="environment",
                check_name="Debug Mode",
                severity=Severity.ERROR,
                message="DEBUG enabled in production!",
                fix_suggestion="Set DEBUG=false in production"
            ))
        
        # Verbose logging
        log_level = os.environ.get('LOG_LEVEL', '').upper()
        if log_level in ['DEBUG', 'TRACE']:
            results.append(ValidationResult(
                category="environment",
                check_name="Log Level",
                severity=Severity.WARNING,
                message=f"Verbose logging ({log_level}) in production",
                fix_suggestion="Set LOG_LEVEL=INFO or LOG_LEVEL=WARN in production"
            ))
        
        return results
    
    def _mask_value(self, var_name: str, value: str) -> str:
        """Mask sensitive values for display."""
        sensitive_keywords = ['key', 'secret', 'password', 'token', 'credential']
        
        if any(kw in var_name.lower() for kw in sensitive_keywords):
            if len(value) > 8:
                return value[:4] + '...' + value[-4:]
            return '***'
        
        return value
    
    def _apply_auto_fixes(self):
        """Apply automatic fixes where possible."""
        auto_fixable_results = [r for r in self.report.results if r.auto_fixable]
        
        if not auto_fixable_results:
            return
        
        print("\n\n🔧 Applying Auto-Fixes...")
        
        for result in auto_fixable_results:
            if result.check_name == ".gitignore":
                self._fix_gitignore()
                self.fixes_applied.append(result.fix_suggestion or result.check_name)
    
    def _fix_gitignore(self):
        """Fix .gitignore file."""
        gitignore_path = self.project_root / '.gitignore'
        
        entries_to_add = [
            '# Environment variables',
            '.env',
            '.env.local',
            '.env.production',
            '',
            '# Dependencies',
            'node_modules/',
            '__pycache__/',
            '*.pyc',
            '',
            '# Build outputs',
            '.next/',
            'dist/',
            'build/',
            '',
            '# IDE',
            '.vscode/',
            '.idea/',
            '',
            '# OS',
            '.DS_Store',
            'Thumbs.db',
            '',
            '# Database',
            '*.db',
            '*.sqlite3',
            '',
            '# Backups',
            'backups/',
        ]
        
        if gitignore_path.exists():
            existing = gitignore_path.read_text()
        else:
            existing = ''
        
        new_entries = []
        for entry in entries_to_add:
            if entry and entry not in existing:
                new_entries.append(entry)
        
        if new_entries:
            with open(gitignore_path, 'a') as f:
                if existing and not existing.endswith('\n'):
                    f.write('\n')
                f.write('\n'.join(new_entries) + '\n')
            
            print(f"   ✅ Added {len(new_entries)} entries to .gitignore")
    
    def print_report(self):
        """Print formatted validation report."""
        print("\n" + "="*60)
        print("📋 VALIDATION REPORT SUMMARY")
        print("="*60)
        
        status_icon = "✅" if self.report.is_valid else "❌"
        print(f"\nStatus: {status_icon} {'VALID' if self.report.is_valid else 'ISSUES FOUND'}")
        print("\nIssues:")
        print(f"   🚨 Critical: {self.report.critical_count}")
        print(f"   ❌ Errors:   {self.report.error_count}")
        print(f"   ⚠️  Warnings: {self.report.warning_count}")
        print(f"   ℹ️  Info:     {self.report.info_count}")
        
        if self.fixes_applied:
            print("\nAuto-fixes applied:")
            for fix in self.fixes_applied:
                print(f"   ✅ {fix}")
        
        # Group by category
        categories = {}
        for result in self.report.results:
            if result.severity in [Severity.CRITICAL, Severity.ERROR, Severity.WARNING]:
                if result.category not in categories:
                    categories[result.category] = []
                categories[result.category].append(result)
        
        if categories:
            print(f"\n{'='*60}")
            print("ISSUES BY CATEGORY")
            print('='*60)
            
            for category, issues in categories.items():
                print(f"\n{category.upper()}:")
                for issue in issues:
                    icon = {
                        Severity.CRITICAL: "🚨",
                        Severity.ERROR: "❌",
                        Severity.WARNING: "⚠️"
                    }.get(issue.severity, "•")
                    
                    print(f"  {icon} {issue.check_name}")
                    print(f"     {issue.message}")
                    if issue.fix_suggestion:
                        print(f"     💡 Fix: {issue.fix_suggestion}")
        
        print()