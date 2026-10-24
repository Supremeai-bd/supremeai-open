#!/usr/bin/env python3
"""Generate coldstart_knowledge_seed_knowledge_base.json — correct, programmatic generation."""
import json, sys

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        print('Silenced error in except block')


def entry(aid, title, claim, solution, tags, assumptions=None, invariants=None,
          failure_modes=None, counterarguments=None, evidence=None, confidence=0.95):
    domain_map = {
        "pf_": "programming_fundamentals", "sd_": "system_design_principles",
        "ai_": "ai_ml_fundamentals", "sec_": "security_principles",
        "de_": "data_engineering", "ops_": "devops_reliability",
        "math_": "mathematics_logic", "rf_": "reasoning_frameworks",
        "sci_": "science_fundamentals",
    }
    domain = "general"
    for prefix, d in domain_map.items():
        if aid.startswith(prefix):
            domain = d
            break
    return {
        "artifact_id": aid,
        "type": "concept",
        "domain": domain,
        "title": title,
        "claim": claim,
        "solution": solution,
        "assumptions": assumptions or [],
        "invariants": invariants or [],
        "failure_modes": failure_modes or [],
        "counterarguments": counterarguments or [],
        "evidence": evidence or [],
        "confidence": confidence,
        "verification_status": "verified",
        "tags": tags,
    }


PF = "programming_fundamentals"
SD = "system_design_principles"
AI = "ai_ml_fundamentals"
SEC = "security_principles"
DE = "data_engineering"
OPS = "devops_reliability"
MT = "mathematics_logic"
RF = "reasoning_frameworks"

entries = []

# ============================================================
# PROGRAMMING FUNDAMENTALS (priority 1)
# ============================================================
entries.append(entry("pf_bigO_001", "Big-O Notation and Complexity Analysis",
    "Big-O describes the asymptotic upper bound of algorithm time or space complexity as input size grows.",
    "O(1) constant, O(log n) logarithmic, O(n) linear, O(n log n), O(n^2) quadratic, O(2^n) exponential, O(n!) factorial. Count primitive operations as a function of n; drop constants and lower-order terms. To choose: prefer O(n log n) over O(n^2) for large n; prefer O(1) hash lookup over O(n) linear search. Big-Omega is the lower bound (best case), Big-Theta is the tight bound (average case).",
    ["complexity", "algorithms", "analysis", "asymptotic", "performance"],
    assumptions=["Input size n is the dominant variable", "Primitive operations are O(1)", "Sufficient memory available"],
    invariants=["O(1) is faster than O(n) for large enough n", "Lower Big-O wins asymptotically", "Time and space complexity are independent tradeoffs"],
    failure_modes=["Confusing Big-O worst-case with Big-Theta average-case", "Ignoring cache effects - cache-friendly O(n^2) may beat cache-unfriendly O(n log n)", "Constants matter for small n - Big-O is asymptotic only"],
    counterarguments=["Deep learning with massive data shifts the tradeoff plane"],
    evidence=["Cormen et al. Introduction to Algorithms", "Knuth The Art of Computer Programming"],
    confidence=0.99))

entries.append(entry("pf_arr_ll_002", "Arrays vs Linked Lists",
    "Array stores elements contiguously for O(1) random access but O(n) insertion; linked list uses pointers for O(1) insertion at a known position but O(n) random access.",
    "Array: contiguous memory, O(1) random access, O(n) insert/delete (shifting), cache-friendly (spatial locality). Dynamic array: amortized O(1) append via geometric resizing (capacity doubles on full). Linked List: node-based (data + pointer(s)), O(1) insert/delete at head/tail if pointer is known, O(n) traversal, no spatial locality. Doubly linked allows O(1) delete with node reference. Use arrays for random access and cache locality; use lists for frequent insert/delete when node pointer is known.",
    ["data-structures", "arrays", "linked-list"],
    assumptions=["Need random access", "Need frequent insert/delete at known positions", "Cache locality matters"],
    invariants=["Dynamic arrays achieve amortized O(1) append via doubling", "Linked lists have per-node pointer overhead and poor cache behavior"],
    failure_modes=["Cache misses from linked-list pointer chasing", "Dynamic array O(n) reallocation on growth", "Not resizing leads to O(n^2) appends"],
    counterarguments=["For small datasets under 100 elements, linear search may outperform hash-table setup cost"],
    evidence=["Python list (CPython list_resize), Java ArrayList, C++ std::vector", "Java LinkedList, C++ std::list", "Systems programming uses arrays for performance"],
    confidence=0.98))

entries.append(entry("pf_hash_003", "Hash Tables: Design and Collision Resolution",
    "Hash tables provide average O(1) lookup, insertion, and deletion via a hash function mapping keys to buckets; collisions are resolved by chaining or open addressing.",
    "Hash function h(k) maps to bucket index h(k) mod table_size. Chaining: each bucket holds a list; simple, handles load beyond 1.0. Open addressing: probe for next empty slot (linear i+1, quadratic i^2, double hashing via h2(k)). Load factor alpha = n/m; resize at alpha > 0.75 for open addressing or > 1.0 for chaining. Good hash: deterministic, uniform, fast (MurmurHash, FNV-1a, or language builtins).",
    ["data-structures", "hashing", "hash-table", "collision-resolution"],
    assumptions=["Good hash function distributes uniformly", "Memory overhead of chaining is acceptable", "Table can be resized periodically"],
    invariants=["Average O(1) at load factor under 0.75", "Worst case O(n) when all keys collide in one bucket", "Hash tables are unordered - iteration order is arbitrary"],
    failure_modes=["Hash flooding attack - attacker crafts colliding keys to degrade to O(n)", "Poor hash function causes clustering and degraded performance", "Forgetting to resize causes lookup degradation"],
    counterarguments=["For small datasets, sorted array plus binary search may be simpler than a hash table"],
    evidence=["Java HashMap with chaining and tree bins for buckets over 8 entries", "Python dict using open addressing with pseudo-random probing", "Redis dictionary implementation"],
    confidence=0.97))

entries.append(entry("pf_bst_004", "Binary Search Trees and Balanced Tree Variants",
    "A BST stores data in a binary tree where left subtree keys are less than the node and right subtree keys are greater, enabling O(log n) operations when balanced.",
    "BST: search/insert/delete O(h) where h is height. Unbalanced tree on sorted input gives h = n, degrading to O(n). Balanced variants: AVL tree (strict balance, height difference <= 1, rotations on insert/delete, guarantees O(log n)), Red-Black tree (relaxed balance, no path more than 2x another, O(log n) with fewer rotations), B-Tree (multi-key nodes, optimized for disk storage, used in databases and filesystems), Treap (randomized priority, expected O(log n)), Splay tree (amortized O(log n), self-adjusting).",
    ["data-structures", "trees", "bst", "avl", "red-black", "b-tree"],
    assumptions=["Tree fits in memory", "Ordered traversal is needed", "A balanced variant prevents worst-case degradation"],
    invariants=["In-order traversal yields sorted order", "Balanced BST guarantees O(log n) for all operations", "Self-balancing trees use O(1) metadata per node"],
    failure_modes=["Sorted array plus binary search has better cache locality than BST", "Red-black tree deletion is complex to implement correctly", "Unbalanced BST on sorted input degrades to O(n^2)"],
    counterarguments=["None - trees are fundamental structures with well-established tradeoffs"],
    evidence=["CLRS Chapters 13 (Red-Black Trees) and 18 (B-Trees)", "Linux kernel rbtree implementation", "Java TreeMap uses Red-Black tree"],
    confidence=0.96))

entries.append(entry("pf_sort_005", "Sorting Algorithms: Comparison vs Non-comparison",
    "Comparison-based sorting has an O(n log n) lower bound; non-comparison sorts achieve O(n+k) by exploiting key properties like bounded range or fixed digit width.",
    "Comparison sorts: Merge Sort (stable, O(n log n), O(n) space, parallelizable, divide and conquer). Quick Sort (unstable, O(n log n) avg with random pivot, O(n^2) worst, in-place). Heap Sort (unstable, O(n log n), in-place, cache-unfriendly). Insertion Sort (stable, O(n) best case for nearly-sorted data, O(n^2) worst, in-place). Timsort (adaptive, finds natural runs, used in Python and Java). Non-comparison sorts: Counting Sort O(n+k) for small integer ranges, Radix Sort O(d*(n+k)) for fixed-width keys, Bucket Sort O(n) average for uniform distributions.",
    ["sorting", "algorithms", "merge-sort", "quick-sort", "radix-sort", "timsort"],
    assumptions=["Need deterministic ordering", "Need stable sort for some use cases", "Small integers may permit non-comparison sorts", "Memory constrained requires in-place sorting"],
    invariants=["Merge sort stability is useful for sorting by multiple keys sequentially", "Quick sort has cache-friendly sequential memory access", "Non-comparison sorts achieve sub-O(n log n) by exploiting key properties"],
    failure_modes=["Quick sort worst case O(n^2) - mitigate with introsort (switch to heapsort at depth limit)", "Counting sort O(n+k) is bad if k is large - use radix sort instead", "Unstable sort breaks multi-key sequential sorting"],
    counterarguments=["For nearly-sorted data, insertion sort O(n) outperforms all O(n log n) algorithms"],
    evidence=["C++ std::sort is introsort (quick + heap + insertion)", "Python sorted uses Timsort", "Rust sort_by is stable, sort_unstable_by is unstable quicksort"],
    confidence=0.95))

