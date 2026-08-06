# Mock Interview Report — Backend Engineer

- Interviewer: **Senior Backend Engineer, Core Services** (Series B SaaS)
- Seniority: mid · Focus: mixed · Base difficulty: 5.0
- Status: completed · Turns: 5
- Optimizes for: execution reliability, cross-team coordination, system design fundamentals
- Vibe: Efficient and direct; asks for the trade‑off, then the plan.

## Transcript

### Turn 1 — behavioral (difficulty 5.0)
**Q:** Tell me about a time you had to pivot a project due to a critical bug discovered late in the cycle. What trade‑offs did you consider, what plan did you implement, and what was your personal ownership in ensuring the release stayed on track?
**A:**
In late‑stage development of a payment‑gateway microservice, a race condition in the credit‑card validation module caused a 15 % failure rate under load. I immediately halted the release, convened a 30‑minute “bug‑flood” sprint, and re‑architected the validation logic to use a lock‑free queue. Trade‑offs: I weighed delaying the release by 3 days against the risk of a production outage that could cost $200k in refunds. I chose the latter, adding a temporary fallback to an external validation API while we fixed the core. I owned the rollback plan, coordinated with ops for a blue‑green deploy, and ran a 24‑hour canary test. The release shipped on schedule with zero post‑production incidents.
*Score 4.4 — substantive*
*substance: 4.0 · structure: 4.0 · relevance: 5.0 · credibility: 5.0 · differentiation: 4.0*

### Turn 2 — technical (difficulty 6.0)
*Expects code*
**Q:** Implement a thread‑safe in‑memory LRU cache that holds up to 1000 string key/value pairs. Provide the core code, then explain the trade‑offs between using a ConcurrentHashMap with a separate LinkedList versus a synchronized LinkedHashMap. Finally, describe how you would handle a scenario where the JVM is under heavy memory pressure and what fallback strategy you would employ.
*Context:* The cache should support get(key) and put(key, value) operations, evicting the least recently used entry when the size limit is reached.
**A:**
**Core code (Java 17)**  
```java
import java.util.concurrent.*;
import java.util.*;

public class LruCache {
    private static final int CAPACITY = 1_000;
    private final ConcurrentHashMap<String, Node> map = new ConcurrentHashMap<>(CAPACITY);
    private final ReentrantLock lock = new ReentrantLock();
    private Node head, tail;

    private static class Node {
        final String key, value;
        Node prev, next;
        Node(String k, String v){ key=k; value=v; }
    }

    public String get(String key) {
        Node node = map.get(key);
        if (node == null) return null;
        moveToHead(node);
        return node.value;
    }

    public void put(String key, String value) {
        Node node = map.get(key);
        if (node != null) {
            node.value = value;
            moveToHead(node);
            return;
        }
        node = new Node(key, value);
        lock.lock();
        try {
            addFirst(node);
            map.put(key, node);
            if (map.size() > CAPACITY) evictLast();
        } finally { lock.unlock(); }
    }

    private void moveToHead(Node n) {
        lock.lock();
        try {
            if (n == head) return;
            unlink(n);
            addFirst(n);
        } finally { lock.unlock(); }
    }

    private void addFirst(Node n) {
        n.next = head;
        if (head != null) head.prev = n;
        head = n;
        if (tail == null) tail = n;
    }

    private void unlink(Node n) {
        if (n.prev != null) n.prev.next = n.next;
        else head = n.next;
        if (n.next != null) n.next.prev = n.prev;
        else tail = n.prev;
    }

    private void evictLast() {
        if (tail == null) return;
        map.remove(tail.key);
        unlink(tail);
    }
}
```

**Trade‑offs**  
*ConcurrentHashMap + LinkedList*:  
- **Pros**: High concurrency for reads; only lock list during updates.  
- **Cons**: Manual synchronization complexity; risk of list corruption if lock omitted.  
*Synchronized LinkedHashMap*:  
- **Pros**: Single data structure; built‑in ordering; simpler code.  
- **Cons**: Global lock on every access; lower throughput under contention.  

