## Overview

In Go, there are several ways to safely share map-like data across goroutines. The most common options are:

- A regular `map` protected by `sync.Mutex`
- A regular `map` protected by `sync.RWMutex`
- The specialized concurrent map type `sync.Map`

The best choice depends on the workload, especially the balance between reads and writes, the need for type safety, and whether operations need to maintain broader invariants.

---

## `sync.Map`

`sync.Map` is a specialized concurrent map provided by Go's standard library.

It is safe for concurrent use by multiple goroutines without manually adding a separate mutex.

```go
var cache sync.Map

cache.Store("user:1", "Alice")

value, ok := cache.Load("user:1")
if ok {
    fmt.Println(value)
}
```

Unlike a regular Go map, `sync.Map` does not require you to wrap every access with a lock.

---

## When `sync.Map` Is Suitable

### 1. Many Reads, Few Writes

`sync.Map` is well suited for workloads where the map is read frequently but updated rarely.

A common example is a cache that is populated once and then read many times.

```go
var cache sync.Map

value, ok := cache.Load(key)
if !ok {
    value = computeValue(key)
    actual, _ := cache.LoadOrStore(key, value)
    value = actual
}
```

This pattern avoids duplicate work while allowing many goroutines to read concurrently.

---

### 2. Keys Are Mostly Written Once, Then Read Many Times

`sync.Map` works well when entries are effectively append-only or mostly stable after being created.

Good examples include:

- Memoization caches
- Configuration lookup caches
- Reflection or type metadata caches
- Compiled regular expression caches
- Session or connection lookup tables where entries are mostly stable

This is one of the most natural use cases for `sync.Map`.

---

### 3. Goroutines Operate on Mostly Different Keys

`sync.Map` can also be useful when many goroutines access different keys independently.

For example:

```go
var counters sync.Map // key -> *atomic.Int64
```

This can reduce contention compared with a single global lock around a normal map.

---

### 4. You Need Built-In Atomic Map Operations

`sync.Map` provides several useful atomic operations:

```go
Load
Store
LoadOrStore
LoadAndDelete
CompareAndSwap
CompareAndDelete
Swap
Range
```

These can simplify concurrent logic that would otherwise require careful locking.

Example:

```go
actual, loaded := cache.LoadOrStore(key, value)
if loaded {
    // Another goroutine already stored a value for this key.
    value = actual
}
```

---

## When to Avoid `sync.Map`

### 1. You Need Type Safety

`sync.Map` stores keys and values as `any`, so you lose compile-time type safety.

```go
value, ok := m.Load("user")
if ok {
    user := value.(*User) // runtime type assertion
}
```

With a regular map, the type is explicit and checked at compile time:

```go
map[string]*User
```

For most application-level code, this is often clearer and safer.

---

### 2. You Frequently Update the Same Keys

If many goroutines repeatedly update the same entries, `sync.Map` may not be the best choice.

In that case, consider:

- `map` + `sync.Mutex`
- `map` + `sync.RWMutex`
- Sharded maps
- Atomic values for individual entries

---

### 3. You Need Map-Wide Invariants

`sync.Map` is not good when multiple keys need to be updated together atomically.

For example:

```go
balances[userA] -= amount
balances[userB] += amount
```

This kind of operation needs a broader lock to preserve correctness.

A regular map with a mutex is usually better:

```go
mu.Lock()
balances[userA] -= amount
balances[userB] += amount
mu.Unlock()
```

---

### 4. You Need a Consistent Snapshot While Iterating

`sync.Map.Range` does not provide a fully consistent snapshot.

Entries may be added, deleted, or modified while iteration is happening.

```go
m.Range(func(key, value any) bool {
    fmt.Println(key, value)
    return true
})
```

This is fine for approximate inspection or cleanup logic, but not for operations requiring a stable view of all entries.

---

### 5. The Map Is Small or Simple

For simple cases, a regular map with a mutex is usually easier to read and maintain.

```go
type SafeMap struct {
    mu sync.Mutex
    m  map[string]int
}
```

Do not use `sync.Map` just because multiple goroutines are involved. It is specialized, not a general replacement for `map`.

---

## General Rule for `sync.Map`

```text
Use map + mutex by default.
Use sync.Map when reads dominate, keys are mostly stable, or goroutines operate on independent keys.
```

`sync.Map` is best viewed as a specialized concurrent cache or lookup table, not as the default concurrent map abstraction.

---

# `Mutex` vs `RWMutex`

## `sync.Mutex`

A `sync.Mutex` provides exclusive access.

Only one goroutine can hold the lock at a time.

```go
mu.Lock()
value := m[key]
mu.Unlock()
```

Even if two goroutines are only reading, they still block each other when using a plain `Mutex`.

This makes `Mutex` simple and safe, but not always optimal for read-heavy workloads.

