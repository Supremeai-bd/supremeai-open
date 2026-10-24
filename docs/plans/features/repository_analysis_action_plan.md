---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:repository_analysis_action_plan
subject: SupremeAI - GitHub Repository Analysis & Action Plan
document_role: audit
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI - GitHub Repository Analysis & Action Plan
## Repository: https://github.com/paykaribazaronline/supremeai
## Analysis Date: 2026-04-26

---

# 1. Current Repository State

## 1.1 Detected Structure
```
supremeai/
├── .github/
│   └── workflows/
│       └── ci.yml              # CI/CD pipeline
├── src/
│   ├── main.py                 # Main entry point
│   ├── config.py               # Configuration
│   ├── agents/
│   │   └── base_agent.py       # Base agent class
│   └── utils/
│       └── helpers.py          # Utility functions
├── tests/
│   └── test_main.py            # Basic tests
├── requirements.txt            # Dependencies
└── README.md                   # Project documentation
```

## 1.2 Current Status Assessment
| Aspect | Status | Notes |
|--------|--------|-------|
| **Code Structure** | 🟡 Basic | Single agent, no orchestration |
| **CI/CD** | 🟡 Minimal | Basic workflow exists |
| **Testing** | 🔴 Insufficient | Only one test file |
| **Documentation** | 🟡 Basic | README only |
| **Configuration** | 🟡 Hardcoded | No environment management |
| **Multi-Agent** | 🔴 Missing | Plan 1 not implemented |
| **API Rotation** | 🔴 Missing | Plan 2 not implemented |
| **Learning System** | 🔴 Missing | Plan 3 not implemented |
| **Intent Analysis** | 🔴 Missing | Plan 4 not implemented |
| **GitHub Integration** | 🟡 Partial | Basic CI only |

---

# 2. Problems Identified (Current vs Planned)

## 2.1 Critical Gaps (Must Fix)

### Gap 1: No Multi-Agent System
**Current:** Single `base_agent.py`
**Required:** Dynamic 0 to ∞ agents with task orchestration
**Impact:** Core functionality missing

### Gap 2: No API Key Management
**Current:** `config.py` likely hardcoded
**Required:** Rotation system with multiple keys
**Impact:** Cannot scale, will hit rate limits

### Gap 3: No Learning Mechanism
**Current:** Static code
**Required:** Self-updating knowledge base
**Impact:** System cannot improve over time

### Gap 4: No Intent Analysis
**Current:** Direct command processing
**Required:** Smart confirmation system
**Impact:** Risk of misinterpretation

### Gap 5: No Dual Repo Support
**Current:** Single repo (own)
**Required:** Main + User repo management
**Impact:** Cannot serve users

## 2.2 Infrastructure Gaps

### Gap 6: Database Missing
**Current:** No database layer
**Required:** SQLite/PostgreSQL for:
- User preferences
- Agent performance
- API key status
- Conversation history
- Plan compatibility data

### Gap 7: No Web Interface
**Current:** CLI only (assumed)
**Required:** Dashboard for:
- Admin settings
- User chat interface
- API key management
- Plan visualization

### Gap 8: No GitHub App/Bot
**Current:** Basic CI workflow
**Required:** GitHub App for:
- User repo access
- Auto-push capability
- Pre-push verification
- Webhook handling

### Gap 9: Testing Insufficient
**Current:** `test_main.py` only
**Required:** Comprehensive test suite:
- Unit tests for each module
- Integration tests
- CI/CD pipeline tests
- Mock API tests

### Gap 10: No Error Handling
**Current:** Basic (assumed)
**Required:** Robust error handling:
- API failure fallback
- Network retry logic
- Graceful degradation
- User-friendly error messages

---

# 3. Changes Required - Priority Order

## Phase 1: Foundation (Weeks 1-4)

### 3.1 Project Structure Overhaul
```
supremeai/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── src/
│   ├── __init__.py
│   ├── main.py                    # Entry point
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py            # Environment-based config
│   │   └── constants.py           # Constants
│   ├── core/
│   │   ├── __init__.py
│   │   ├── orchestrator.py        # Plan 1: Agent orchestrator
│   │   ├── intent_analyzer.py     # Plan 4: Intent analysis
│   │   └── plan_manager.py        # Plan 5: Plan compatibility
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py          # Base class
│   │   ├── agent_pool.py          # Plan 1: Dynamic pool
│   │   └── performance_tracker.py # Plan 1: Performance tracking
│   ├── api/
│   │   ├── __init__.py
│   │   ├── key_manager.py         # Plan 2: Key rotation
│   │   ├── key_validator.py       # Plan 10: Limit discovery
│   │   └── rotation_strategy.py   # Plan 2: Rotation logic
│   ├── learning/
│   │   ├── __init__.py
│   │   ├── knowledge_base.py      # Plan 3: Knowledge storage
│   │   ├── web_scraper.py         # Plan 3: Web learning
│   │   └── pattern_learner.py     # Plan 20: Example learning
│   ├── github/
│   │   ├── __init__.py
│   │   ├── repo_manager.py        # Plan 6: Dual repo
│   │   ├── push_verifier.py       # Plan 11: Pre-push verify
│   │   └── webhook_handler.py     # GitHub webhooks
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py            # Database layer
│   │   ├── data_lifecycle.py      # Plan 17: Auto-expiry
│   │   └── selective_storage.py   # Plan 9: Smart storage
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── speech_to_text.py      # Plan 15: Voice input
│   │   └── intent_pre_analyzer.py # Plan 15: Pre-analysis
│   ├── vision/
│   │   ├── __init__.py
│   │   └── image_processor.py     # Plan 14: Image understanding
│   ├── marketing/
│   │   ├── __init__.py
│   │   └── strategy_advisor.py    # Plan 13: Marketing
│   ├── platform/
│   │   ├── __init__.py
│   │   └── multi_platform.py      # Plan 12: Multi-platform
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── admin_dashboard.py     # Plan 7: Admin settings
│   │   └── user_interface.py      # User chat UI
│   ├── voting/
│   │   ├── __init__.py
│   │   ├── voting_system.py       # Voting mechanism
│   │   └── result_analyzer.py     # Result analysis
│   ├── court/
│   │   ├── __init__.py
│   │   └── error_checker.py       # Court error checking
│   └── utils/
│       ├── __init__.py
│       ├── helpers.py
│       └── logger.py              # Logging
├── tests/
│   ├── __init__.py
│   ├── test_orchestrator.py
│   ├── test_key_manager.py
│   ├── test_intent_analyzer.py
│   ├── test_repo_manager.py
│   └── test_learning.py
├── docs/
│   ├── architecture.md
│   ├── api_reference.md
│   └── deployment_guide.md
├── scripts/
│   ├── setup.sh
│   └── deploy.sh
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
└── README.md
```