**Memory‑pressure fallback**  
When `Runtime.getRuntime().freeMemory()` falls below a threshold (e.g., 10 % of max), switch to a *soft‑reference* cache: wrap values in `SoftReference`. Eviction then occurs automatically under GC pressure, preventing OutOfMemoryError while still serving cached data when memory is available. This keeps the cache adaptive without manual eviction logic.
*Score 3.0 — substantive*
*substance: 3.0 · structure: 3.0 · relevance: 3.0 · credibility: 3.0 · differentiation: 3.0*

### Turn 3 — case (difficulty 6.0)
**Q:** Design a real‑time analytics pipeline for a streaming service that must process 10k events per second, with low latency and high fault tolerance. Outline components, trade‑offs between batch vs stream processing, how you would handle back‑pressure, and what fallback strategy you would use if a downstream service fails. Explain your personal ownership of ensuring reliability.
*Context:* Assume the service uses Kafka for event ingestion, has microservices, and must support real‑time dashboards.
**A:**
I’d build a Kafka‑first pipeline: producers write to a high‑throughput topic (10 k eps) with a 1 s retention. A Kafka Streams or Flink job reads the topic, keeps a RocksDB/Redis state store for 10‑minute windows, and pushes results to a low‑latency Redis cache that feeds the dashboards.  

**Batch vs stream trade‑offs**: stream gives <100 ms latency but limited fault‑tolerance; batch (e.g., nightly Spark) offers stronger consistency and easier recovery but unacceptable latency for real‑time dashboards. I chose stream for core metrics and scheduled micro‑batch jobs for nightly aggregates.  

**Back‑pressure**: the consumer pauses when the processing queue exceeds 5 k messages, and the framework signals Kafka to reduce fetch rate.  

**Fallback**: if the dashboard service goes down, the stream writes to a dead‑letter topic, triggers a circuit‑breaker, and retries with exponential back‑off; meanwhile a cached snapshot keeps the UI alive.  

I own reliability by writing end‑to‑end tests, setting up Prometheus alerts for lag > 2 s, and running quarterly chaos‑engineering drills.
*Score 3.0 — substantive*
*substance: 3.0 · structure: 3.0 · relevance: 3.0 · credibility: 3.0 · differentiation: 3.0*

### Turn 4 — behavioral (difficulty 6.0)
**Q:** Tell me about a time you had to lead a cross‑team effort to refactor a legacy module that was critical to production. What trade‑offs did you evaluate between a full rewrite and incremental refactor, how did you plan the rollout, and what fallback did you set up if the refactor caused a regression? What was your personal ownership in ensuring the change was delivered safely?
**A:**
I led a six‑team effort to refactor the legacy “Order‑Processing” module that handled 75 % of our daily revenue. I chose an incremental approach: split the module into three bounded contexts, refactor each in a feature‑branch, and deploy with feature flags. A full rewrite would have required 12 weeks of downtime and a 30 % risk of breaking the 3‑hour settlement window, so incremental refactor minimized risk and cost. The rollout was staged: first 10 % of traffic, then 30 %, 60 %, and finally 100 %, monitored by automated smoke tests and a 1‑hour rollback window. I set up a fallback by keeping the original binary in a parallel “legacy” environment and a circuit‑breaker that redirected traffic back if latency exceeded 200 ms. I owned the release plan, coordinated daily stand‑ups, and personally approved each stage after passing all regression tests, ensuring the change delivered safely.
*Score 4.2 — substantive*
*substance: 4.0 · structure: 4.0 · relevance: 5.0 · credibility: 5.0 · differentiation: 3.0*

### Turn 5 — technical (difficulty 7.0)
*Expects code*
**Q:** Implement a sliding window rate limiter for an API that supports per-user and global limits. Provide the core code in Java, then explain trade-offs between using a fixed window vs sliding window, and how you'd handle high memory usage or a burst scenario. Also describe fallback strategy if the limiter becomes a bottleneck.
**A:**
**Java core**

