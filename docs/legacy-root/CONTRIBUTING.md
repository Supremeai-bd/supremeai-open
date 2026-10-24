# Contributing to SupremeAI

Thank you for your interest in contributing to SupremeAI! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation Standards](#documentation-standards)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Community](#community)

---

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inspiring community for all. Please be respectful and constructive in your interactions.

### Expected Behavior

- Use welcoming and inclusive language
- Be respectful of differing viewpoints
- Accept constructive criticism gracefully
- Focus on what's best for the community
- Show empathy towards other contributors

### Unacceptable Behavior

- Harassment or discriminatory language
- Trolling or insulting comments
- Public or private harassment
- Publishing others' private information
- Other unprofessional conduct

---

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- **Python 3.11+** with pip
- **Node.js 18+** with npm
- **Git** version control
- **Docker** (optional, for local database)
- A code editor (VS Code recommended)

### Initial Setup

```bash
# 1. Fork the repository
# Click 'Fork' on https://github.com/SaifulHaqueNiloy/supremeai

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/supremeai.git
cd supremeai

# 3. Add upstream remote
git remote add upstream https://github.com/SaifulHaqueNiloy/supremeai.git

# 4. Backend setup
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
cp .env.example .env
# Edit .env with your settings

# 5. Frontend setup (new terminal)
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

### Recommended VS Code Extensions

- Python (Microsoft)
- Pylance (Microsoft)
- ESLint (Microsoft)
- Prettier (Prettier)
- Thunder Client (for API testing)

---

## Development Workflow

### 1. Choose an Issue

- Look for issues labeled `good first issue` for beginners
- Check `help wanted` for tasks needing assistance
- Create an issue for new features or bugs you've found
- Comment on the issue to claim it (prevents duplicate work)

### 2. Create a Branch

```bash
# Sync main branch first
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/your-feature-name

# Or bug fix branch
git checkout -b fix/description-of-fix

# Or documentation branch
git checkout -b docs/what-youre-documenting
```

**Branch Naming Convention:**

| Type | Prefix | Example |
|------|--------|---------|
| Feature | `feature/` | `feature/add-webhook-support` |
| Bug Fix | `fix/` | `fix/memory-leak-in-agent` |
| Documentation | `docs/` | `docs/update-api-examples` |
| Refactor | `refactor/` | `refactor/simplify-auth-flow` |
| Test | `test/` | `test/add-hitl-integration-tests` |
| Chore | `chore/` | `chore/update-dependencies` |

### 3. Make Your Changes

#### Development Tips

**Backend:**
```bash
# Run with auto-reload
cd backend
uvicorn app.main:app --reload --port 8000

# Run tests
pytest tests/ -v

# Run specific test file
pytest tests/test_auth.py -v

# Run with coverage
pytest --cov=app tests/
```

**Frontend:**
```bash
# Start dev server
cd frontend
npm run dev

# Run linting
npm run lint

# Run type checking
npm run type-check

# Run tests
npm run test

# Run tests in watch mode
npm run test:watch
```

### 4. Commit Your Changes

See [Commit Guidelines](#commit-guidelines) below for message format.

### 5. Push and Create PR

```bash
# Push to your fork
git push origin feature/your-feature-name

# Open Pull Request on GitHub
# Go to your fork -> "Contribute" -> "Open pull request"
```

---

## Coding Standards

### Python (Backend)

Follow PEP 8 style guidelines:

#### Formatting

Use Black for automatic formatting:

```bash
# Format code
black .

# Check formatting without changing files
black --check .
```

#### Linting

Use flake8 for linting:

```bash
# Lint code
flake8 .

# Common flake8 errors to avoid:
# - E501: Line too long (Black handles this)
# - F841: Local variable assigned but never used
# - E722: Do not use bare except
# - W605: Invalid escape sequence (use raw strings for regex)
```

#### Type Hints

All functions must have type hints:

```python
# Good
def calculate_tokens(
    messages: list[Message],
    model: str = "gpt-4"
) -> int:
    """Calculate total tokens for message list."""
    return sum(msg.token_count for msg in messages)

# Bad
def calculate_tokens(messages, model="gpt-4"):
    # No type hints
    pass
```

#### Docstrings

Use Google-style docstrings:

```python
def create_agent(
    name: str,
    system_prompt: str,
    owner_id: UUID,
    **kwargs: Any
) -> Agent:
    """Create a new AI agent.
    
    Args:
        name: Display name for the agent.
        system_prompt: Instructions defining agent behavior.
        owner_id: UUID of the user creating this agent.
        **kwargs: Additional configuration options.
        
    Returns:
        The newly created Agent instance.
        
    Raises:
        ValueError: If name is empty or system_prompt too long.
        DuplicateError: If agent with same name exists for owner.
        
    Example:
        >>> agent = create_agent(
        ...     name="Research Assistant",
        ...     system_prompt="You are a researcher...",
        ...     owner_id=user.id
        ... )
    """
```

#### Error Handling

```python
# Good: Specific exceptions, proper logging
async def get_agent(agent_id: UUID) -> Agent:
    """Retrieve agent by ID."""
    try:
        agent = await agent_repository.get(agent_id)
    except DatabaseError as e:
        logger.error(f"Database error fetching agent {agent_id}: {e}")
        raise AgentNotFoundError(f"Agent {agent_id} not found") from e
    
    if not agent:
        raise AgentNotFoundError(f"Agent {agent_id} not found")
    
    return agent

# Bad: Bare except, no logging
async def get_agent(agent_id):
    try:
        return db.get(agent_id)
    except:
        return None
```

### TypeScript (Frontend)

#### Formatting

Use Prettier:

```bash
# Format code
npx prettier --write .

# Check formatting
npx prettier --check .
```

#### Linting

Use ESLint:

```bash
# Lint code
npm run lint

# Auto-fix where possible
npm run lint:fix
```

#### Code Style

```typescript
// Good: Explicit types, interfaces, async/await
interface Agent {
  id: string;
  name: string;
  status: AgentStatus;
  createdAt: Date;
}

async function fetchAgent(id: string): Promise<Agent> {
  const response = await api.get<Agent>(`/agents/${id}`);
  
  if (!response.data) {
    throw new Error(`Agent ${id} not found`);
  }
  
  return response.data;
}

// Bad: Any types, then chains, no error handling
function fetchAgent(id: any) {
  return api.get('/agents/' + id).then(r => r.data);
}
```

#### Component Structure

```tsx
// Good: Organized component with proper hooks
interface MessageListProps {
  messages: Message[];
  isLoading?: boolean;
  onRetry?: (messageId: string) => void;
}

export function MessageList({ 
  messages, 
  isLoading = false,
  onRetry 
}: MessageListProps): JSX.Element {
  const [filter, setFilter] = useState<MessageType>('all');
  
  const filteredMessages = useMemo(
    () => filterMessages(messages, filter),
    [messages, filter]
  );
  
  if (isLoading) {
    return <MessageSkeleton count={5} />;
  }
  
  return (
    <div className="space-y-4">
      <MessageFilter value={filter} onChange={setFilter} />
      {filteredMessages.map((msg) => (
        <MessageItem 
          key={msg.id}
          message={msg}
          onRetry={onRetry ? () => onRetry(msg.id) : undefined}
        />
      ))}
    </div>
  );
}
```

---

## Testing Guidelines

### Backend Testing (pytest)

#### Test Structure

```python
# tests/conftest.py - Shared fixtures
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def auth_headers(client: AsyncClient):
    """Get authenticated headers for tests."""
    response = await client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword123"
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

#### Writing Tests

```python
# tests/test_agents.py
import pytest
from httpx import AsyncClient


class TestCreateAgent:
    """Tests for agent creation endpoint."""
    
    @pytest.mark.asyncio
    async def test_create_agent_success(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Should create agent with valid data."""
        payload = {
            "name": "Test Agent",
            "system_prompt": "You are a test agent",
            "model": "gpt-4-turbo"
        }
        
        response = await client.post(
            "/api/v1/agents",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Agent"
        assert "id" in data
    
    @pytest.mark.asyncio
    async def test_create_agent_requires_name(
        self,
        client: AsyncClient,
        auth_headers: dict
    ):
        """Should reject agent creation without name."""
        payload = {
            "system_prompt": "You are a test agent"
        }
        
        response = await client.post(
            "/api/v1/agents",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_create_agent_unauthorized(
        self,
        client: AsyncClient
    ):
        """Should reject without authentication."""
        payload = {
            "name": "Test Agent",
            "system_prompt": "You are a test agent"
        }
        
        response = await client.post(
            "/api/v1/agents",
            json=payload
        )
        
        assert response.status_code == 401
```

#### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_agents.py -v

# Run specific test class
pytest tests/test_agents.py::TestCreateAgent -v

# Run with coverage
pytest --cov=app --cov-report=html

# Run only marked tests
pytest -m slow  # Tests decorated with @pytest.mark.slow
```

### Frontend Testing (vitest)

#### Writing Component Tests

```tsx
// src/components/__tests__/MessageList.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MessageList } from '../MessageList';

// Mock API calls
vi.mock('../../lib/api', () => ({
  useMessages: vi.fn(),
}));

describe('MessageList', () => {
  it('renders messages correctly', () => {
    const messages = [
      { id: '1', content: 'Hello', role: 'user' },
      { id: '2', content: 'Hi there!', role: 'assistant' },
    ];
    
    render(<MessageList messages={messages} />);
    
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('Hi there!')).toBeInTheDocument();
  });
  
  it('shows skeleton when loading', () => {
    render(<MessageList messages={[]} isLoading={true} />);
    
    expect(screen.getByTestId('message-skeleton')).toBeInTheDocument();
  });
  
  it('calls onRetry when retry button clicked', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    
    const messages = [
      { 
        id: '1', 
        content: 'Failed message', 
        role: 'assistant',
        status: 'error' 
      }
    ];
    
    render(<MessageList messages={messages} onRetry={onRetry} />);
    
    await user.click(screen.getByRole('button', { name: /retry/i }));
    
    expect(onRetry).toHaveBeenCalledWith('1');
  });
});
```

#### Running Tests

```bash
# Run all tests
npm run test