### 3.2 Database Schema (SQLite/PostgreSQL)
```sql
-- Users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    github_username TEXT UNIQUE,
    trust_level INTEGER DEFAULT 0, -- 0=low, 1=high
    preferred_language TEXT DEFAULT 'en',
    auto_approve BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- API Keys table
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    provider TEXT, -- openai, anthropic, etc.
    key_hash TEXT, -- Hashed key
    is_active BOOLEAN DEFAULT TRUE,
    usage_count INTEGER DEFAULT 0,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Agents table
CREATE TABLE agents (
    id INTEGER PRIMARY KEY,
    name TEXT,
    model TEXT,
    specialization TEXT, -- code, court, vote, etc.
    performance_score REAL DEFAULT 0.0,
    task_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tasks table
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    agent_id INTEGER,
    type TEXT, -- code_writing, court_check, etc.
    status TEXT, -- pending, running, completed, failed
    input TEXT,
    output TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id)
);

-- Knowledge Base table
CREATE TABLE knowledge (
    id INTEGER PRIMARY KEY,
    topic TEXT,
    content TEXT,
    source TEXT, -- web, user, system
    confidence REAL DEFAULT 0.0,
    is_permanent BOOLEAN DEFAULT FALSE,
    expiry_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User Repos table
CREATE TABLE user_repos (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    repo_url TEXT,
    has_bot_installed BOOLEAN DEFAULT FALSE,
    access_level TEXT, -- read, write
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Plans table
CREATE TABLE plans (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    name TEXT,
    description TEXT,
    status TEXT, -- active, completed, rejected
    parent_plan_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Conversations table
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    message TEXT,
    intent_type TEXT, -- rule, planning, command
    is_confirmed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 3.3 Environment Configuration (.env.example)
```bash
# Database
DATABASE_URL=sqlite:///supremeai.db
# DATABASE_URL=postgresql://user:pass@localhost/supremeai

# GitHub
GITHUB_TOKEN=your_github_token
GITHUB_APP_ID=your_app_id
GITHUB_APP_PRIVATE_KEY=your_private_key

# API Keys (System fallback)
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_API_KEY=your_google_key

# Application
DEBUG=False
SECRET_KEY=your_secret_key
PORT=8000
HOST=0.0.0.0

# Features
ENABLE_VOICE=False
ENABLE_VISION=False
ENABLE_LEARNING=True
AUTO_APPROVE=False
```

---

## Phase 2: Core Implementation (Weeks 5-8)

### 3.4 Agent Orchestrator (Plan 1)
```python
# src/core/orchestrator.py
class AgentOrchestrator:
    def __init__(self):
        self.agent_pool = AgentPool()
        self.performance_tracker = PerformanceTracker()

    def assign_task(self, task_type, task_input):
        # Get best 3 agents for this task type
        best_agents = self.performance_tracker.get_best_agents(
            task_type, 
            limit=3
        )

        if not best_agents:
            # Fallback to system AI
            return self.system_ai_handle(task_type, task_input)

        # Assign to top agent
        selected_agent = best_agents[0]
        return selected_agent.execute(task_input)

    def update_performance(self, agent_id, task_id, success, duration):
        self.performance_tracker.record(
            agent_id=agent_id,
            task_id=task_id,
            success=success,
            duration=duration
        )
```

### 3.5 API Key Manager (Plan 2)
```python
# src/api/key_manager.py
class APIKeyManager:
    def __init__(self):
        self.keys = {}
        self.rotation_threshold = 0.8  # 80%

    def add_key(self, provider, key, user_id=None):
        # Validate key first
        if self.validate_key(provider, key):
            self.keys[provider] = {
                'key': key,
                'user_id': user_id,
                'usage': 0,
                'limit': self.discover_limit(provider, key)
            }
            return True
        return False

    def get_key(self, provider):
        key_data = self.keys.get(provider)
        if not key_data:
            return None

        # Check if near limit
        usage_ratio = key_data['usage'] / key_data['limit']
        if usage_ratio >= self.rotation_threshold:
            # Try to rotate
            rotated = self.rotate_key(provider)
            if rotated:
                return rotated
            # Fallback to system AI
            return 'SYSTEM_AI_FALLBACK'

        key_data['usage'] += 1
        return key_data['key']

    def validate_key(self, provider, key):
        # Real validation logic
        pass

    def discover_limit(self, provider, key):
        # Plan 10: Auto-discover limit
        pass

    def rotate_key(self, provider):
        # Find next available key
        pass
```

### 3.6 Intent Analyzer (Plan 4)
```python
# src/core/intent_analyzer.py
class IntentAnalyzer:
    def __init__(self):
        self.confidence_threshold = 0.7

    def analyze(self, user_message, context):
        # Determine intent type
        intent_type = self.classify_intent(user_message)

        # Extract entities
        entities = self.extract_entities(user_message)

        # Calculate confidence
        confidence = self.calculate_confidence(user_message, context)

        if confidence < self.confidence_threshold:
            # Ask for confirmation
            return {
                'intent': intent_type,
                'entities': entities,
                'confidence': confidence,
                'needs_confirmation': True,
                'suggested_action': self.suggest_action(intent_type, entities)
            }

        return {
            'intent': intent_type,
            'entities': entities,
            'confidence': confidence,
            'needs_confirmation': False
        }

    def classify_intent(self, message):
        # Rule, Planning, or Command
        pass

    def confirm_intent(self, intent_data, user_confirmation):
        if user_confirmation:
            self.save_to_database(intent_data)
        return user_confirmation
```

---

## Phase 3: Integration (Weeks 9-12)

### 3.7 GitHub Integration (Plan 6, 11)
```python
# src/github/repo_manager.py
class RepoManager:
    def __init__(self, github_token):
        self.github = Github(github_token)

    def push_to_user_repo(self, user_id, repo_url, code_changes):
        # Check if user has bot installed
        repo = self.get_repo(repo_url)

        if not self.has_bot_installed(repo):
            # Manual mode: return code for user to apply
            return {
                'mode': 'manual',
                'code': code_changes,
                'instructions': 'Please apply these changes manually'
            }

        # Auto mode: verify and push
        verification = self.verify_changes(repo, code_changes)
        if verification['has_conflicts']:
            return {
                'mode': 'review_required',
                'conflicts': verification['conflicts'],
                'suggestion': verification['suggestion']
            }

        # Safe to push
        return self.push_changes(repo, code_changes)

    def verify_changes(self, repo, changes):
        # Check for others' changes
        # Plan 11: Pre-push verification
        pass
```

### 3.8 Learning System (Plan 3)
```python
# src/learning/knowledge_base.py
class KnowledgeBase:
    def __init__(self):
        self.db = Database()
        self.scraper = WebScraper()

    def learn_topic(self, topic, admin_approved=True):
        if not admin_approved:
            return {'status': 'pending_approval'}

        # Scrape web for knowledge
        web_data = self.scraper.search(topic)

        # Process and store
        for item in web_data:
            self.db.insert('knowledge', {
                'topic': topic,
                'content': item['content'],
                'source': item['source'],
                'confidence': item['confidence']
            })

        return {'status': 'learned', 'items': len(web_data)}

    def query(self, topic, min_confidence=0.5):
        return self.db.query(
            'SELECT * FROM knowledge WHERE topic = ? AND confidence >= ?',
            (topic, min_confidence)
        )