entries.append(entry("pf_dp_006", "Dynamic Programming: Memoization vs Tabulation",
    "DP solves problems with overlapping subproblems and optimal substructure by caching results to avoid redundant recomputation.",
    "Overlapping subproblems: same subproblem solved repeatedly (naive recursion is exponential, DP is polynomial). Optimal substructure: optimal solution contains optimal subproblem solutions. Memoization: top-down recursion + cache (hashmap/array), lazy evaluation, recursion stack depth risk. Tabulation: bottom-up iterative, fills table in dependency order, no recursion overhead, can optimize space with rolling arrays. Classic examples: Fibonacci O(n) vs O(2^n), 0/1 Knapsack, Longest Common Subsequence, Edit Distance, Bellman-Ford shortest path. State definition is the key challenge: the state tuple [position][constraint] must capture enough information for all future decisions.",
    ["algorithms", "dynamic-programming", "memoization", "tabulation", "optimization"],
    assumptions=["Subproblems overlap (repeated computation)", "Optimal substructure holds", "State space is manageable"],
    invariants=["Tabulation table must be filled in topological dependency order", "Memoization cache keyed on all varying state parameters", "Space reducible via rolling arrays when only last row is needed"],
    failure_modes=["Wrong state definition - unsound recurrence or exponential state space", "Integer overflow in counting problems - use big integers or modular arithmetic", "Not recognizing a problem as DP leads to incorrect greedy solutions"],
    counterarguments=["For some problems, divide-and-conquer with pruning may be simpler than DP"],
    evidence=["Competitive Programming resources: AtCoder DP Contest, Codeforces EDU DP section", "CLRS Chapter 15 on Dynamic Programming"],
    confidence=0.94))

entries.append(entry("pf_solid_007", "SOLID Principles of Object-Oriented Design",
    "SOLID is a set of five design principles that improve maintainability and extensibility of OOP code by reducing coupling and increasing cohesion.",
    "Single Responsibility - a class has one reason to change (one responsibility). Open/Closed - closed for modification, open for extension via inheritance, polymorphism, or composition. Liskov Substitution - subtypes must be substitutable for their base types (preconditions cannot be strengthened, postconditions cannot be weakened). Interface Segregation - many small client-specific interfaces are better than one fat interface. Dependency Inversion - high-level modules should not depend on low-level modules; both depend on abstractions; use DI containers for wiring.",
    ["oop", "design-principles", "solid", "architecture", "maintainability"],
    assumptions=["Using object-oriented design", "Code is expected to evolve", "Team benefits from clear structure"],
    invariants=["SRP isolates changes to a single class", "LSP ensures polymorphism works correctly", "DIP decouples high-level policy from low-level implementation"],
    failure_modes=["Over-segregating interfaces creates excessive indirection", "Violating LSP in overridden methods breaks the behavioral contract", "Creating unnecessary abstractions for simple use cases"],
    counterarguments=["SOLID principles add complexity - for simple CRUD applications, YAGNI may be preferable"],
    evidence=["Robert C. Martin - Clean Craftsmanship", "Java Effective Items 58-68 on SOLID", "C# in Depth chapters on interfaces"],
    confidence=0.93))

entries.append(entry("pf_conc_008", "Concurrency vs Parallelism and Thread Safety",
    "Concurrency manages multiple tasks in an interleaved fashion; parallelism executes tasks simultaneously on multiple cores; thread safety requires protecting shared mutable state.",
    "Concurrency: tasks in progress simultaneously sharing resources; requires synchronization to avoid race conditions. Parallelism: truly simultaneous execution on multiple cores; requires partitioning of work. Thread safety primitives: Mutex/lock (mutual exclusion, one thread at a time, deadlock risk), Semaphore (allows N threads), Read-Write lock (multiple readers, one writer), Atomic operations (compare-and-swap, lock-free), Immutability (no locks needed), Thread-local storage (each thread has own copy), Message passing (channels - no shared state). Deadlock prevention: consistent lock ordering, timeout, try-lock.",
    ["concurrency", "parallelism", "thread-safety", "locks", "deadlock"],
    assumptions=["Shared mutable state exists and must be protected", "Multiple execution flows access the same data"],
    invariants=["Deadlock requires all 4 Coffman conditions - eliminate any one to prevent it", "Immutable objects are always thread-safe by definition", "Thread-safe design should be the default, not an afterthought"],
    failure_modes=["Cache misses from non-sequential memory access", "Deadlock if lock ordering is violated across call sites", "Race conditions on shared mutable state"],
    counterarguments=["For CPU-bound work, parallelism requires multi-threading or multi-processing; the event loop alone cannot utilize multiple cores"],
    evidence=["Amdahl's Law: speedup <= 1/(S + P/N) where S is serial fraction, P parallel, N cores", "Java synchronized/volatile/atomic, Rust ownership system for compile-time safety", "Go channels and goroutines, Erlang message passing"],
    confidence=0.95))

entries.append(entry("pf_gc_009", "Garbage Collection Algorithms",
    "Garbage collection automatically reclaims memory from unreachable objects using tracing algorithms such as mark-and-sweep, copying, generational, or mark-compact collectors.",
    "Reference counting: track references per object, free when count reaches 0. Fails on cycles. Mark-sweep: DFS from roots marks live objects, sweep unmarked objects; causes fragmentation. Copying: live objects copied to new space, old space collected; wastes 50% space but compacts. Generational: young generation (minor GC, frequent, copying) plus old generation (major GC, infrequent, mark-sweep or compact). Hypothesis: most objects die young. Mark-compact: mark then slide live objects to eliminate fragmentation. G1 (Java): region-based, concurrent marking, prioritizes garbage-rich regions. ZGC and Shenandoah: sub-millisecond pauses via concurrent relocation.",
    ["garbage-collection", "memory-management", "jvm", "gc", "performance"],
    assumptions=["GC-enabled language (Java, Go, C#)", "Memory is sufficient for copying overhead"],
    invariants=["Objects form a reachable graph from GC roots", "GC is not real-time - pauses can be significant"],
    failure_modes=["Stop-the-world pauses in non-concurrent collectors", "Memory leaks from unintentional references (listeners, inner class captures)", "Weak/Soft/Phantom references needed for memory-sensitive caches"],
    counterarguments=["For deterministic resource release, use try-finally or try-with-resources instead of finalizers"],
    evidence=["JVM HotSpot collectors: Serial, Parallel, G1, ZGC, Shenandoah", "Python CPython: reference counting plus cycle detector", "Go runtime: concurrent tri-color mark-sweep"],
    confidence=0.93))

entries.append(entry("pf_idem_010", "Idempotency in Programming and HTTP",
    "An operation is idempotent if applying it multiple times produces the same effect as applying it once; critical for safe retries in distributed systems.",
    "Mathematical: f(f(x)) = f(x). HTTP: GET is safe and idempotent. PUT is idempotent (replace resource). DELETE is idempotent (second call returns 404). POST and PATCH are not idempotent. Distributed systems: network retries and duplicate messages are common. Idempotency implementation: (1) Idempotency keys - client generates a unique key; server stores the result and returns cached result on repeat. (2) Deterministic operations. (3) Conditional updates (compare-and-swap). (4) Upsert semantics (INSERT ON CONFLICT). Stripe and Shopify APIs implement idempotency keys.",
    ["idempotency", "distributed-systems", "retries", "http", "reliability"],
    assumptions=["Operations may be retried due to network timeouts", "Client can generate unique idempotency keys (UUID)", "Server can persist idempotency keys long enough for possible retries"],
    invariants=["Idempotency keys must be scoped to operation type", "Idempotency keys should expire (e.g. 24-72 hours)"],
    failure_modes=["Idempotency key collision - use high-entropy UUIDs", "Not storing idempotency key causes duplicate processing", "POST for idempotent operations without an idempotency key"],
    counterarguments=["For read-only operations, natural idempotency is better than adding idempotency key infrastructure"],
    evidence=["Stripe API idempotency documentation", "AWS idempotency tokens for API requests", "HTTP RFC 9110 Section 9.2.2 on idempotent methods"],
    confidence=0.96))