# Run in watch mode
npm run test:watch

# Run with coverage
npm run test:coverage

# Run specific test file
npm run test -- MessageList.test.tsx
```

### Coverage Requirements

- **New code**: Minimum 80% coverage
- **Critical paths** (auth, HITL, memory): Minimum 90% coverage
- **Utilities**: Minimum 70% coverage acceptable if well-documented

---

## Documentation Standards

### Code Comments

```python
# Good: Explain WHY, not WHAT
def prune_old_memories(self, days: int = 30) -> int:
    """Remove memories older than specified days.
    
    We keep recent memories accessible for fast retrieval while
    moving older, less relevant memories to cold storage. This
    balances query performance against storage costs.
    
    Args:
        days: Age threshold in days. Memories older than this
             will be archived.
             
    Returns:
        Number of memories that were pruned.
    """
    # Implementation...
```

### README Updates

When adding features:
1. Update the Features section
2. Add API endpoint examples
2. Update configuration variables if needed
4. Add screenshots for UI changes

### API Documentation

All API endpoints should have:
- Clear description
- Request/response examples
- Error responses
- Authentication requirements

```python
@router.post("/agents", response_model=AgentResponse, status_code=201)
async def create_agent(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    agent_in: AgentCreate
) -> AgentResponse:
    """Create a new AI agent.
    
    Creates a new agent associated with the authenticated user.
    The agent will have default configurations unless overridden
    in the request body.
    
    Args:
        db: Database session dependency.
        current_user: Authenticated user making the request.
        agent_in: Agent creation data with validation.
        
    Returns:
        Newly created agent with generated ID and timestamps.
        
    Raises:
        HTTPException(409): If agent name already exists for user.
        HTTPException(422): If validation fails.
        
    Example:
        POST /api/v1/agents
        {
            "name": "My Agent",
            "system_prompt": "Help users..."
        }
    """