```

---

## Phase 4: Advanced Features (Weeks 13-16)

### 3.9 Voice Integration (Plan 15)
```python
# src/voice/speech_to_text.py
class VoiceProcessor:
    def __init__(self):
        self.primary_engine = 'web_speech_api'
        self.fallback_engine = 'whisper'

    def process(self, audio_input):
        # Try primary
        text = self.web_speech_convert(audio_input)

        if not text or self.confidence_low(text):
            # Fallback to Whisper
            text = self.whisper_convert(audio_input)

        # Pre-analyze intent
        intent = self.pre_analyze(text)

        return {
            'text': text,
            'intent': intent,
            'confidence': intent['confidence']
        }
```

### 3.10 Vision Integration (Plan 14)
```python
# src/vision/image_processor.py
class ImageProcessor:
    def __init__(self):
        self.vision_api = VisionAPI()

    def process(self, image_data):
        # Detect image type
        image_type = self.detect_type(image_data)

        if image_type == 'error_screenshot':
            return self.analyze_error(image_data)
        elif image_type == 'code_snippet':
            return self.extract_code(image_data)
        else:
            return self.describe_image(image_data)

    def analyze_error(self, image):
        # OCR + error pattern matching
        pass
```

---

## Phase 5: Simulator Controller (Weeks 17-24)

### 3.11 Core Model & Persistence (Plan 22)

**Spring Boot Package Structure:**
```
src/main/java/com/supremeai/
├── controller/
│   └── SimulatorController.java          # REST endpoints
├── model/
│   └── UserSimulatorProfile.java         # Expanded entity
├── repository/
│   └── SimulatorProfileRepository.java   # Firestore DAO
├── service/
│   └── SimulatorService.java             # Business logic
├── config/
│   └── SimulatorConfig.java              # Configuration properties
└── websocket/
    └── SimulatorWebSocketHandler.java    # Real-time comms
```

**Expanded Model (Java):**
```java
@Entity
@Document(collectionName = "simulator_profiles")
public class UserSimulatorProfile {
    
    @Id
    private String userId;
    private int installQuota = 5;
    private int activeInstalls = 0;
    private LocalDateTime lastActiveAt;
    
    @ElementCollection
    private List<SimulatorApp> installedApps = new ArrayList<>();
    
    @Embedded
    private SimulatorDevice device = new SimulatorDevice();
    
    @Embedded
    private SimulatorSession currentSession;
    
    @ElementCollection
    private List<QuotaHistory> quotaHistory = new ArrayList<>();
    
    // Getters & Setters
}

public class SimulatorApp {
    private String appId;
    private String appName;
    private String version;
    private String deployedUrl;        // Cloud Run URL
    private LocalDateTime installedAt;
    private int launchCount;
    private LocalDateTime lastLaunchedAt;
    private SimulatorAppStatus status; // INSTALLED, RUNNING, ERROR
}

public class SimulatorDevice {
    private DeviceType type = DeviceType.PIXEL_6;
    private String osVersion = "Android 14";
    private String screenResolution = "1080x2340";
    private int densityDpi = 440;
}

public class SimulatorSession {
    private String sessionId;
    private String activeAppId;
    private String sessionUrl;        // WebSocket URL
    private LocalDateTime startedAt;
    private LocalDateTime lastHeartbeat;
    private SessionState state;       // ACTIVE, PAUSED, TERMINATED
}
```

**Firestore Repository:**
```java
@Repository
public class SimulatorProfileRepository {
    
    @Autowired
    private Firestore firestore;
    
    private final CollectionReference collection;
    
    public SimulatorProfileRepository(Firestore firestore) {
        this.firestore = firestore;
        this.collection = firestore.collection("simulator_profiles");
    }
    
    public Optional<UserSimulatorProfile> findByUserId(String userId) {
        try {
            DocumentSnapshot doc = collection.document(userId).get().get();
            if (doc.exists()) {
                return Optional.of(doc.toObject(UserSimulatorProfile.class));
            }
            return Optional.empty();
        } catch (Exception e) {
            return Optional.empty();
        }
    }
    
    public void save(UserSimulatorProfile profile) {
        try {
            Map<String, Object> data = new HashMap<>();
            // ... populate map from profile object
            collection.document(profile.getUserId())
                .set(data, SetOptions.merge())
                .get();
        } catch (Exception e) {
            throw new DataAccessException("Failed to save simulator profile", e);
        }
    }
    
    public List<UserSimulatorProfile> findAllProfiles() {
        try {
            ApiFuture<QuerySnapshot> future = collection.get();
            List<QueryDocumentSnapshot> documents = future.get().getDocuments();
            return documents.stream()
                .map(doc -> doc.toObject(UserSimulatorProfile.class))
                .collect(Collectors.toList());
        } catch (Exception e) {
            return Collections.emptyList();
        }
    }
}
```

### 3.12 Installation Workflow & Quota Enforcement

```java
@Service
@Slf4j
public class SimulatorService {
    
    @Autowired
    private SimulatorProfileRepository profileRepository;
    
    @Autowired
    private AppDeploymentService deploymentService;
    
    @Autowired
    private AuditLogService auditLogService;
    
    @Value("${simulator.max.installs.per.user:5}")
    private int defaultQuota;
    
    /**
     * Install app to user's simulator with atomic quota check
     * Thread-safe via Firestore transactions
     */
    @Transactional
    public SimulatorInstallResult installApp(String userId, String appId, String deviceType) {
        UserSimulatorProfile profile = profileRepository.findByUserId(userId)
            .orElseGet(() -> createNewProfile(userId));
        
        // Check quota
        if (profile.getActiveInstalls() >= profile.getInstallQuota()) {
            log.warn("Quota exceeded for user {}: {}/{}", 
                userId, profile.getActiveInstalls(), profile.getInstallQuota());
            throw new SimulatorQuotaExceededException(
                "Quota exceeded: " + profile.getActiveInstalls() + "/" + profile.getInstallQuota()
            );
        }
        
        // Check duplicate
        boolean alreadyInstalled = profile.getInstalledApps().stream()
            .anyMatch(app -> app.getAppId().equals(appId));
        if (alreadyInstalled) {
            throw new SimulatorConflictException("App already installed");
        }
        
        // Validate app belongs to user (query app repository)
        GeneratedApp app = appRepository.findByAppIdAndUserId(appId, userId);
        if (app == null) {
            throw new ResourceNotFoundException("App not found or unauthorized");
        }
        
        // Deploy to Cloud Run preview environment
        String previewUrl = deploymentService.deployToSimulator(app, deviceType);
        
        // Create installed app entry
        SimulatorApp installedApp = new SimulatorApp();
        installedApp.setAppId(appId);
        installedApp.setAppName(app.getName());
        installedApp.setVersion(app.getVersion());
        installedApp.setDeployedUrl(previewUrl);
        installedApp.setInstalledAt(LocalDateTime.now());
        installedApp.setStatus(SimulatorAppStatus.INSTALLED);
        
        // Update profile atomically
        profile.getInstalledApps().add(installedApp);
        profile.setActiveInstalls(profile.getActiveInstalls() + 1);
        profile.setLastActiveAt(LocalDateTime.now());
        profileRepository.save(profile);
        
        // Audit log
        auditLogService.log("APP_INSTALL", userId, Map.of(
            "appId", appId,
            "device", deviceType,
            "previewUrl", previewUrl
        ));
        
        return new SimulatorInstallResult(profile, installedApp);
    }
    