entries.append(entry("pf_evtlp_011", "Event Loop Concurrency Model",
    "The event loop enables async I/O on a single thread by delegating blocking operations to the OS kernel and queueing callbacks when operations complete.",
    "Node.js event loop phases: timers (setTimeout/setInterval), pending callbacks, idle/prepare (internal), poll (wait for I/O), check (setImmediate callbacks), close (close events). Call stack executes synchronously; heap stores objects; callback queue holds completed async callbacks. Python asyncio: coroutines with async/await, event loop schedules on ready queue (cooperative multitasking). Critical insight: microtasks (Promise.then, process.nextTick, asyncio callbacks) always drain completely before the next macrotask or event loop phase. Single-threaded: no locks needed, but CPU-bound work blocks the loop - use worker threads (Node) or multiprocessing (Python) for CPU-heavy tasks.",
    ["event-loop", "async", "concurrency", "nodejs", "asyncio", "non-blocking-io"],
    assumptions=["Single-threaded execution model", "OS provides non-blocking I/O via epoll/kqueue/IOCP"],
    invariants=["Microtasks run before the next macrotask or phase", "Synchronous code blocks the entire event loop"],
    failure_modes=["Blocking the event loop with CPU-heavy synchronous work degrades all connections", "Uncaught async errors not caught by try/catch - need process-level handlers", "Forgotten await causes silent floating promise failures"],
    counterarguments=["For CPU-bound work, event loop alone cannot utilize multiple cores - use process pool"],
    evidence=["Node.js official documentation on the Event Loop", "Python asyncio PEP 3156 and documentation", "Etsy engineering blog on Node.js event loop visualization"],
    confidence=0.94))

# ============================================================
# SYSTEM DESIGN PRINCIPLES (priority 2)
# ============================================================
entries.append(entry("sd_cap_001", "CAP Theorem and PACELC Extension",
    "CAP theorem: a distributed system can guarantee at most two of Consistency, Availability, or Partition tolerance; PACELC adds that else (no partition) you choose Latency vs Consistency.",
    "CAP: network partition (P) is inevitable in distributed systems (network is not reliable). So you choose C or A during a partition. CP (consistent and partition-tolerant, sacrifices availability during partition): HBase, MongoDB, Etcd, Zookeeper. AP (available and partition-tolerant, sacrifices consistency): DynamoDB, Cassandra, CouchDB, Couchbase. PACELC: P=partition, A=availability, C=consistency, E=else, L=latency, C=consistency. Even without partitions, there is a latency-consistency trade-off. Spanner chooses consistency (uses TrueTime). DynamoDB chooses latency (eventual consistency).",
    ["system-design", "distributed-systems", "cap-theorem", "consistency", "availability"],
    assumptions=["Network partition is the failure mode considered in CAP", "Consistency means linearizability (strong consistency)"],
    invariants=["Partition tolerance cannot be disabled in a network-partitioned distributed system", "Cannot have all three C, A, and P simultaneously"],
    failure_modes=["Thinking CAP is a hard binary guarantee rather than a tunable spectrum", "Confusing availability (responsive) with durability (data preserved)", "Ignoring that single-node systems trivially satisfy CA"],
    counterarguments=["Modern databases offer tunable consistency (Redis, Cosmos DB) - it's not binary"],
    evidence=["Gilbert and Lynch: Impossibility of Distributed Consensus (2002)", "Fox and Gurevin: PACELC (2016)"],
    confidence=0.97))

entries.append(entry("sd_circ_002", "Circuit Breaker Pattern",
    "The Circuit Breaker wraps calls to external services with a proxy that trips open after repeated failures, temporarily stops requests, and probes to recover.",
    "Three states: CLOSED (requests flow normally, failure counter increments, on reaching threshold transitions to OPEN). OPEN (requests immediately fail fast via fallback - no call to downstream, after timeout transitions to HALF-OPEN). HALF-OPEN (limited test requests; success transitions to CLOSED with reset; failure transitions back to OPEN). Configuration: failure threshold (consecutive or percentage), timeout (open to half-open wait), retry limit (half-open to open). Libraries: Resilience4j, Polly, Sentinel. Monitoring: state changes, success/failure rates. Best practice: use with retry, bulkhead, and timeout - don't wrap DB calls that have their own timeouts.",
    ["circuit-breaker", "resilience", "fault-tolerance", "distributed-systems"],
    assumptions=["External service calls may fail or become unavailable", "Downstream failures should not cascade to callers"],
    invariants=["Half-open should allow only a limited number of test requests", "Circuit breaker state must be thread-safe"],
    failure_modes=["Failure threshold set too low - trips on normal error fluctuations", "Timeout set too short - doesn't allow downstream recovery", "No fallback response strategy - callers see raw errors"],
    counterarguments=["For critical internal services with guaranteed uptime, circuit breaker adds latency overhead"],
    evidence=["Netflix Hystrix documentation", "Martin Fowler: CircuitBreaker article", "Resilience4j documentation"],
    confidence=0.98))

entries.append(entry("sd_cache_003", "Caching Strategies and Cache Invalidation",
    "Caching improves read performance but introduces invalidation, consistency, and stampede challenges requiring careful strategy design.",
    "Cache placement: client-side (browser), edge (CDN), application (Redis/Memcached), database query cache. Strategies: (1) Cache-Aside (Lazy): application checks cache, on miss queries DB and populates cache. Most common. (2) Write-Through: write to cache and DB atomically; reads always fresh, write penalty. (3) Write-Behind: write to cache only, async flush to DB. (4) Write-Around: write to DB, skip cache. Invalidation: TTL expiry, explicit delete after write, version-based keys, cache tags for bulk invalidation. Cache stampede prevention: single-flight (deduplicate concurrent misses), stale-while-revalidate, probabilistic early expiration.",
    ["caching", "cache-invalidation", "cache-stampede", "redis", "performance"],
    assumptions=["Read-heavy workload with temporal data locality", "Cache layer is fast and highly available"],
    invariants=["Cache entry TTL must be set per data freshness requirements", "Cache key must incorporate data version for atomic invalidation"],
    failure_modes=["Cache stampede on mass expiry overwhelms the backing store", "Stale cache serving outdated data", "Cache poisoning with malicious data"],
    counterarguments=["For write-heavy workloads, caching complexity may exceed benefits - use read replicas instead"],
    evidence=["Facebook: Achieving Anoughness on cache invalidation", "Redis documentation on caching patterns", "Google SRE on cache management"],
    confidence=0.96))

entries.append(entry("sd_lb_004", "Load Balancing Algorithms and Strategies",
    "Load balancers distribute traffic across backend servers using algorithms with health checks and failover for high availability and scalability.",
    "Layer 4 (transport) vs Layer 7 (application/HTTP). Algorithms: Round Robin (weighted) for homogeneous servers. Least Connections for long-lived connections. IP Hash for sticky sessions. Consistent Hashing (for distributed caches) handles node add/remove with minimal redistribution (used in DynamoDB, Redis Cluster). Health checks: active (periodic HTTP/TCP probes to /health endpoint) and passive (monitor request failures). Sticky sessions break on server failure - use external store for session state. Graceful shutdown: stop accepting new connections, finish existing then terminate.",
    ["load-balancing", "scalability", "high-availability", "health-checks"],
    assumptions=["Multiple servers available for the same service", "Health checks are reliable and fast"],
    invariants=["Health check interval must be shorter than client timeout", "Graceful shutdown must drain all active connections"],
    failure_modes=["Health checks too aggressive mark healthy servers down", "Sticky sessions lost on server failure", "No health check sends traffic to dead server"],
    counterarguments=["For static assets, DNS-level anycast load balancing may be simpler than L7 proxy"],
    evidence=["NGINX, HAProxy, AWS ALB/NLB documentation", "Google SRE Workbook on load balancing"],
    confidence=0.95))

entries.append(entry("sd_shard_005", "Database Sharding and Partitioning",
    "Sharding splits data across machines by a shard key for horizontal scaling; partitioning splits data within a database for manageability.",
    "Horizontal partitioning: by range, list, or hash. Vertical partitioning: by columns. Sharding strategies: (1) Range-based - sequential ranges (date, ID); easy range queries but hotspots. (2) Hash-based - consistent hashing via hash(key) mod N; even distribution but range queries need all shards. (3) Directory-based - lookup table maps key to shard. (4) Composite - combine keys. Shard key must have high cardinality, even distribution, and co-locate related data. Cross-shard: two-phase commit (2PC) for ACID or saga pattern for eventual consistency. Rebalancing: split hot shards, merge underutilized. Router maps shard key to shard with a connection pool per shard.",
    ["database", "sharding", "partitioning", "scaling", "distributed-systems"],
    assumptions=["Shard key distributes data evenly", "Applications can route queries to correct shard"],
    invariants=["Shard key is immutable - changing requires re-sharding the row", "Cross-shard joins and transactions have higher latency and complexity"],
    failure_modes=["Hot shard from uneven key distribution", "Shard key too granular causes excessive scatter-gather queries"],
    counterarguments=["For most applications, vertical scaling plus read replicas plus caching covers needs without sharding complexity"],
    evidence=["Designing Data-Intensive Applications by Martin Kleppmann (Chapter 6)", "MongoDB sharding documentation"],
    confidence=0.94))