```

---

## Commit Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/):

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `style` | Code style (formatting, semicolons) |
| `refactor` | Code refactoring |
| `perf` | Performance improvements |
| `test` | Adding/updating tests |
| `chore` | Build process, dependencies |
| `ci` | CI/CD changes |

### Scopes

Common scopes: `backend`, `frontend`, `agents`, `auth`, `hitl`, `memory`, `docs`, `tests`

### Examples

```bash
# Feature
feat(agents): add webhook integration for notifications

# Bug fix
fix(auth): resolve token refresh race condition

# Documentation
docs(readme): update installation guide for Windows

# Refactoring
refactor(memory): simplify vector search query builder

# Test
test(hitl): add approval workflow integration tests

# Breaking change
feat(api)!: remove deprecated v1 endpoints

BREAKING CHANGE: Endpoints /v1/legacy/* have been removed
```

### Subject Line Rules

- Use imperative mood ("add" not "added")
- No period at end
- Keep under 72 characters
- Reference issue number if applicable

---

## Pull Request Process

### Before Submitting

- [ ] Code follows project style guidelines
- [ ] Self-review completed (review your own diff!)
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] New features have tests (min 80% coverage)
- [ ] All tests pass locally (`pytest && npm test`)
- [ ] No new warnings introduced
- [ ] Commits follow conventional format
- [ ] Branch is up-to-date with main

### CI Gates You Must Pass (PR)

1. **`security`** — Trivy + secret scan
2. **`registry`** — canonical config registry structure + runtime contract + no hardcoded deployment config
3. **`advanced-checks`** — required secrets pre-check, ~14 analyzers, `ci-full-audit.sh`, pip-audit, bandit, trufflehog, gitleaks, actionlint
4. **`backend-tests`** — ruff, tiered pytest, OpenAPI validation, coverage gate (`coverage_quality_gate.py`)
5. **`integration-test`**
6. **`frontend-tests`** — single-frontend gate, strict tsc, eslint, vitest + coverage, knip
7. **`build`** — pnpm build succeeds (backend URL fail-fast must be satisfied via env)

### Toolchain Requirements

- **Node 24+** and **pnpm 10.15+** (Corepack: `corepack enable` — `packageManager` field pins it)
- **Python 3.11+** and **Poetry 2.x** (CI pins 2.4.1 and fails on lockfile drift)
- Pre-commit: `pip install pre-commit && pre-commit install` (or `bash scripts/setup-git-hooks.sh`, which also installs the SyncGuard pre-push hook)

### Repository Workflow

1. Branch from `main` using the naming conventions CI filters recognize: `feature/*`, `fix/*` (plus `docs/*`, `chore/*`, `refactor/*`, `test/*` seen in history).
2. PRs target `main` or `develop`; CI path-filters jobs (backend/frontend/infra) — use `workflow_dispatch` force inputs only when necessary.
3. Force pushes to `main`/`master` are **rejected client-side** by the SyncGuard pre-push hook (defense-in-depth where branch protection is unavailable). Bypass locally with `SKIP_CI_PARITY=1`; run the full suite before push with `RUN_FULL_TESTS=1`.
4. The pre-push hook also runs the **SyncGuard agent audit** — pushes abort on failure.

### Code Style

**Backend (Python)**
- Format/lint: **ruff** — `ruff check` + `ruff format` must pass in CI.
- Types: **mypy strict** — helper `scripts/devops/fix_mypy.py`.
- Tests colocated under `backend/tests/<topic>/`; new tests must be marked (`critical`/`important`/…).

### PR Template

```markdown
## Description
<!-- Describe your changes in detail -->

## Type of Change
- [ ] 🐛 Bug fix (non-breaking change fixing an issue)
- [ ] ✨ New feature (non-breaking change adding functionality)
- [ ] 💥 Breaking change (fix or feature causing existing functionality to change)
- [ ] 📝 Documentation update

## Related Issues
<!-- Link to related issues using Fixes #xxx or Closes #xxx -->
Fixes #(issue number)

## Screenshots (if applicable)
<!-- Add screenshots for UI changes -->

## Testing
<!-- Describe how you tested your changes -->
- [ ] Backend tests pass
- [ ] Frontend tests pass
- [ ] Manual testing completed
- [ ] Browser testing completed (Chrome, Firefox, Safari)

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review of code completed
- [ ] Comments added for complex logic
- [ ] Documentation updated (README, AGENTS.md, API docs)
- [ ] No new warnings generated
- [ ] Tests cover new functionality (80%+ coverage)
- [ ] Changes generate no new warnings
```

### Review Process

1. **Automated Checks** - CI runs tests, linting, type checking
2. **Code Review** - At least one maintainer approval required
3. **Changes Requested** - Address feedback and push new commits
4. **Approval** - All reviewers approve
5. **Merge** - Maintainer squashes and merges to main

### Merge Policy

- **Squash merge** for all PRs (clean history)
- **No merge commits** (use rebase if needed)
- **Main branch protection** enabled (requires PR, status checks passing)

---

## Community

### Getting Help

- **Questions**: Use GitHub Discussions
- **Bugs**: Open an issue with reproduction steps
- **Features**: Open an issue with proposal
- **Security**: Email security@supremeai.app (DO NOT open public issue)

### Recognition

Contributors are recognized in:
- README.md Contributors section
- Release notes for significant contributions
- Annual community highlights blog post

### Ways to Contribute

Not just code! You can contribute by:

- 📝 Writing documentation
- 🐛 Reporting bugs
- 💡 Suggesting features
- ✅ Reviewing PRs
- 🌍 Translations
- 🎨 Design improvements
- 📢 Sharing the project
- ❓ Answering questions

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to SupremeAI! 🚀