    public void uninstallApp(String userId, String appId) {
        UserSimulatorProfile profile = profileRepository.findByUserId(userId)
            .orElseThrow(() -> new ResourceNotFoundException("Profile not found"));
        
        SimulatorApp appToRemove = profile.getInstalledApps().stream()
            .filter(app -> app.getAppId().equals(appId))
            .findFirst()
            .orElseThrow(() -> new ResourceNotFoundException("App not installed"));
        
        // Stop session if active
        if (profile.getCurrentSession() != null && 
            profile.getCurrentSession().getActiveAppId().equals(appId)) {
            stopSession(userId);
        }
        
        // Decrement counters
        profile.getInstalledApps().remove(appToRemove);
        profile.setActiveInstalls(profile.getActiveInstalls() - 1);
        profileRepository.save(profile);
        
        auditLogService.log("APP_UNINSTALL", userId, Map.of("appId", appId));
    }
    
    private UserSimulatorProfile createNewProfile(String userId) {
        UserSimulatorProfile profile = new UserSimulatorProfile();
        profile.setUserId(userId);
        profile.setInstallQuota(defaultQuota);
        profile.setActiveInstalls(0);
        profile.setDevice(new SimulatorDevice());
        return profile;
    }
}
```

### 3.13 Simulator Deployment Service (Cloud Run)

```java
@Service
@Slf4j
public class SimulatorDeploymentService {
    
    @Value("${simulator.cloudrun.region:us-central1}")
    private String region;
    
    @Value("${simulator.cloudrun.memory:2Gi}")
    private String memory;
    
    @Value("${simulator.cloudrun.cpu:1}")
    private String cpu;
    
    @Value("${simulator.preview.url.format}")
    private String urlFormat;
    
    /**
     * Deploy generated app to Cloud Run preview environment
     * Each installed app gets its own isolated Cloud Run service
     */
    public String deployToSimulator(GeneratedApp app, String deviceType) {
        String serviceName = "sim-" + app.getAppId().toLowerCase();
        String imageUrl = app.getDockerImageUrl();
        
        try {
            // Using Google Cloud Run client
            Service service = CloudRunService.newBuilder()
                .setMetadata(ServiceMetadata.newBuilder()
                    .setName(serviceName)
                    .setNamespace("supremeai")
                    .setLabels(Map.of(
                        "app-id", app.getAppId(),
                        "device", deviceType,
                        "simulator", "true",
                        "user-id", app.getUserId()
                    ))
                    .build())
                .setSpec(ServiceSpec.newBuilder()
                    .setTemplate(ServiceTemplate.newBuilder()
                        .setMetadata(ContainerInstanceMetadata.newBuilder()
                            .setLabels(Map.of(
                                "app-id", app.getAppId(),
                                "simulator", "true"
                            ))
                            .build())
                        .setSpec(ContainerInstanceSpec.newBuilder()
                            .setContainers(List.of(
                                Container.newBuilder()
                                    .setImage(imageUrl)
                                    .setResources(ResourceRequirements.newBuilder()
                                        .setLimits(Map.of(
                                            "memory", memory,
                                            "cpu", cpu
                                        ))
                                        .build())
                                    .addPorts(ContainerPort.newBuilder()
                                        .setContainerPort(8080)
                                        .build())
                                    .addEnvVars(ContainerEnvVar.newBuilder()
                                        .setName("SIMULATOR_MODE")
                                        .setValue("true")
                                        .build())
                                    .build()
                            ))
                            .setTimeoutSeconds(
                                Integer.parseInt(
                                    System.getenv().getOrDefault(
                                        "SIMULATOR_DEPLOY_TIMEOUT", "120"
                                    )
                                )
                            )
                            .build())
                        .build())
                    .build())
                .build();
            
            // Deploy service (async)
            ApiFuture<Operation> future = cloudRunClient.createService(
                CreateServiceRequest.newBuilder()
                    .setParent(parent)
                    .setService(service)
                    .build()
            );
            
            // Wait for deployment to complete
            future.get();
            
            String previewUrl = String.format(urlFormat, 
                Pattern.compile("\\{appId\\}").matcher(serviceName).replaceAll(app.getAppId()));
            log.info("Deployed simulator for app {} at {}", app.getAppId(), previewUrl);
            return previewUrl;
            
        } catch (Exception e) {
            log.error("Failed to deploy simulator for app " + app.getAppId(), e);
            throw new SimulatorDeploymentException("Simulator deployment failed", e);
        }
    }
    
    /**
     * Scheduled task: Clean up expired simulator apps (older than configurable TTL)
     */
    @Scheduled(cron = "0 0 2 * * *")  // Daily at 2 AM UTC
    @Transactional
    public void cleanupExpiredApps() {
        log.info("Starting simulator cleanup job");
        
        List<UserSimulatorProfile> allProfiles = profileRepository.findAllProfiles();
        LocalDateTime expiryThreshold = LocalDateTime.now()
            .minusDays(
                Integer.parseInt(
                    System.getenv().getOrDefault("SIMULATOR_APP_EXPIRY_DAYS", "7")
                )
            );
        
        int totalCleaned = 0;
        
        for (UserSimulatorProfile profile : allProfiles) {
            boolean modified = false;
            Iterator<SimulatorApp> iterator = profile.getInstalledApps().iterator();
            
            while (iterator.hasNext()) {
                SimulatorApp app = iterator.next();
                if (app.getInstalledAt().isBefore(expiryThreshold)) {
                    // Delete Cloud Run service
                    deleteCloudRunService("sim-" + app.getAppId());
                    iterator.remove();
                    modified = true;
                    profile.setActiveInstalls(profile.getActiveInstalls() - 1);
                    totalCleaned++;
                    log.info("Cleaned up expired app {} for user {}", 
                        app.getAppId(), profile.getUserId());
                }
            }
            
            if (modified) {
                profileRepository.save(profile);
            }
        }
        
        log.info("Simulator cleanup complete: {} apps removed", totalCleaned);
    }
    
    private void deleteCloudRunService(String serviceName) {
        try {
            ApiFuture<Operation> future = cloudRunClient.deleteService(
                DeleteServiceRequest.newBuilder()
                    .setName(ServiceName.of(region, "supremeai", serviceName).toString())
                    .build()
            );
            future.get();  // Wait for deletion
        } catch (Exception e) {
            log.warn("Failed to delete Cloud Run service: " + serviceName, e);
        }
    }
}
```

### 3.14 Real-time Session Management (WebSocket)

```java
@EnableWebSocket
@Component
@Slf4j
public class SimulatorWebSocketHandler extends TextWebSocketHandler {
    