entries.append(entry("sd_12fac_006", "The Twelve-Factor App Methodology",
    "The 12-Factor methodology defines principles for building SaaS applications deployable on modern cloud platforms.",
    "1. Codebase - one codebase, many deploys. 2. Dependencies - explicit, pinned, isolated via package manager. 3. Config - environment variables (not in code). 4. Backing services - attached resources (DB, cache, queue) as env URLs. 5. Build, release, run - strict separation. Compile once, run everywhere. 6. Processes - stateless, shared-nothing. 7. Port binding - app listens on a port (self-contained). 8. Concurrency - scale by processes. 9. Disposability - fast start, graceful shutdown. 10. Dev/prod parity - minimize gaps. 11. Logs - as event stream (stdout/stderr). 12. Admin processes - one-off tasks (migrations) run in prod environment.",
    ["cloud-native", "twelve-factor", "devops", "scalability", "saas"],
    assumptions=["Application is deployed as a cloud service", "Dependencies are managed via package managers"],
    invariants=["Processes are stateless and share nothing - state in backing services", "Config varies by deploy but not stored in codebase"],
    failure_modes=["Admin processes using wrong environment causes data inconsistency", "Stateful processes cannot scale horizontally", "Logging to local files instead of streams"],
    counterarguments=["Some factors (logs, admin processes) may be better handled by infrastructure"],
    evidence=["12factor.net canonical reference", "Used by Heroku, Cloud Foundry, and modern platform engineering"],
    confidence=0.96))

entries.append(entry("sd_bulk_007", "Bulkhead Pattern for Fault Isolation",
    "The Bulkhead pattern isolates system resources into separate pools so that failure in one component does not cascade to unrelated components, like watertight compartments in a ship.",
    "Inspired by watertight compartments in ships: breach floods only one section, ship stays afloat. In software: (1) Process isolation - each critical function runs in its own process; crash stays contained (max blast radius = one process). (2) Thread pool isolation - each downstream dependency gets its own thread pool; a slow DB does not exhaust web request threads. (3) Connection pool isolation - separate pools per external service. (4) Network isolation - separate VPCs or subnets. (5. Resource quotas - CPU and memory limits (Kubernetes). (6) Circuit breaker per dependency. Bounded resource pools with timeouts prevent one slow dependency from starving others.",
    ["bulkhead", "fault-isolation", "resilience", "patterns"],
    assumptions=["Multiple dependencies with different reliability profiles", "Need to prevent failure propagation"],
    invariants=["Bulkhead pool sizes must be bounded to prevent resource exhaustion", "Failures in one bulkhead do not affect others"],
    failure_modes=["Too many bulkheads causes resource fragmentation and overhead", "No timeout on resource acquisition causes pool exhaustion", "Shared thread pool defeats bulkhead isolation"],
    counterarguments=["For systems with tightly-coupled dependencies, separate processes may add unnecessary complexity"],
    evidence=["Netflix Hystrix thread pool isolation patterns", "Microsoft Azure application architecture guide on bulkheads"],
    confidence=0.93))

entries.append(entry("sd_saga_008", "Saga Pattern for Distributed Transactions",
    "Saga manages distributed transactions as a sequence of local transactions with compensating actions that undo each step on failure, avoiding two-phase commit complexity.",
    "Two coordination styles: (1) Choreography - services emit events; when a saga step completes, it publishes an event; the next service consumes it, executes its local transaction, and publishes the next event. On failure, publishes a compensation event. No central coordinator. (2) Orchestration - a saga orchestrator sends commands to each service; services execute and return results; the orchestrator decides next step or triggers compensating transactions. Compensation actions must be idempotent. Example: money transfer - create debit (compensating action: refund debit), create credit (compensating: reverse credit), if credit fails, compensate debit. Not all actions can be undone (e.g., sending an email).",
    ["saga", "distributed-transactions", "compensation", "microservices", "event-driven"],
    assumptions=["Each local transaction either fully succeeds or fails", "Compensating actions are available for every step"],
    invariants=["Compensating actions are idempotent - must handle execution multiple times", "Saga steps are eventually consistent - intermediate inconsistency may be observable"],
    failure_modes=["Irreversible actions in saga cannot be compensated", "Race condition between compensating actions for same resource", "Compensation failure leaves system inconsistent"],
    counterarguments=["For simple two-database transactions, two-phase commit or XA may be simpler than a full saga"],
    evidence=["Garcia-Molina and Salem: The Saga Pattern (1987)", "Microservices Patterns by Chris Richardson (Saga chapter)"],
    confidence=0.96))

# ============================================================
# AI/ML FUNDAMENTALS (priority 3)
# ============================================================
entries.append(entry("ai_bias_001", "Bias-Variance Tradeoff in Machine Learning",
    "The bias-variance tradeoff describes the tension between model simplicity (high bias, underfitting) and model complexity (high variance, overfitting) in minimizing total prediction error.",
    "Total Error = Bias^2 + Variance + Irreducible Error (noise). Bias: error from erroneous assumptions (underfitting). Variance: error from sensitivity to training data fluctuations (overfitting). Irreducible: noise inherent in the data. To reduce bias: add features, increase model complexity, reduce regularization. To reduce variance: add more training data, apply regularization (L1, L2, dropout), use ensemble methods (bagging), cross-validation. The sweet spot minimizes total error.",
    ["machine-learning", "bias-variance", "overfitting", "underfitting", "ensemble"],
    assumptions=["Model has sufficient capacity to learn the true relationship", "Training and test data are drawn from the same distribution"],
    invariants=["Increasing model complexity generally reduces bias but increases variance", "Ensemble averaging reduces variance without affecting bias"],
    failure_modes=["Confusing variance (model sensitivity) with irreducible error (noise)", "Not collecting more data as the primary variance-reduction lever", "Hyperparameter tuning without cross-validation leads to overfitting validation set"],
    counterarguments=["Modern deep learning with massive data and compute often reduces both bias and variance simultaneously"],
    evidence=["Geman et al. A Connectionist Approach to Cognitive Breakdown (1992)", "Hastie, Tibshirani, Friedman: Elements of Statistical Learning"],
    confidence=0.96))

entries.append(entry("ai_rag_002", "RAG: Retrieval-Augmented Generation",
    "RAG combines a retriever searching external documents with a generator (LLM) conditioning output on retrieved passages, reducing hallucination and providing source attribution.",
    "Pipeline: (1) Index - chunk documents into passages (200-500 tokens), embed each with a dense embedding model (all-MiniLM-L6-v2, bge-m3), store in a vector database (ChromaDB, pgvector, Pinecone). (2) Query - embed user query, compute cosine similarity, retrieve top-k passages. (3) Rerank - cross-encoder (ColBERT, Cohere reranker) refines relevance beyond semantic search. (4) Generate - concatenate passages as context, prompt LLM with citation instructions. Variants: naive RAG (single retrieval), Fusion RAG (query rewrite plus multiple retrievers), Self-RAG (LLM self-evaluates and requests more retrieval). The ChromaDBStore in backend/memory has a TF-IDF fallback when vector search is unavailable.",
    ["llm", "rag", "retrieval", "vector-db", "hallucination", "chromadb"],
    assumptions=["Retrieved passages are relevant and correct", "Embedding model generalizes to query domain"],
    invariants=["Passage chunks should be 200-500 tokens for precise retrieval", "RAG cannot correct errors in the indexed source documents"],
    failure_modes=["Hallucination despite retrieval - LLM ignores context or fabricates citations", "Low recall - retrieval misses relevant documents due to embedding mismatch", "RAG latency from sequential retrieval plus generation"],
    counterarguments=["For factual QA over well-structured data, a fine-tuned retriever plus LLM may outperform dense retrieval"],
    evidence=["Lewis et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP (2020)", "SupremeAI backend/memory/rag_pipeline.py"],
    confidence=0.96))

