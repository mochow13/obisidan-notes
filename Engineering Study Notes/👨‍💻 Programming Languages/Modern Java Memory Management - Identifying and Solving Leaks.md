
**Source:** [How to trace a Java Memory Leak by Victor Rentea](https://www.youtube.com/watch?v=8lswtL1wqxk)

## 🧠 Core Philosophy: Prepare for Death
Every Java project in production should be configured to die when it encounters an `OutOfMemoryError` and capture a heap dump. Leaving a JVM running after it runs out of memory leaves it in an unhealthy, corrupted state where background processes (like metrics and logging) may fail.

**The "Necropsy" Flags:**
Always deploy to production with the flags to capture a heap dump upon crash. Once you have the heap dump, 80% of your troubleshooting job is done.
```bash
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/path/to/surviving/storage
```

---

## 🔬 Heap Dump Analysis Basics
When analyzing memory in tools like VisualVM, IntelliJ Profiler, or Eclipse MAT, it's crucial to understand how object sizes are calculated.

* **Shallow Size:** The memory allocated strictly for the object's fields and pointer (e.g., an 8-byte pointer on a 64-bit JVM). This is rarely what you are looking for during an investigation.
* **Retained Size:** The sum of the sizes of all objects in the object graph that are kept alive *only* by this object. If the root object dies, all the memory in its retained size is freed. This is the metric you should focus on.

---

## 🚨 Common Memory Leaks & Pitfalls

### 1. High Cardinality Metrics
Metrics (like Prometheus/Micrometer) are essential, but tagging them with dynamically generated, high-cardinality values—like a random `UUID` or an unbounded URL path—will tag the metric with an infinite spectrum of values. This will quickly cause an Out of Memory error.
**Takeaway:** Never use highly dynamic data (like IDs or raw URLs) as metric tags.

### 2. Hibernate First-Level Cache (Persistence Context)
When streaming over a massive result set (e.g., exporting a 600MB database table into a file with only 200MB of JVM RAM allocated), loading the entities keeps them in Hibernate's First-Level Cache (Transaction-Scoped Cache).
**The Fix:** Manually tell the `EntityManager` to forget the entity using `detach()` or use a `StatelessSession`.
```java
// Fix: Detach after processing to free memory
while (resultSet.hasNext()) {
    Entity entity = resultSet.next();
    process(entity);
    entityManager.detach(entity); //
}
```

### 3. Caching Pitfalls
* **DIY Caches:** Never build your own caches (e.g., using a `HashMap` that only grows and never evicts). Always use established libraries like Caffeine or Redis that support max sizes and eviction times.
* **Missing `equals`/`hashCode`:** If the objects used as cache keys lack proper `equals` and `hashCode` implementations, every lookup will be a cache miss, dropping the cache hit ratio to 0% and filling up memory.
* **Mutating Keys:** If an entity (like a Hibernate entity) has a null ID when entering the cache, but receives an ID upon saving, its hash mutates. Subsequent lookups will miss the cache because the key inside the cache has changed its identity.
* **Always Monitor:** A cache without a metric for its size and hit ratio should never go to production.

### 4. Non-Static Inner Classes & Anonymous Classes
Non-static inner classes keep a hidden reference to their enclosing parent class. This means the inner class can inadvertently keep a massive parent object alive in memory. The same applies to anonymous interface implementations (e.g., passing `new Predicate() { ... }` instead of a lambda) and double-brace initialization (e.g., `new HashMap<>() {{ put(...) }}`).
**The Fix:** Always mark inner classes as `static`.

### 5. Number Parsing DoS (The "Popcorn Effect")
Calling big number parsers (like `BigDecimal`) on unvalidated strings can be catastrophic. If a JSON payload contains a massive sequence of scientific notation characters (like a `UUID` without dashes interpreted as a string of `E`s or `e`s), `BigDecimal` will exhaust all memory trying to construct the number, killing instances one by one (e.g., taking down Kafka listeners).

### 6. The `List.subList()` View Leak
`List.subList(from, to)` does not create a new list; it returns a *view* backed by the original list. If you take a `subList` of the last 10 items of a million-item list and keep it around, the entire million-item list is retained in memory.
**The Fix:** Create a completely new list if you intend to store it.
```java
// Bad: retains the entire original list
List<String> lastTen = largeList.subList(largeList.size() - 10, largeList.size());

// Good: allocates a new, isolated list
List<String> lastTenIsolated = new ArrayList<>(largeList.subList(...));
```

### 7. ThreadLocal Data in Thread Pools
A `ThreadLocal` holds data specific to the current thread. However, modern JVMs (e.g., Tomcat) use Thread Pools. When an HTTP thread finishes your request, the thread returns to the pool without dying. If you leave data in a `ThreadLocal`, it remains attached to that thread forever (or until overwritten), bloating memory.
**The Fix:** Always clear `ThreadLocal` data using a `try-finally` block.
```java
try {
    myThreadLocal.set(heavyData);
    // ... do work ...
} finally {
    myThreadLocal.remove(); // Always clean up!
}
```
*Note: Third-party libraries often leave orphaned `ThreadLocal` data. You might have to clear it manually using Reflection or Jar shading.*

### 8. Unbounded Queues & CompletableFuture
Submitting heavy background tasks to an unbounded queue (like the default `ForkJoinPool.commonPool()`) via `CompletableFuture.runAsync()` is highly dangerous under load. If you receive tasks faster than you can process them, the queue will grow infinitely and cause an OOM.
**The Fixes:**
1. **Backpressure:** Use a custom thread pool with a fixed queue capacity. If the queue is full, it will throw a `RejectedExecutionException`, saving your system.
2. **Lazy Loading:** Don't load massive datasets (like 10MB blobs) into memory *before* submitting them to the queue. Load the data from within the background worker itself only when it's ready to process.

### 9. Executor Self-Submit Deadlocks
If a thread running inside a thread pool submits *another* task to that same thread pool, and then calls `.get()` or `.join()` to wait for its completion, you risk a deadlock. If all threads in the pool are busy waiting for their sub-tasks to finish, no threads are available to actually execute those sub-tasks.