    private static final Map<String, WebSocketSession> sessions = 
        new ConcurrentHashMap<>();
    private static final Map<String, SimulatorSession> sessionStates = 
        new ConcurrentHashMap<>();
    
    @Autowired
    private SimulatorService simulatorService;
    
    @Autowired
    private AuditLogService auditLogService;
    
    private final ObjectMapper objectMapper = new ObjectMapper();
    
    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        String sessionId = session.getId();
        sessions.put(sessionId, session);
        
        SimulatorSession simulatorSession = new SimulatorSession();
        simulatorSession.setSessionId(sessionId);
        simulatorSession.setState(SessionState.ACTIVE);
        simulatorSession.setStartedAt(LocalDateTime.now());
        simulatorSession.setLastHeartbeat(LocalDateTime.now());
        sessionStates.put(sessionId, simulatorSession);
        
        log.info("WebSocket connected: sessionId={}", sessionId);
    }
    
    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        String payload = message.getPayload();
        JsonNode json = objectMapper.readTree(payload);
        
        String type = json.get("type").asText();
        String sessionId = session.getId();
        SimulatorSession simSession = sessionStates.get(sessionId);
        
        if (simSession == null) {
            session.close(CloseStatus.NOT_ACCEPTABLE.withReason("Session not found"));
            return;
        }
        
        switch (type) {
            case "heartbeat":
                simSession.setLastHeartbeat(LocalDateTime.now());
                session.sendMessage(new TextMessage("{\"type\":\"heartbeat_ack\"}"));
                break;
                
            case "user_input":
                // Forward touch/gesture events to simulator container
                forwardToSimulator(sessionId, json);
                break;
                
            case "session_stop":
                simulatorService.stopSession(simSession.getUserId());
                session.close();
                auditLogService.log("SESSION_STOP", simSession.getUserId(), Map.of(
                    "sessionId", sessionId
                ));
                break;
                
            case "session_pause":
                simSession.setState(SessionState.PAUSED);
                sendToSimulator(sessionId, Map.of("type", "pause"));
                break;
                
            case "session_resume":
                simSession.setState(SessionState.ACTIVE);
                sendToSimulator(sessionId, Map.of("type", "resume"));
                break;
                
            default:
                log.warn("Unknown WebSocket message type: {}", type);
        }
    }
    
    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) throws Exception {
        String sessionId = session.getId();
        sessions.remove(sessionId);
        
        SimulatorSession simSession = sessionStates.remove(sessionId);
        if (simSession != null) {
            log.info("WebSocket disconnected: sessionId={}, state={}", 
                sessionId, simSession.getState());
            // Auto-cleanup of Cloud Run service after timeout
        }
    }
    
    private void forwardToSimulator(String sessionId, JsonNode data) throws Exception {
        WebSocketSession session = sessions.get(sessionId);
        if (session != null && session.isOpen()) {
            // Forward to simulator container via backend channel
            simulatorMessageChannel.send(SimulatorMessage.builder()
                .sessionId(sessionId)
                .payload(data.toString())
                .timestamp(LocalDateTime.now())
                .build());
        }
    }
    
    /**
     * Health check: Remove stale sessions (>30 min inactive)
     */
    @Scheduled(fixedDelay = 600000)  // Every 10 minutes
    public void cleanupStaleSessions() {
        LocalDateTime cutoff = LocalDateTime.now().minusMinutes(30);
        
        sessionStates.entrySet().removeIf(entry -> {
            SimulatorSession session = entry.getValue();
            if (session.getLastHeartbeat().isBefore(cutoff)) {
                log.info("Terminating stale session: {}", session.getSessionId());
                sessions.remove(entry.getKey());
                return true;
            }
            return false;
        });
    }
}
```

### 3.15 Admin Operations & Monitoring

```java
@RestController
@RequestMapping("/api/simulator/admin")
@PreAuthorize("hasRole('ADMIN')")
@Slf4j
public class SimulatorAdminController {
    
    @Autowired
    private SimulatorProfileRepository profileRepository;
    
    @Autowired
    private AuditLogService auditLogService;
    
    @Autowired
    private SimulatorMetrics metrics;
    
    /**
     * Get simulator usage across all users (admin view)
     */
    @GetMapping("/usage")
    public Map<String, Object> getAllUsersUsage() {
        List<UserSimulatorProfile> allProfiles = profileRepository.findAllProfiles();
        
        int totalUsers = allProfiles.size();
        int totalActiveInstalls = allProfiles.stream()
            .mapToInt(UserSimulatorProfile::getActiveInstalls)
            .sum();
        long totalSessions = allProfiles.stream()
            .filter(p -> p.getCurrentSession() != null)
            .count();
        
        List<Map<String, Object>> userSummaries = allProfiles.stream()
            .map(profile -> Map.of(
                "userId", profile.getUserId(),
                "activeInstalls", profile.getActiveInstalls(),
                "installQuota", profile.getInstallQuota(),
                "installedApps", profile.getInstalledApps().stream()
                    .map(app -> Map.of(
                        "appId", app.getAppId(),
                        "appName", app.getAppName(),
                        "status", app.getStatus().name()
                    ))
                    .collect(Collectors.toList()),
                "hasActiveSession", profile.getCurrentSession() != null
            ))
            .collect(Collectors.toList());
        
        Map<String, Object> response = new HashMap<>();
        response.put("totalUsers", totalUsers);
        response.put("totalActiveInstalls", totalActiveInstalls);
        response.put("totalActiveSessions", totalSessions);
        response.put("users", userSummaries);
        response.put("generatedAt", LocalDateTime.now());
        
        auditLogService.log("ADMIN_USAGE_VIEW", "system", Map.of(
            "resultCount", totalUsers
        ));
        
        return response;
    }
    
    /**
     * Admin override: force-set user quota
     */
    @PostMapping("/force-quota/{userId}")
    public ResponseEntity<?> overrideQuota(
            @PathVariable String userId,
            @RequestParam int newQuota,
            @AuthenticationPrincipal User admin) {
        
        UserSimulatorProfile profile = profileRepository.findByUserId(userId)
            .orElseThrow(() -> new ResourceNotFoundException("User not found"));
        
        int oldQuota = profile.getInstallQuota();
        profile.setInstallQuota(newQuota);
        profileRepository.save(profile);
        
        auditLogService.log("ADMIN_QUOTA_OVERRIDE", admin.getUsername(), Map.of(
            "userId", userId,
            "oldQuota", oldQuota,
            "newQuota", newQuota
        ));
        
        return ResponseEntity.ok(Map.of(
            "success", true,
            "userId", userId,
            "oldQuota", oldQuota,
            "newQuota", newQuota
        ));
    }
    