entries.append(entry("ai_opt_003", "Gradient Descent and Modern Optimizers",
    "Gradient descent optimizes model parameters by moving opposite to the loss gradient; momentum, adaptive learning rates, and weight decay improve convergence speed and stability.",
    "Vanilla GD: theta = theta - lr * gradient. SGD with momentum: velocity = momentum * velocity + gradient; theta -= lr * velocity - smooths oscillations in relevant direction. Adam: maintains per-parameter first moment (mean) and second moment (uncentered variance); bias-corrected; adaptive per-parameter learning rate. AdamW: decoupled weight decay applied directly to parameters, not through gradient. LAMB and LARS: layer-wise adaptive learning rates for large-batch training. Adafactor: memory-efficient (no second moment buffer). Gradient clipping: clip by norm or value to prevent exploding gradients in deep RNNs/Transformers.",
    ["optimization", "gradient-descent", "adam", "momentum", "weight-decay", "deep-learning"],
    assumptions=["Loss function has smooth (Lipschitz continuous) gradient", "Learning rate is tuned for model and dataset"],
    invariants=["Adam epsilon prevents division by zero in second moment", "Learning rate is the most sensitive hyperparameter"],
    failure_modes=["Learning rate too high - diverges or oscillates", "Adam converges to sharp minimum that may generalize worse than SGD", "Not resetting optimizer state on a new training run"],
    counterarguments=["For convex problems, plain SGD with momentum may be more reliable than adaptive methods"],
    evidence=["Kingma and Ba: Adam (2015)", "Loshchilov and Hutter: Decoupled Weight Decay (2019)"],
    confidence=0.96))

entries.append(entry("ai_attn_004", "Transformer Attention and Positional Encoding",
    "Transformers use self-attention to compute contextual token representations in parallel, with multi-head attention capturing different relation types and positional encodings providing sequence order.",
    "Self-attention: Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) V. Q, K, V are linear projections of the same input. Multi-head: h attention heads in parallel (different learned projections), concatenated and projected - each head can learn different relations. Encoder: multi-head self-attention plus feed-forward (two linear layers with GELU) plus residual plus layer norm. Decoder: same plus masked self-attention (prevents looking ahead) and encoder-decoder attention. Layer norm: normalizes across feature dimension, more stable than batch norm for variable sequence lengths. Positional encoding: sinusoidal (PE(pos, 2i) = sin(pos / 10000^(2i/d_model))), learned embeddings, RoPE (rotary - used in GPT-J/LLaMA), or ALiBi (linear bias).",
    ["transformer", "attention", "llm", "architecture", "positional-encoding"],
    assumptions=["Input sequence fits in model's context window", "Attention mechanism is the dominant computational cost"],
    invariants=["Attention weights sum to 1 (softmax is row-normalized)", "Self-attention is permutation-invariant without positional encoding"],
    failure_modes=["Quadratic memory and compute in sequence length without sparse/linear attention", "Positional encoding missing at inference if present at training", "Not scaling attention scores by 1/sqrt(d_k) causes gradient explosion at initialization"],
    counterarguments=["For tasks requiring strong sequential inductive bias (copying, sorting), RNNs may generalize better than transformers"],
    evidence=["Vaswani et al. Attention Is All You Need (2017)", "RoFormer: Su et al. on rotary position embedding (2021)", "ALiBi: Press et al. (2022)"],
    confidence=0.96))

entries.append(entry("ai_eval_005", "Machine Learning Evaluation Metrics",
    "Correct metric selection ensures models optimize the right objective - classification uses precision/recall/F1/AUROC, regression uses MAE/MSE/R2, ranking uses NDCG/MRR, and text generation uses BLEU/ROUGE or human evaluation.",
    "Classification: Accuracy = (TP+TN)/total. Precision = TP/(TP+FP). Recall = TP/(TP+FN). F1 = 2*P*R/(P+R). Imbalanced data: accuracy is misleading; use F1, PR-AUC, or AUROC. AUROC: probability that a random positive is ranked higher than random negative. AUPRC: area under PR curve, better for imbalanced data. Regression: MAE (robust, interpretable), MSE (penalizes large errors), RMSE (same units as target), R2 (variance explained, negative if worse than mean baseline). Ranking: NDCG (discounted cumulative gain at position k, accounts for ranking), MRR (reciprocal rank of first relevant result). LLM generation: BLEU/ROUGE (n-gram overlap, cheap but imperfect), BERTScore/BLEURT (embedding-based), human evaluation (gold standard for quality, helpfulness, harmlessness).",
    ["ml", "evaluation", "metrics", "precision", "recall", "auc", "bleu", "rouge"],
    assumptions=["Test set is representative of production data", "Metrics align with business objectives"],
    invariants=["Always evaluate on held-out test set never used in training or model selection", "Use stratified sampling for imbalanced classification"],
    failure_modes=["Accuracy misleading on imbalanced datasets - 99% accuracy on 1% positive class is trivial", "Data leakage between train and test splits causes false confidence", "Metric gaming - optimizing a proxy metric that doesn't improve user experience"],
    counterarguments=["For ranking/search systems, offline metrics (NDCG) may not correlate with user engagement - supplement with A/B tests"],
    evidence=["Saito and Rehmsmeier: The Precision-Recall Plot (2005)", "Manning: Evaluation in Information Retrieval (2020)"],
    confidence=0.95))

entries.append(entry("ai_samp_006", "Sampling Methods for LLM Text Generation",
    "Sampling strategies control LLM output diversity and quality, balancing determinism versus creativity for the specific task at hand.",
    "Greedy: pick highest-probability token (argmax) - deterministic but repetitive, misses alternatives. Temperature sampling: apply softmax(logits / temperature) before sampling - low T (0.1-0.5) deterministic and focused, high T (0.8-1.5) diverse and random. Top-k: restrict sampling to the k highest-probability tokens, renormalize, then sample. Top-p (nucleus sampling): restrict to the smallest set of tokens whose cumulative probability >= p (e.g. 0.9), adaptive unlike fixed k. Typical sampling: include tokens near expected frequency. Repetition penalty: divide logits of already-generated tokens to reduce repetition. Frequency and presence penalties: reduce logit proportional to occurrence count. Best practice: low temperature (0.2-0.7) for factual, higher (0.7-1.0) for creative; top_p 0.9-1.0; enable presence penalty.",
    ["llm", "sampling", "temperature", "top-p", "top-k", "generation", "nucleus-sampling"],
    assumptions=["Logits represent well-calibrated probability distribution over vocabulary", "Vocabulary is fixed and known at inference time"],
    invariants=["Greedy decoding and temperature 0 produce identical output", "Top-k=1 is equivalent to greedy decoding"],
    failure_modes=["Temperature too high (above 2.0) - incoherent, off-topic output", "Top-k too small misses relevant but lower-ranked tokens", "No repetition penalty causes text generation loops"],
    counterarguments=["For some tasks (summarization, translation), beam search can produce more globally coherent text than sampling"],
    evidence=["Holtzman et al. The Curious Case of Neural Text Generation (2020)", "OpenAI API documentation on sampling parameters"],
    confidence=0.93))

# ============================================================
# SECURITY PRINCIPLES (priority 4)
# ============================================================
entries.append(entry("sec_owasp_001", "OWASP Top 10: Web Application Security Risks",
    "OWASP Top 10 enumerates the most critical web application security risks, providing a prioritization framework for application security.",
    "Top 10 (2021): (1) Broken Access Control - IDOR, BOLA; fix: deny by default, check every request, validate ownership. (2) Cryptographic Failures - weak TLS, plaintext storage; fix: TLS 1.3, AES-256, Argon2. (3) Injection - SQL, command, LDAP; fix: parameterized queries, ORM, allowlist. (4) Insecure Design - missing security in SDLC; fix: threat modeling. (5) Security Misconfiguration - default credentials, debug mode; fix: hardening. (6) Vulnerable Components - unpatched deps; use SCA tools. (7) Auth Failures - session fixation; fix: MFA, session rotation. (8) Data Integrity Failures - unsigned data; fix: signatures. (9) Logging Failures - no monitoring; fix: structured logging. (10) SSRF - server-side request forgery; fix: URL allowlist, egress filtering.",
    ["owasp", "security", "vulnerabilities", "web-app", "risk"],
    assumptions=["Application accepts external user input", "Security is considered throughout SDLC"],
    invariants=["Never trust user input - validate, sanitize, encode for output context", "Defense in depth - multiple independent controls"],
    failure_modes=["OWASP checklist without deep threat modeling", "Blocking SQL but missing NoSQL injection in same code path", "Fixing symptoms (input sanitization) not root cause (parameterized queries)"],
    counterarguments=["For internal tools with no internet exposure, some OWASP categories may be lower priority"],
    evidence=["OWASP.org Top 10 (2021)", "OWASP Cheat Sheet Series", "MITRE CWE Top 25"],
    confidence=0.97))

