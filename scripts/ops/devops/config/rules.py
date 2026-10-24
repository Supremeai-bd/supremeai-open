import re

"""
================================================================================
SuperAI Config Validator - Environment & Configuration Validation
================================================================================
✅ Validates all configuration files and environment variables
🔍 Detects security issues, misconfigurations, and best practice violations
⚡ Pre-deployment validation to prevent runtime errors
📋 Generates detailed reports with fix recommendations

Author: SuperAI Toolkit
Version: 1.0.0
License: MIT

Usage:
    python superai_config_validator.py                    # Full validation
    python superai_config_validator.py --security         # Security-focused check
    python superai_config_validator.py --env-only         # Check only .env file
    python superai_config_validator.py --fix              # Auto-fix common issues
    python superai_config_validator.py --json             # JSON output for CI/CD

Validation Categories:
  🔐 Security (exposed secrets, weak settings)
  ⚙️ Configuration (missing vars, invalid values)
  🌐 Network (CORS, URLs, endpoints)
  🗄️ Database (connection strings, pool settings)
  💾 Redis (connection, configuration)
  🤖 LLM Providers (API keys, model configs)
  📦 Dependencies (versions, conflicts)

CPU Impact:
  - Runs once: <1 second CPU time
  - No network calls (local validation only)
  - Safe for CI/CD pipelines
================================================================================
"""

ENV_SCHEMA = {
    # Required variables
    'required': [
        ('DATABASE_URL', 'PostgreSQL/Supabase connection string', r'postgresql://.+|postgres://.+'),
        ('NEXTAUTH_SECRET', 'Random secret for NextAuth', r'.{16,}'),
        ('NEXTAUTH_URL', 'Application URL', r'https?://.+'),
        ('SUPABASE_URL', 'Supabase project URL', r'https://[a-z0-9-]+\.supabase\.co'),
        ('SUPABASE_ANON_KEY', 'Supabase anonymous key', r'ey[A-Za-z0-9_-]{50,}'),
    ],

    # At least one required (LLM providers)
    'at_least_one': [
        ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GOOGLE_API_KEY']
    ],

    # Recommended with patterns
    'recommended': [
        ('REDIS_URL', 'Redis connection URL', r'redis://.+|rediss://.+'),
        ('UPSTASH_REDIS_REST_URL', 'Upstash Redis REST URL', r'https://[a-z0-9-]+\.upstash\.io'),
        ('NODE_ENV', 'Environment mode', r'^development$|^production$|^test$'),
    ],

    # Security sensitive (should not have default/weak values)
    'security_sensitive': [
        'NEXTAUTH_SECRET',
        'DATABASE_URL',
        'SECRET_KEY',
        'JWT_SECRET',
        'ENCRYPTION_KEY',
    ]
}

URL_PATTERNS = {
    'valid_url': re.compile(r'^https?://[^\s/$.?#].[^\s]*$', re.IGNORECASE),
    'supabase_url': re.compile(r'https://[a-z0-9-]+\.supabase\.co', re.IGNORECASE),
    'api_key_openai': re.compile(r'^sk-[a-zA-Z0-9]{48}$'),
    'api_key_anthropic': re.compile(r'^sk-ant-api03-[a-zA-Z0-9_-]{93}$'),
}