---

## `sync.RWMutex`

A `sync.RWMutex` separates read locking from write locking.

It provides two kinds of locks:

- `RLock()` / `RUnlock()` for readers
- `Lock()` / `Unlock()` for writers

Multiple readers can hold the read lock at the same time.

```go
mu.RLock()
value := m[key]
mu.RUnlock()
```

Writers still require exclusive access:

```go
mu.Lock()
m[key] = value
mu.Unlock()
```

While a writer holds the lock, no readers or other writers can proceed.

---

## Example: Safe Map with `RWMutex`

```go
type SafeMap struct {
    mu sync.RWMutex
    m  map[string]int
}

func (s *SafeMap) Get(key string) (int, bool) {
    s.mu.RLock()
    defer s.mu.RUnlock()

    v, ok := s.m[key]
    return v, ok
}

func (s *SafeMap) Set(key string, value int) {
    s.mu.Lock()
    defer s.mu.Unlock()

    s.m[key] = value
}
```

In this design:

- Many goroutines can call `Get` concurrently.
- Only one goroutine can call `Set` at a time.
- `Set` blocks readers while the write is happening.

---

## Why Use `RWMutex` Instead of Just `Mutex`?

Use `RWMutex` when reads dominate and reads can safely happen concurrently.

With a plain `Mutex`, this happens:

```text
Reader 1 blocks Reader 2
Reader 2 blocks Reader 3
Reader 3 blocks Reader 4
```

With an `RWMutex`, this can happen:

```text
Reader 1, Reader 2, Reader 3, and Reader 4 all read concurrently
```

That can improve performance in read-heavy workloads.

---

## When `RWMutex` Is Useful

`RWMutex` is useful when:

- Many goroutines read the same data
- Writes are relatively rare
- Read operations are not completely trivial
- Concurrent reads can safely happen without violating invariants

Example use cases:

- Read-heavy in-memory caches
- Shared configuration state
- Routing tables
- Metadata registries
- Mostly-read lookup maps

---

## When a Plain `Mutex` Is Better

A plain `Mutex` may be better when:

- Writes are frequent
- Critical sections are tiny
- The lock is not heavily contended
- Simplicity matters more than potential read concurrency
- You are not sure `RWMutex` improves performance

`RWMutex` has more internal bookkeeping than `Mutex`, so it is not automatically faster.

For small or simple operations, a plain `Mutex` can be just as good or better.

---

## Rule of Thumb: `Mutex` vs `RWMutex`

```text
Start with Mutex.
Use RWMutex when the workload is clearly read-heavy or profiling shows that concurrent reads would help.
```

---

# Choosing Between `Mutex`, `RWMutex`, and `sync.Map`

## Use `Mutex` When

Use `sync.Mutex` when:

- You want the simplest correct solution
- Reads and writes both happen frequently
- You need to protect multiple fields together
- You need to maintain invariants across multiple map entries
- The critical section is small

Example:

```go
type Store struct {
    mu sync.Mutex
    users map[string]*User
}
```

---

## Use `RWMutex` When

Use `sync.RWMutex` when:

- Reads are much more frequent than writes
- Multiple readers can safely access the data concurrently
- You still want type safety with a regular map
- You may need to protect broader state, not just individual map entries

Example:

```go
type Store struct {
    mu sync.RWMutex
    users map[string]*User
}
```

---

## Use `sync.Map` When

Use `sync.Map` when:

- The map is mostly read-only after initial writes
- Keys are mostly written once and read many times
- Goroutines usually operate on independent keys
- You benefit from operations like `LoadOrStore`
- You are building something like a concurrent cache or registry

Example:

```go
var cache sync.Map
```

---

# Practical Decision Guide

```text
Do I need a concurrent map?
    |
    v
Start with map + Mutex.
    |
    v
Are reads much more frequent than writes?
    |
    +-- Yes --> Consider map + RWMutex.
    |
    +-- No  --> Keep map + Mutex.
    |
    v
Are keys mostly written once and read many times,
or do goroutines operate on independent keys?
    |
    +-- Yes --> Consider sync.Map.
    |
    +-- No  --> Prefer map + Mutex or map + RWMutex.
```

---

# Final Takeaways

- `sync.Map` is specialized, not a default replacement for `map`.
- `Mutex` is simple and often the best starting point.
- `RWMutex` helps when many readers can safely run concurrently.
- `sync.Map` is useful for read-heavy, mostly-stable, or independent-key workloads.
- If you need type safety or map-wide consistency, prefer a regular map with a lock.
- If unsure, start with `Mutex`, then optimize based on workload or profiling.

---

## One-Line Summary

```text
Use Mutex by default, RWMutex for clear read-heavy shared state, and sync.Map for specialized concurrent cache-like workloads.
```