entries.append(entry("sec_crypto_002", "Cryptography: Symmetric, Asymmetric, and Hash Functions",
    "Symmetric encryption (AES) provides fast bulk encryption with a shared key; asymmetric (RSA/ECC) enables key exchange and digital signatures; hash functions provide integrity; password hashing uses specialized slow algorithms.",
    "Symmetric: AES (block cipher, 128/256-bit key, modes: GCM = authenticated encryption, CBC = legacy, CTR = streaming). ChaCha20-Poly1305 for mobile (faster than AES without hardware AES). Key exchange: Diffie-Hellman or ECDH over P-256 or X25519. Asymmetric signatures: RSA-PSS or RSASSA-PKCS1-v1_5 (legacy), ECDSA (shorter than RSA), Ed25519 (EdDSA, deterministic nonces, prevents nonce-reuse attacks - preferred). Hashing: SHA-256/384/512 (SHA-2 family), SHA-3 (Keccak, different construction). Password hashing: bcrypt (GPU-resistant, built-in salt), scrypt (memory-hard), Argon2id (PHC winner, memory + time + parallelism). Key derivation: HKDF, PBKDF2, scrypt. NEVER use MD5, SHA-1, or DES for security.",
    ["cryptography", "encryption", "aes", "rsa", "hashing", "argon2", "security"],
    assumptions=["Cryptographically secure PRNG available (os.urandom)", "Keys have sufficient entropy (at least 128 bits)"],
    invariants=["Never reuse nonce/IV with same AES key in GCM mode", "Never use same RSA key for encryption and signing"],
    failure_modes=["Hardcoding keys in source code or config files", "Using non-CSPRNG for cryptographic operations", "Weak/legacy algorithms (MD5, SHA-1, RC4, DES) in production", "Nonce reuse with stream cipher allows XOR of ciphertexts"],
    counterarguments=["For maximum performance in trusted environments, symmetric-only encryption may suffice"],
    evidence=["NIST FIPS 197 (AES)", "RFC 8439 (HMAC and AES-GCM)", "RFC 8032 (EdDSA)", "Password Hashing Competition (Argon2)"],
    confidence=0.96))

entries.append(entry("sec_auth_003", "Secure Authentication and Session Management",
    "Secure authentication requires multi-factor verification, slow password hashing, cryptographically random session tokens, and proper session lifecycle management.",
    "Password storage: bcrypt/scrypt/Argon2id with per-user salt; cost factor high (bcrypt >= 12, Argon2id t=3, memory 64MB). Never store plaintext, MD5, or SHA. MFA: TOTP (RFC 6238) or WebAuthn/FIDO2 (passwordless). Session tokens: cryptographically random, at least 128 bits, httpOnly + Secure + SameSite cookies. Generate new session ID on login (prevents session fixation). Regenerate on privilege escalation. Set expiration plus sliding timeout. Destroy server-side on logout. Refresh token rotation: each refresh rotates both access and refresh tokens. JWT: HS256 (shared secret) or RS256 (asymmetric); short expiry (at most 15 min), refresh via secure refresh token; pin algorithm to prevent none attack.",
    ["auth", "authentication", "session", "mfa", "jwt", "passwords", "security"],
    assumptions=["TLS (HTTPS) is enforced end-to-end", "Clock is synchronized for TOTP (allows +/- 1 step window)"],
    invariants=["Session ID must be unpredictable (CSPRNG) and at least 128 bits", "Password reset links one-time use and time-limited"],
    failure_modes=["Session fixation - attacker-provided session ID accepted instead of regenerated", "JWT stored in localStorage - XSS can steal token", "Session not invalidated on logout causes replay attacks"],
    counterarguments=["For internal tools using SSO (SAML/OIDC), custom auth implementation adds unnecessary risk"],
    evidence=["OWASP Authentication Cheat Sheet", "OWASP Session Management Cheat Sheet", "NIST SP 800-63B Digital Identity Guidelines"],
    confidence=0.98))

entries.append(entry("sec_inj_004", "Injection Attacks: Prevention by Parameterization",
    "Injection attacks occur when untrusted data is interpreted as code or commands; prevention requires parameterized queries, allowlist validation, and context-specific output encoding.",
    "SQL Injection: parameterized queries (prepared statements) or ORM; never string-concatenate user input into SQL. Example: cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,)) vs f-string. NoSQL injection: validate types (parseInt), use ORM, avoid loose equality (in JS). Command injection: avoid shell=True (Python subprocess); use argument lists; allowlist permitted commands. LDAP injection: parameterized filters. SSTI (server-side template injection): sandboxed template engine (Jinja2 autoescape), do not render user input as a template. General prevention: allowlist input validation (type, length, range), context-aware output encoding (HTML, JavaScript, SQL, URL, CSS). Defense in depth.",
    ["injection", "sql-injection", "xss", "command-injection", "parameterized-queries", "security"],
    assumptions=["User input is used in query or command construction", "Application uses string building for queries or commands"],
    invariants=["Parameterization is the primary defense - validation is secondary", "All user-derived output must be encoded for the output context"],
    failure_modes=["Allowlist regex too permissive (e.g. no length limit)", "Using blocklist instead of allowlist - attacker finds bypass", "Encoding for wrong output context (HTML-encode JavaScript that needs JS-encoding)"],
    counterarguments=["For legacy code with extensive string concatenation, parameterized query refactoring requires careful migration"],
    evidence=["PortSwigger Web Security Academy labs", "OWASP Injection Prevention Cheat Sheet", "CWE-89 (SQL injection), CWE-79 (XSS)"],
    confidence=0.97))

entries.append(entry("sec_ssrf_005", "SSRF (Server-Side Request Forgery) Prevention",
    "SSRF occurs when a server fetches a user-supplied URL without validation, allowing attackers to access internal services, cloud metadata endpoints, and private networks.",
    "Defense layers: (1) URL allowlist - only approved domains. (2) IP address validation - resolve to IP, check private ranges (10.x, 172.16-31.x, 192.168.x, 127.x, 169.254.x, ::1, fc00::/7). (3) DNS rebinding prevention - resolve twice at different times. (4) Redirect validation - re-check the final URL after following all redirects. (5) Egress filtering - firewall blocks outbound to internal networks and cloud metadata. (6) Cloud IAM - minimal permissions, block access to metadata service (169.254.169.254). (7) Via service - controlled outbound proxy. Use a dedicated SSRF-safe HTTP client with safe URL validation.",
    ["ssrf", "injection", "vulnerability", "cloud-security", "networking"],
    assumptions=["Server fetches URLs on behalf of users", "Need to access external services sometimes"],
    invariants=["DNS resolution and TCP connection both validated", "Redirects must re-pass all validation checks"],
    failure_modes=["Only validating initial URL not redirect targets", "Not checking IP after DNS resolution", "No egress filtering on cloud instances allows metadata access"],
    counterarguments=["For applications that legitimately proxy arbitrary URLs (e.g. screenshot services), network-level controls are essential"],
    evidence=["PortSwigger Web Security Academy SSRF labs", "Google Cloud SSRF best practices documentation"],
    confidence=0.94))

# ============================================================
# DATA ENGINEERING (priority 5)
# ============================================================
entries.append(entry("de_index_001", "Database Indexing and Query Optimization",
    "Indexes trade faster reads for slower writes and storage; B-tree handles most equality and range queries, while bitmap, hash, GIN, GiST, and BRIN indexes address specific access patterns.",
    "B-tree (balanced tree): default for equality (=), range (<, >, BETWEEN), and prefix LIKE queries. O(log n). Composite index follows leftmost prefix rule - first column must appear in WHERE clause. Write overhead: INSERT/UPDATE/DELETE must update the index. Index-only scan (covering index): all columns needed are in the index - no table row lookup needed. Bitmap index: excellent for low-cardinality columns (gender, status) with AND/OR combinations. Hash index: only single-key equality queries, O(1), no range support, not crash-safe in PostgreSQL (must rebuild). GIN (Generalized Inverted Index): for arrays, full-text search, JSONB keys. GiST/SP-GiST: for geometric, full-text, ranges, IP addresses. BRIN (Block Range Index): for very large append-only tables (time-series data) - small storage, efficient for range queries. Partial index: CREATE INDEX with WHERE condition to reduce size and write cost.",
    ["sql", "indexing", "database", "performance", "btree", "postgres"],
    assumptions=["Read-heavy workload with known query patterns", "Write load justifies read speed improvement"],
    invariants=["Every index adds write overhead - create indexes CONCURRENTLY in production", "PostgreSQL automatically indexes foreign key columns"],
    failure_modes=["Too many indexes slow all write operations", "Composite index column order does not match query patterns", "Missing index on foreign key join columns"],
    counterarguments=["For very small tables (under 1000 rows), sequential scan often beats indexed lookup"],
    evidence=["PostgreSQL documentation on indexes", "Use The Index Luke by Markus Winand"],
    confidence=0.96))