    /**
     * Force-kill a user's active session
     */
    @PostMapping("/kill-session/{userId}")
    public ResponseEntity<?> killUserSession(@PathVariable String userId) {
        UserSimulatorProfile profile = profileRepository.findByUserId(userId)
            .orElse(null);
        
        if (profile != null && profile.getCurrentSession() != null) {
            String sessionId = profile.getCurrentSession().getSessionId();
            // Close WebSocket
            WebSocketSession wsSession = SimulatorWebSocketHandler.sessions.get(sessionId);
            if (wsSession != null && wsSession.isOpen()) {
                try {
                    wsSession.close();
                } catch (IOException e) {
                    log.error("Failed to close WebSocket", e);
                }
            }
            
            profile.setCurrentSession(null);
            profileRepository.save(profile);
            
            auditLogService.log("ADMIN_KILL_SESSION", "system", Map.of(
                "userId", userId,
                "sessionId", sessionId
            ));
            
            return ResponseEntity.ok(Map.of("killed", true, "sessionId", sessionId));
        }
        
        return ResponseEntity.ok(Map.of("killed", false, "reason", "No active session"));
    }
    
    /**
     * Cleanup stale/inactive simulator sessions manually
     */
    @DeleteMapping("/cleanup")
    public CleanupResult cleanupStaleSessions() {
        CleanupResult result = new CleanupResult();
        
        // Use same logic as scheduled job, but immediate
        // (logic from SimulatorDeploymentService.cleanupExpiredApps)
        
        result.setCleanedAt(LocalDateTime.now());
        return result;
    }
    
    /**
     * Prometheus metrics aggregation
     */
    @GetMapping("/metrics")
    public Map<String, Double> getMetrics() {
        return Map.of(
            "activeSessions", (double) metrics.getActiveSessions(),
            "totalInstalls", metrics.getTotalInstalls(),
            "quotaExceededRate", metrics.getQuotaExceededRate(),
            "avgInstallLatencySec", metrics.getAvgInstallLatency()
        );
    }
    
    /**
     * Get detailed audit log
     */
    @GetMapping("/audit")
    public List<AuditLogEntry> getAuditLog(
            @RequestParam(required = false) String userId,
            @RequestParam(required = false) String action,
            @RequestParam(defaultValue = "100") int limit) {
        
        return auditLogService.getLogs(userId, action, limit);
    }
}
```

### 3.16 Frontend UI Integration (React + TypeScript + Ant Design)

**File:** `dashboard/src/components/SimulatorPanel.tsx`

```tsx
import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Button, 
  Progress, 
  Select, 
  Modal, 
  message,
  Spin,
  Empty,
  Tag,
  Tooltip,
  Row,
  Col,
  Statistic,
  Table
} from 'antd';
import { 
  PlayCircleOutlined, 
  DeleteOutlined, 
  PlusOutlined,
  CloudUploadOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons';
import type { SimulatorApp, SimulatorProfile } from '../types/simulator';

const { Option } = Select;
const { confirm } = Modal;

export const SimulatorPanel: React.FC = () => {
  const [profile, setProfile] = useState<SimulatorProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState<DeviceType>('PIXEL_6');
  const [showAddApp, setShowAddApp] = useState(false);
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);
  
  // Fetch user's simulator profile
  const fetchProfile = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/simulator/profile/me', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      });
      const data = await response.json();
      setProfile(data);
    } catch (error) {
      message.error('Failed to load simulator profile');
    } finally {
      setLoading(false);
    }
  };
  
  useEffect(() => {
    fetchProfile();
  }, []);
  
  // Launch app in new browser window
  const launchApp = (app: SimulatorApp) => {
    if (app.deployedUrl) {
      // Open simulator in new window with specific dimensions for mobile frame
      const width = 414;  // iPhone/Pixel width
      const height = 896; // iPhone/Pixel height
      const left = (screen.width - width) / 2;
      const top = (screen.height - height) / 2;
      
      window.open(
        app.deployedUrl, 
        `simulator-${app.appId}`,
        `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
      );
      
      // Record launch via API
      fetch('/api/simulator/launch', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ appId: app.appId })
      });
    }
  };
  
  // Install new app
  const installApp = async (appId: string) => {
    try {
      const response = await fetch('/api/simulator/install', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ 
          appId, 
          deviceProfile: selectedDevice 
        })
      });
      
      if (response.ok) {
        message.success('App installed successfully');
        fetchProfile();
        setShowAddApp(false);
      } else {
        const error = await response.json();
        if (response.status === 409) {
          message.error('Quota exceeded. Uninstall an app first or contact admin for quota increase.');
        } else {
          message.error(error.message || 'Install failed');
        }
      }
    } catch (error) {
      message.error('Network error during install');
    }
  };
  
  // Uninstall confirmation
  const uninstallApp = (app: SimulatorApp) => {
    confirm({
      title: 'Uninstall App',
      content: `Are you sure you want to uninstall ${app.appName}? This cannot be undone.`,
      okText: 'Uninstall',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          await fetch(`/api/simulator/install/${app.appId}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
          });
          message.success('App uninstalled');
          fetchProfile();
        } catch (error) {
          message.error('Failed to uninstall app');
        }
      }
    });
  };
  
  const deviceOptions = [
    { label: 'Pixel 6 (Android 14)', value: 'PIXEL_6' },
    { label: 'Pixel 7 (Android 14)', value: 'PIXEL_7' },
    { label: 'iPhone 15 (iOS 17)', value: 'IPHONE_15' },
    { label: 'iPhone 14 (iOS 17)', value: 'IPHONE_14' },
  ];
  
  if (loading) {
    return <Spin size="large" tip="Loading Simulator..." />;
  }
  
  if (!profile) {
    return <Empty description="Simulator profile not found" />;
  }
  
  const quotaUsed = profile.activeInstalls;
  const quotaTotal = profile.installQuota;
  const quotaPercent = (quotaUsed / quotaTotal) * 100;
  
  return (
    <div className="simulator-panel p-6">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-4">My Simulator</h2>
        
        {/* Quota Banner */}
        <Card className="mb-4">
          <Row gutter={16} align="middle">
            <Col flex="auto">
              <Statistic
                title="Install Quota"
                value={quotaUsed}
                suffix={`/ ${quotaTotal} apps`}
                valueStyle={{ color: quotaUsed >= quotaTotal ? '#cf1322' : '#3f8600' }}
              />
            </Col>
            <Col>
              <Progress 
                percent={Math.round(quotaPercent)} 
                status={quotaUsed >= quotaTotal ? 'exception' : 'success'}
                showInfo={false}
              />
            </Col>
            <Col>
              <Select 
                value={selectedDevice}
                onChange={setSelectedDevice}
                style={{ width: 180 }}
              >
                {deviceOptions.map(opt => (
                  <Option key={opt.value} value={opt.value}>
                    {opt.label}
                  </Option>
                ))}
              </Select>
            </Col>
            <Col>
              <Button 
                type="primary" 
                icon={<PlusOutlined />}
                onClick={() => setShowAddApp(true)}
                disabled={quotaUsed >= quotaTotal}
              >
                Add App
              </Button>
            </Col>
          </Row>
        </Card>
      </div>
      
      {/* Installed Apps Grid */}
      {profile.installedApps && profile.installedApps.length > 0 ? (
        <div className="apps-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {profile.installedApps.map(app => (
            <Card 
              key={app.appId} 
              className="app-card hover:shadow-lg transition-shadow"
              actions={[
                <Tooltip title="Launch Simulator">
                  <PlayCircleOutlined 
                    onClick={() => launchApp(app)}
                    style={{ fontSize: '16px', color: '#1890ff' }}
                  />
                </Tooltip>,
                <Tooltip title="Uninstall">
                  <DeleteOutlined 
                    onClick={() => uninstallApp(app)}
                    style={{ fontSize: '16px', color: '#ff4d4f' }}
                  />
                </Tooltip>
              ]}
            >
              <Card.Meta
                avatar={<CloudUploadOutlined style={{ fontSize: '32px', color: '#52c41a' }} />}
                title={app.appName}
                description={
                  <div>
                    <div>v{app.version}</div>
                    <div className="text-xs text-gray-500">
                      Installed: {new Date(app.installedAt).toLocaleDateString()}
                    </div>
                    <div className="text-xs text-gray-500">
                      Launched {app.launchCount} times
                    </div>
                    <Tag color={
                      app.status === 'INSTALLED' ? 'green' : 
                      app.status === 'RUNNING' ? 'blue' : 'red'
                    }>
                      {app.status}
                    </Tag>
                    {app.deployedUrl && (
                      <div className="mt-2">
                        <Tag color="purple" 
                          className="cursor-pointer"
                          onClick={() => window.open(app.deployedUrl, '_blank')}
                        >
                          Preview: {new URL(app.deployedUrl).hostname}
                        </Tag>
                      </div>
                    )}
                  </div>
                }
              />
            </Card>
          ))}
        </div>
      ) : (
        <Empty 
          description="No apps installed"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        >
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={() => setShowAddApp(true)}
          >
            Install Your First App
          </Button>
        </Empty>
      )}
      
      {/* Add App Modal */}
      <Modal
        title="Install App to Simulator"
        open={showAddApp}
        onCancel={() => setShowAddApp(false)}
        footer={null}
      >
        <AppSelector
          onSelect={installApp}
          currentCount={quotaUsed}
          maxQuota={quotaTotal}
        />
      </Modal>
    </div>
  );
};
```

### 3.17 Configuration & Environment Variables

**application.yml / application.properties:**
```properties
# Simulator quota settings
simulator.max.installs.per.user=${SIMULATOR_MAX_INSTALLS:5}
simulator.session.timeout.minutes=${SIMULATOR_SESSION_TIMEOUT:30}
simulator.deployment.timeout.seconds=${SIMULATOR_DEPLOY_TIMEOUT:120}
simulator.auto.cleanup.enabled=${SIMULATOR_AUTO_CLEANUP:true}
simulator.app.expiry.days=${SIMULATOR_APP_EXPIRY_DAYS:7}