```java
class SlidingRateLimiter {
    private final int userLimit, globalLimit, windowMs;
    private final ConcurrentHashMap<String, Deque<Long>> userMap = new ConcurrentHashMap<>();
    private final Deque<Long> globalQueue = new ConcurrentLinkedDeque<>();
    private final ReentrantLock lock = new ReentrantLock();

    public SlidingRateLimiter(int userLimit, int globalLimit, int windowMs) {
        this.userLimit = userLimit; this.globalLimit = globalLimit; this.windowMs = windowMs;
    }

    public boolean allow(String userId) {
        long now = System.currentTimeMillis();
        lock.lock();
        try {
            // purge old entries
            purge(userMap.computeIfAbsent(userId, k -> new ArrayDeque<>()), now);
            purge(globalQueue, now);

            if (userMap.get(userId).size() >= userLimit || globalQueue.size() >= globalLimit)
                return false;

            userMap.get(userId).addLast(now);
            globalQueue.addLast(now);
            return true;
        } finally { lock.unlock(); }
    }

    private void purge(Deque<Long> q, long now) {
        while (!q.isEmpty() && now - q.peekFirst() > windowMs) q.pollFirst();
    }
}
```

**Trade‑offs**  
Fixed window is O(1) and cheap, but can let a burst hit the next window, giving ~2× the limit. Sliding window smooths bursts, but needs per‑user queues and O(k) purge, increasing CPU and memory.

**High memory / burst**  
Use a probabilistic counter (leaky bucket) or a time‑bucketed counter with exponential decay. Store only timestamps for active users; drop users after inactivity. For a burst, temporarily raise the limit for a short grace period or reject until the queue clears.

**Fallback if bottleneck**  
Expose a “soft‑limit” mode: if lock contention > 5 ms, switch to a simple token bucket per user and a global counter in Redis. If that also stalls, return a 429 with a retry‑after header and log the spike for later scaling.
*Score 4.2 — substantive*
*substance: 4.0 · structure: 4.0 · relevance: 5.0 · credibility: 4.0 · differentiation: 4.0*

## Decisions
- `new_topic` (strong_performance)
- `new_topic` (solid_moderate)
- `new_topic` (solid_moderate)
- `new_topic` (strong_performance)
- `end_interview` (strong_finish)

## Summary
- Root cause: **insufficient-specificity**
- Drill: **Specificity pass** (targets credibility)
- Trend: flat · Overall average: 3.76

## Methodology
- Evaluator model: openai/gpt-oss-20b
- Model fallback used: no
- All evaluations validated: yes

## Coach
## What went well  
- **Concrete metrics**: You cited a 15 % failure rate, a 3‑day delay, and a $200 k refund risk in the payment‑gateway story, which made the stakes crystal clear.  
- **Ownership language**: Phrases like “I immediately halted the release” and “I owned the rollback plan” show you take personal responsibility for outcomes.  
- **Structured trade‑offs**: You weighed delay versus outage risk and quantified the impact (e.g., 12 weeks downtime vs. 30 % risk) when deciding on the incremental refactor, giving the interviewer a clear decision framework.

## The pattern  
Your answers often lack the level of detail that turns a good story into a credible one.  
*Example*: In the LRU‑cache question, you supplied code but did not mention any concrete number for memory usage, thread count, or a specific fallback strategy. The answer felt generic because it omitted a metric and a first‑person action, which is exactly what the drill is targeting.

## Drill  
**Specificity Pass**  
1. **Pick three recent answers** (e.g., the LRU cache, the sliding‑window limiter, and a behavioral story).  
2. **Add a concrete example**: name the artifact or scenario you worked on.  
3. **Insert a metric**: a number, percentage, or time that quantifies the impact.  
4. **State a first‑person action** you took that drove the outcome.  
5. **Review**: read each revised answer aloud, checking that the metric and action are clear and that the story feels grounded.  
*Coaching note*: Focus on “I” statements and tangible numbers—this is what moves credibility from “good” to “great.”

## Next session  
**Goal**: In the next mock interview, include at least one metric and a first‑person action in **every** answer to raise your credibility dimension from 4.0 to 4.3. Track the change by scoring each answer on the same rubric.