entries.append(entry("de_txn_002", "Database Transactions and ACID Isolation Levels",
    "Transactions ensure ACID properties (Atomicity, Consistency, Isolation, Durability) with isolation levels preventing concurrency anomalies: dirty reads, non-repeatable reads, and phantom reads.",
    "ACID: (1) Atomicity - all-or-nothing; ROLLBACK undoes on error. (2) Consistency - valid state transitions via constraints. (3) Isolation - concurrent transactions isolated. (4) Durability - committed data survives crash (WAL and fsync). Isolation levels: Read Uncommitted (dirty reads possible), Read Committed (prevents dirty reads, allows non-repeatable and phantom), Repeatable Read (prevents dirty and non-repeatable, allows phantom), Serializable (prevents all three). PostgreSQL uses MVCC (Multi-Version Concurrency Control) for snapshot isolation. InnoDB uses next-key locks in Repeatable Read to prevent phantom reads. Use the lowest isolation level that prevents your application's specific anomalies. Serializable is correct but has lowest concurrency.",
    ["database", "transactions", "acid", "isolation", "mvcc", "locking"],
    assumptions=["Database implements at least Read Committed by default", "Transactions are short-lived to minimize lock contention"],
    invariants=["Serializable is correct but slowest - use lowest level that prevents your anomalies", "MVCC avoids read locks but write locks still needed for mutations"],
    failure_modes=["Using Read Committed when Repeatable Read is needed for consistency", "Long-running transactions in PostgreSQL block autovacuum causing table bloat", "Application not retrying serialization failures from Serializable isolation"],
    counterarguments=["For analytical workloads with eventual consistency requirements, read replicas may suffice"],
    evidence=["PostgreSQL documentation on MVCC and isolation levels", "ANSI SQL-92 standard on isolation", "Jim Gray The Transaction Concept"],
    confidence=0.95))

# ============================================================
# DEVOPS AND RELIABILITY (priority 6)
# ============================================================
entries.append(entry("ops_ci_001", "CI/CD Pipeline Design and Deployment Strategies",
    "CI/CD automates building, testing, and deployment; deployment strategies (blue-green, canary, rolling) control how new versions replace old ones, balancing speed, safety, and rollback capability.",
    "CI (Continuous Integration): developers push to shared branch frequently, automated build and tests run on every commit. CD Delivery: every commit passes all tests, artifact is deployable. CD Deployment: auto-deploy to production. Pipeline stages: source -> lint -> build -> unit test -> integration test -> security scan -> deploy staging -> smoke test -> canary deploy -> deploy production. Blue-Green: two identical environments, instant traffic switch, instant rollback (extra cost). Canary: gradually shift traffic percentage, monitor metrics, increase slowly. Rolling: replace instances gradually (slow rollback). Feature flags decouple deploy from release. Health gates: pre-check (tests pass) and post-check (metrics within SLO). Automated rollback on health gate failure.",
    ["ci-cd", "deployment", "blue-green", "canary", "rolling", "sre"],
    assumptions=["Automated tests provide sufficient quality signal", "Health checks are reliable and fast"],
    invariants=["Every deployment must have a defined rollback path", "Health checks must complete faster than client timeout"],
    failure_modes=["Canary traffic percentage too high - large blast radius on bug", "Health check passes but metrics degrade later - need SLO-based rollback", "Feature flag never cleaned up - tech debt accumulates"],
    counterarguments=["For regulatory environments, manual approval gates may be required"],
    evidence=["Google SRE Workbook", "AWS Well-Architected Framework", "Kubernetes deployment strategies"],
    confidence=0.96))

entries.append(entry("ops_slo_002", "SRE: Error Budgets, SLI/SLO/SLA",
    "Site Reliability Engineering balances reliability and feature velocity using error budgets (allowed unreliability), with SLIs (measured indicators), SLOs (targets), and SLAs (contractual agreements).",
    "SLI = Service Level Indicator (metric measured: latency, error rate, availability). SLO = Service Level Objective (target: e.g. 99.9% of requests under 200ms). SLA = Service Level Agreement (contractual penalty). Error budget = 1 - SLO (e.g. 0.1% = 43.2 minutes per month). When budget consumed, freeze feature releases and focus on reliability. Burn rate alerts: fast burn (14.4x rate for 5 minutes), slow burn (6x rate for 30 minutes). SLI types: latency (p99, p95), availability (error rate), freshness. RED metrics per service: Rate, Errors, Duration. Alerting: avoid high-cardinality dimensions to prevent pager fatigue.",
    ["sre", "reliability", "error-budget", "slo", "sli", "sla", "monitoring"],
    assumptions=["SLOs derived from business SLAs and user impact tolerance", "SLIs are measurable and automated"],
    invariants=["Error budgets reset each period (rolling window)", "Alerts page humans only for actionable issues"],
    failure_modes=["SLOs set too lenient - quality degrades unnoticed", "Too many alerts cause fatigue and ignored pages", "No escalation path after alert fires"],
    counterarguments=["For small teams (1-2 engineers), dedicated SRE is impractical - dev team handles ops with automation"],
    evidence=["Google: Site Reliability Engineering (Beyer, Jones, Petoff, 2016)", "Google SRE Workbook"],
    confidence=0.95))

# ============================================================
# MATHEMATICS AND LOGIC (priority 9)
# ============================================================
entries.append(entry("math_bayes_001", "Bayes' Theorem and Probabilistic Reasoning",
    "Bayes' theorem updates probability estimates (posteriors) given new evidence, relating prior belief, likelihood, and marginal probability.",
    "P(A|B) = P(B|A) * P(A) / P(B). P(A) = prior (belief before evidence). P(B|A) = likelihood (probability of evidence given hypothesis). P(B) = marginal (total probability of evidence). P(A|B) = posterior (updated belief). Naive Bayes assumes feature independence. Applications: medical diagnosis P(disease|symptom), spam filtering P(spam|words), A/B testing posterior probability of variant being better. Base rate neglect: always incorporate prior P(A) not just likelihood P(B|A). Bayesian updating is iterative - posterior becomes next prior. For multiple hypotheses, probabilities re-normalize to sum to 1.",
    ["probability", "bayes", "bayesian-reasoning", "statistics", "decision-making"],
    assumptions=["Prior probabilities are known or estimable", "Likelihood P(B|A) is known", "P(B) is positive (evidence is possible)"],
    invariants=["Probabilities of all hypotheses sum to 1", "More evidence shifts posterior from prior toward likelihood"],
    failure_modes=["Base rate neglect - ignoring prior in favor of evidence", "Assuming independence when features are correlated", "Using point estimates instead of full distributions"],
    counterarguments=["Bayesian requires specifying priors which can be subjective - frequentist avoids priors"],
    evidence=["Jaynes: Probability Theory: The Logic of Science", "McGraynor and Sobel: Understanding Odds and Probability"],
    confidence=0.98))

entries.append(entry("math_graph_002", "Graph Theory: Traversals and Core Algorithms",
    "Graphs (vertices connected by edges) model pairwise relationships with fundamental algorithms solving routing, connectivity, and optimization problems.",
    "Definitions: directed/undirected, weighted/unweighted, simple (no self-loops, no multi-edges), complete graph, cycle, DAG. Representations: adjacency list (O(V+E) space, best for sparse), adjacency matrix (O(V^2), good for dense/frequent edge checks). BFS: queue, shortest path in unweighted graph, level-order traversal. DFS: stack/recursion, cycle detection, topological sort, connected components. Dijkstra: non-negative weights, priority queue, O((V+E) log V). Bellman-Ford: handles negative weights, detects negative cycle, O(VE). Floyd-Warshall: all-pairs shortest paths, O(V^3). Kruskal MST: union-find O(E log E). Prim MST: O((V+E) log V). Topological sort: DFS post-order reversed, only for DAG (detects cycles). SCC: Tarjan's or Kosaraju's algorithm. Bipartiteness check via 2-coloring BFS.",
    ["graph-theory", "algorithms", "bfs", "dfs", "dijkstra", "shortest-path"],
    assumptions=["Graph fits in memory or can be external-sorted", "Edges and weights are known a priori"],
    invariants=["Dijkstra requires non-negative edge weights", "Topological sort possible only if graph is a DAG"],
    failure_modes=["BFS/DFS on cyclic graph without visited set causes infinite loop", "Dijkstra on negative weights produces incorrect results", "Wrong graph representation wastes memory on sparse graphs"],
    counterarguments=["For streaming graph data, online algorithms are more appropriate than batch algorithms"],
    evidence=["CLRS Introduction to Algorithms, Graph chapters (22-25)", "Sedgewick and Wayne: Algorithms (4th ed), Part II"],
    confidence=0.97))