# Preview URL format
simulator.preview.url.format=${SIMULATOR_URL_FORMAT:https://{appId}-simulator.run.app}

# Cloud Run settings
simulator.cloudrun.region=${SIMULATOR_REGION:us-central1}
simulator.cloudrun.memory=${SIMULATOR_MEMORY:2Gi}
simulator.cloudrun.cpu=${SIMULATOR_CPU:1}
simulator.cloudrun.service.account=${SIMULATOR_SA:simulator-sa}

# WebSocket
spring.websocket.enabled=true
spring.websocket.max-session-idle-time=1800000  # 30min

# Prometheus metrics
management.endpoints.web.exposure.include=health,metrics,prometheus
management.metrics.export.prometheus.enabled=true
```

**.env.example additions:**
```bash
# Simulator Controller
SIMULATOR_MAX_INSTALLS=5
SIMULATOR_SESSION_TIMEOUT=30
SIMULATOR_DEPLOY_TIMEOUT=120
SIMULATOR_AUTO_CLEANUP=true
SIMULATOR_APP_EXPIRY_DAYS=7
SIMULATOR_REGION=us-central1
SIMULATOR_MEMORY=2Gi
SIMULATOR_CPU=1
SIMULATOR_URL_FORMAT=https://{appId}-simulator.run.app
```

**SimulatorConfig.java (Spring Boot Config):**
```java
@Configuration
@ConfigurationProperties(prefix = "simulator")
@Data
public class SimulatorConfig {
    private int maxInstallsPerUser = 5;
    private int sessionTimeoutMinutes = 30;
    private int deployTimeoutSeconds = 120;
    private boolean autoCleanupEnabled = true;
    private int appExpiryDays = 7;
    private String previewUrlFormat;
    private CloudRun cloudrun = new CloudRun();
    
    @Data
    public static class CloudRun {
        private String region = "us-central1";
        private String memory = "2Gi";
        private String cpu = "1";
        private String serviceAccount;
    }
}
```

### 3.18 Testing Strategy (JUnit 5 + Spring Boot Test)

```java
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class SimulatorControllerIntegrationTest {
    
    @Autowired
    private MockMvc mockMvc;
    
    @Autowired
    private SimulatorProfileRepository profileRepository;
    
    @Test
    @WithMockUser(roles = "USER")
    void testInstallApp_Success() throws Exception {
        String userId = "test-user-123";
        String appId = "test-app-456";
        
        mockMvc.perform(post("/api/simulator/install")
                .header("Authorization", "Bearer " + generateTestToken(userId))
                .content("{\"appId\":\"" + appId + "\",\"deviceProfile\":\"PIXEL_6\"}")
                .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.success").value(true))
            .andExpect(jsonPath("$.quota.used").value(1))
            .andExpect(jsonPath("$.app.deployedUrl").exists());
    }
    
    @Test
    @WithMockUser(roles = "USER")
    void testInstallApp_QuotaExceeded() throws Exception {
        String userId = "quota-user";
        
        // Fill quota first (assume quota=5)
        for (int i = 0; i < 5; i++) {
            mockMvc.perform(post("/api/simulator/install")
                .header("Authorization", "Bearer " + generateTestToken(userId))
                .content("{\"appId\":\"app-\" + i,\"deviceProfile\":\"PIXEL_6\"}")
                .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isCreated());
        }
        
        // 6th install should fail
        mockMvc.perform(post("/api/simulator/install")
            .header("Authorization", "Bearer " + generateTestToken(userId))
            .content("{\"appId\":\"app-overflow\",\"deviceProfile\":\"PIXEL_6\"}")
            .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.error").value("QUOTA_EXCEEDED"));
    }
    
    @Test
    @WithMockUser(roles = "USER")
    void testInstallApp_Duplicate() throws Exception {
        String userId = "dup-user";
        String appId = "duplicate-app";
        
        // First install
        mockMvc.perform(post("/api/simulator/install")
            .header("Authorization", "Bearer " + generateTestToken(userId))
            .content("{\"appId\":\"" + appId + "\",\"deviceProfile\":\"PIXEL_6\"}")
            .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isCreated());
        
        // Second install of same app should fail
        mockMvc.perform(post("/api/simulator/install")
            .header("Authorization", "Bearer " + generateTestToken(userId))
            .content("{\"appId\":\"" + appId + "\",\"deviceProfile\":\"PIXEL_6\"}")
            .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.error").value("APP_ALREADY_INSTALLED"));
    }
    
    @Test
    @WithMockUser(roles = "ADMIN")
    void testAdminForceQuota() throws Exception {
        String adminToken = generateAdminToken();
        String targetUserId = "target-user";
        
        mockMvc.perform(post("/api/simulator/admin/force-quota/{userId}", targetUserId)
            .header("Authorization", "Bearer " + adminToken)
            .param("newQuota", "10"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.newQuota").value(10));
    }
}

/**
 * Concurrency Testing - Verify no race conditions on quota counters
 */
public class SimulatorConcurrencyTest {
    
    @Autowired
    private SimulatorService simulatorService;
    
    @Autowired
    private SimulatorProfileRepository profileRepository;
    
    @Test
    public void testConcurrentInstall_SameUser_NoRaceCondition() throws Exception {
        String userId = "concurrent-user";
        String deviceType = "PIXEL_6";
        int quota = 5;
        
        // Setup: create profile with quota 5
        UserSimulatorProfile profile = new UserSimulatorProfile();
        profile.setUserId(userId);
        profile.setInstallQuota(quota);
        profileRepository.save(profile);
        
        int threadCount = 20;
        CountDownLatch latch = new CountDownLatch(threadCount);
        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        AtomicInteger successCount = new AtomicInteger();
        AtomicInteger failureCount = new AtomicInteger();
        
        for (int i = 0; i < threadCount; i++) {
            final String appId = "concurrent-app-" + i;
            executor.submit(() -> {
                try {
                    simulatorService.installApp(userId, appId, deviceType);
                    successCount.incrementAndGet();
                } catch (SimulatorQuotaExceededException e) {
                    failureCount.incrementAndGet();
                } catch (Exception e) {
                    failureCount.incrementAndGet();
                } finally {
                    latch.countDown();
                }
            });
        }
        
        latch.await(30, TimeUnit.SECONDS);
        executor.shutdown();
        
        // Verify: max 5 successful, rest failed with quota exceeded
        assertEquals(quota, successCount.get());
        assertEquals(threadCount - quota, failureCount.get());
        
        // Verify final state
        UserSimulatorProfile finalProfile = profileRepository.findByUserId(userId).orElseThrow();
        assertEquals(quota, finalProfile.getActiveInstalls());
        assertEquals(quota, finalProfile.getInstalledApps().size());
    }
}

/**
 * TTL Cleanup Test
 */
@SpringBootTest
class SimulatorCleanupTest {
    
    @Autowired
    private SimulatorDeploymentService cleanupService;
    
    @Test
    public void testCleanupRemovesExpiredApps() {
        // Given: profile with app 8 days old
        UserSimulatorProfile oldProfile = new UserSimulatorProfile();
        SimulatorApp oldApp = new SimulatorApp();
        oldApp.setInstalledAt(LocalDateTime.now().minusDays(8));
        oldProfile.setInstalledApps(List.of(oldApp));
        profileRepository.save(oldProfile);
        
        // When: run cleanup
        cleanupService.cleanupExpiredApps();
        
        // Then: old app removed
        UserSimulatorProfile updated = profileRepository.findByUserId(oldProfile.getUserId()).get();
        assertTrue(updated.getInstalledApps().isEmpty());
        assertEquals(0, updated.getActiveInstalls());
    }
}
```

**Mocking WebSocket Tests:**
```java
@SpringBootTest
@AutoConfigureWebSocket
class SimulatorWebSocketTest {
    
    @Autowired
    private SimulatorWebSocketHandler handler;
    
    @Test
    public void testHeartbeatKeepsSessionAlive() throws Exception {
        // Simulate WebSocket connection + heartbeat
        // Verify session not marked stale
    }
}
```

---

## Phase 6: Polish & Optimization (Weeks 25-32)

### 3.19 Multi-Device Support
- Store separate device profiles per user
- Save device configurations (screen size, DPI, OS version)
- Side-by-side device comparison view in UI
- Transfer apps between devices

### 3.20 App Version Management
- Keep history of deployed app versions
- Roll back to previous version
- A/B testing between versions

### 3.21 Automated Screenshot Capture
- Capture screenshot on install
- Store in Cloud Storage
- Display in UI app grid

### 3.22 Performance Benchmarking
- Track app load time
- Memory usage monitoring
- Error rate per app version
- Performance regression alerts

### 3.23 Shareable Simulator Link
- Temporary public access tokens
- Link expiration (24h default)
- View-only mode option
- Embedded iframe support

### 3.24 Cost Management & Alerts
- Cost per simulator session tracking
- Budget alerts (daily/weekly thresholds)
- Automatic throttling when budget exceeded
- Cost reporting dashboard

### 3.25 Enhanced Admin Analytics
- Charts: installs by day, active sessions, quota utilization
- User leaderboard (top users by install count)
- App popularity metrics
- Device type distribution
- Exportable CSV reports

---

# 4. Testing Strategy

## 4.1 Test Coverage Requirements
```
Minimum 80% coverage for:
- Core orchestrator
- API key manager
- Intent analyzer
- Database operations
- GitHub integration
- Simulator service (NEW)
- Simulator deployment
- WebSocket handler
```

## 4.2 CI/CD Pipeline (.github/workflows/ci.yml)
```yaml
name: SupremeAI CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests
        run: pytest --cov=src --cov-report=xml

      - name: Lint
        run: flake8 src/

      - name: Type check
        run: mypy src/

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

# 5. Deployment Plan

## 5.1 Local Development
```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your keys

# Run
python src/main.py
```

## 5.2 Production Deployment
```bash
# Docker
docker build -t supremeai .
docker run -p 8000:8000 --env-file .env supremeai

# Or cloud (Heroku, Railway, etc.)
# Add Procfile
web: python src/main.py
```

---

# 6. Immediate Action Items

## This Week:
1. [ ] Restructure project folders
2. [ ] Add database layer (SQLite)
3. [ ] Create .env configuration
4. [ ] Implement AgentPool class
5. [ ] Add comprehensive .gitignore

## Next Week:
6. [ ] Implement APIKeyManager
7. [ ] Add IntentAnalyzer
8. [ ] Create GitHub integration module
9. [ ] Add database migrations
10. [ ] Write unit tests for core modules

## Following Weeks:
11. [ ] Implement learning system
12. [ ] Add voice processing
13. [ ] Create admin dashboard
14. [ ] Add vision capabilities
15. [ ] Multi-platform support
16. [ ] **Begin Simulator Controller implementation (Phase 5)**

---

# 7. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| API key exposure | Hash storage, .env file, never commit keys |
| Rate limiting | Rotation system, fallback to system AI |
| Data loss | Regular backups, soft delete, grace period |
| Security breach | Input validation, parameterized queries, HTTPS |
| Scaling issues | Modular design, database indexing, caching |
| Simulator cost explosion | Auto-cleanup after 7 days, quota limits, budget alerts |
| Concurrent install race conditions | Firestore transactions for atomic updates |
| Simulator session leaks | Heartbeat + auto-timeout, cleanup daemon |

---

**Document Status:** Action Plan Ready
**Next Step:** Start Phase 1 implementation
**Estimated Timeline:** 20 weeks for full implementation (16 weeks + 4 weeks simulator)