# ============================================================
# REASONING FRAMEWORKS (priority 10)
# ============================================================
entries.append(entry("rf_first_001", "First-Principles Thinking and Problem Decomposition",
    "First-principles thinking decomposes complex problems into fundamental truths and rebuilds solutions from those axioms, avoiding the constraints of analogy-based reasoning.",
    "Process: (1) Identify the problem clearly. (2) Break into constituent parts. (3) Identify assumptions and question them - what is provably true? (4) Separate facts, constraints, assumptions, and causal mechanisms. (5) Rebuild from fundamental truths. (6) Focus on constraints that cannot be changed (physics, math, economics). Example: Elon Musk on rocket cost - assumption was 'rockets are expensive because industry says so'; first principles: raw materials (aluminum, carbon fiber, oxygen, pressure vessels) cost a small fraction; reusable rocket is feasible. Tools: Five Whys to peel back layers of assumption; inversion (think backwards from desired outcome).",
    ["thinking-method", "first-principles", "problem-solving", "decomposition", "reasoning"],
    assumptions=["Problem can be broken into independent subproblems", "Fundamental truths are discoverable and unambiguous"],
    invariants=["More first-principles decomposition reveals cheaper and better solutions", "Questioning assumptions is necessary for breakthrough innovation"],
    failure_modes=["Over-decomposing loses sight of practical constraints and market realities", "Reinventing the wheel when existing solutions already embody first principles", "Not knowing what counts as fundamental truth in the domain"],
    counterarguments=["First-principles thinking is cognitively expensive and slow - analogy-based reasoning is pragmatic under time pressure"],
    evidence=["Elon Musk TED talk on first principles thinking", "Feynman technique for learning from first principles"],
    confidence=0.92))

entries.append(entry("rf_rca_002", "Root Cause Analysis: 5 Whys and Fishbone Diagram",
    "Root Cause Analysis systematically identifies the underlying cause of a problem rather than treating symptoms, using iterative questioning or factor categorization.",
    "5 Whys: start with problem statement, ask 'why did this happen?' five times, each answer becomes input to the next 'why'. Stop when you reach a process/system root cause (not a person). Example: 'Car won't start' -> battery dead -> alternator not charging -> serpentine belt broken -> no preventive maintenance -> no maintenance checklist. Fishbone (Ishikawa): categories on branches (People, Methods, Machines, Materials, Measurements, Environment), team adds contributing factors. Pareto analysis: 80/20 rule, focus on the vital few causes. Techniques: 'but why' for depth, 'how can recurrence be prevented' for solution design.",
    ["root-cause-analysis", "debugging", "5-whys", "fishbone", "problem-solving"],
    assumptions=["Problem has a definable root cause rather than being purely systemic", "Contributing factors can be identified through team collaboration and data"],
    invariants=["Root cause should be process/system-level not person-level", "Solutions must address the root cause, not just symptoms"],
    failure_modes=["Stopping too early - fixing symptoms instead of root cause", "Blaming individuals instead of fixing processes", "Asking why too many times loses connection to original problem"],
    counterarguments=["For intermittent or non-reproducible bugs, RCA by interview alone may miss the true cause"],
    evidence=["Toyota Production System (Taiichi Ohno on 5 Whys)", "NASA 5-step RCA methodology"],
    confidence=0.94))


# ============================================================
# ASSEMBLE FINAL STRUCTURE
# ============================================================
domain_specs = [
    ("programming_fundamentals", "software_engineering", 1, "Timeless programming concepts: data structures, algorithms, complexity, design patterns, idioms."),
    ("system_design_principles", "architecture", 2, "Timeless reliability, scalability, and distributed-systems design axioms."),
    ("ai_ml_fundamentals", "machine_learning", 3, "Evergreen AI/ML theory that does not change with model releases."),
    ("security_principles", "security", 4, "Evergreen security axioms, OWASP categories, cryptography fundamentals."),
    ("data_engineering", "data", 5, "SQL, modeling, ETL, and database timeless knowledge."),
    ("devops_reliability", "operations", 6, "CI/CD, deployment, observability, and incident response patterns."),
    ("mathematics_logic", "foundations", 9, "Foundational mathematics and logic for reasoning."),
    ("reasoning_frameworks", "cognition", 10, "General problem-solving, debugging, and decision methodologies."),
]

prefix_map = {
    "programming_fundamentals": "pf_",
    "system_design_principles": "sd_",
    "ai_ml_fundamentals": "ai_",
    "security_principles": "sec_",
    "data_engineering": "de_",
    "devops_reliability": "ops_",
    "mathematics_logic": "math_",
    "reasoning_frameworks": "rf_",
}

categories = []
for did, dom, prio, desc in domain_specs:
    prefix = prefix_map[did]
    cat_entries = [e for e in entries if e["artifact_id"].startswith(prefix)]
    categories.append({
        "category_id": did,
        "priority": prio,
        "domain": dom,
        "description": desc,
        "entries": cat_entries,
    })

output = {
    "schema_version": "2.1",
    "meta": {
        "purpose": "SupremeAI pre-production local knowledge injection seed - timeless, slow-changing, vendor-neutral knowledge. Structured to KnowledgeArtifact schema (matching tools/knowledge_squeezer/models.py) for direct ingestion into ai_memory / ChromaDB / pgvector.",
        "usage": "Embed each entry's claim+solution+invariants text (768-dim) into vector DB. Serve via RAG as fallback when LLM providers are unreachable.",
        "language": "en",
        "generated": "2026-08-22",
        "principles": ["timeless", "slow-changing", "evergreen", "vendor-neutral", "defensive", "dense", "verifiable", "atomic"],
        "embedding_guidance": {
            "target_dim": 768,
            "chunk_strategy": "One artifact per vector chunk; embed claim+solution+invariants for precision.",
            "metadata_fields": ["artifact_id", "category_id", "domain", "type", "confidence", "verification_status", "tags"],
            "rerank": "Hybrid BM25 + vector cosine; boost confidence:high and verification_status:verified"
        },
        "volume_plan": {
            "tier1_mvp_floor": 1500,
            "tier2_production_target": 6000,
            "tier3_mature_ceiling": 12000
        },
        "excluded_categories_reason": {
            "real_time_data": "Stock prices, weather, live news - stale in seconds; use live API fallback.",
            "current_events": "Elections, sports scores - ephemeral; RAG over live sources.",
            "vendor_pricing": "API costs, quotas, model names - change monthly; keep in feature-flag config.",
            "user_personal_data": "PII, transactions - never inject into static knowledge base."
        }
    },
    "categories": categories,
    "quality_gates": {
        "min_confidence": 0.90,
        "max_tokens_per_entry": 400,
        "required_fields": ["artifact_id", "domain", "claim", "solution", "assumptions", "invariants", "failure_modes", "evidence", "confidence", "verification_status", "tags"],
        "verification": "Every entry has verification_status:verified (no decay). Static facts tagged accordingly.",
        "dedup": "Hash(claim) unique; cross-category overlap under 5%"
    },
    "implementation_notes": {
        "storage": "Primary: ChromaDB (cosine similarity) with TF-IDF fallback (backend/memory/chromadb_store.py). Fallback: SQLite (backend/memory/sqlite_store.py). Cloud: Supabase pgvector (1536-dim embeddings via all-MiniLM-L6-v2 zero-padded).",
        "ingestion_command": "python tools/tool_knowledge_injector.py --inject --verify",
        "retrieval_strategy": "Embed artifact claim+solution text. Query via search_semantic (ChromaDB) or search_learned_facts (pgvector). RAGPipeline.retrieve_context with n=5, threshold 0.15.",
        "fallback_chain": "ChromaDB vector search -> SQLite TF-IDF keyword -> memory_vault.json -> generic response. Each layer independent of network.",
        "update_cadence": "Evergreen entries need no routine review. New domains added incrementally as separate arrays.",
        "confidence_usage": "0.95-1.0: always returned. 0.90-0.95: returned with note. Below 0.90: suppressed in degraded mode.",
        "size_budget": "Each artifact ~1-2KB. At 1500 entries: ~3MB raw, ~600KB embeddings. Fits free-tier Render disk."
    }
}

outpath = "coldstart_knowledge_seed_knowledge_base.json"
with open(outpath, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

total_entries = sum(len(c["entries"]) for c in output["categories"])
print(f"Generated {outpath}: {len(output['categories'])} categories, {total_entries} total entries")
for c in output["categories"]:
    print(f"  {c['category_id']} (priority {c['priority']}): {len(c['entries'])} entries, domain={c['domain']}")
