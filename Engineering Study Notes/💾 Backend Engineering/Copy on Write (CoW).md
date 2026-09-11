Based on: [Copy-On-Write - When to Use It, When to Avoid It](https://arpitbhayani.me/blogs/copy-on-write)

## Summary
Copy-on-write (CoW) is an optimization technique where copying is **deferred until the first write**. Instead of immediately duplicating a resource, two instances initially **share the same underlying data**. A real copy is created only when one of them tries to modify it.

## Core idea
- A normal copy creates an independent duplicate immediately
- A CoW copy starts as a **shared reference**
- On the first mutation, the system performs the actual copy
- This avoids unnecessary duplication when data is copied but never modified

## Why CoW is useful
CoW is valuable when:
- copying is expensive
- reads are common
- writes are relatively rare
- many copies may never be modified

It improves:
- **memory efficiency**
- **copy performance**
- **overall system throughput** in read-heavy scenarios

## Mental model
Think of CoW as:
- **copy now by reference**
- **copy later by value if needed**

This makes the initial duplication cheap while still preserving isolation when mutations happen.

## Deep copy vs copy-on-write
### Deep copy
A deep copy duplicates the entire resource and everything it references immediately.

### Copy-on-write
CoW delays that duplication:
- both versions point to the same data at first
- only the modified part is cloned when a write happens

This keeps the initial copy fast and lightweight.

## How it works
A typical CoW workflow:
1. Create a logical copy of a resource
2. Mark the underlying resource as shared
3. Allow both copies to read from the same data
4. On first write, clone the shared resource
5. Apply the mutation to the new private copy

## Typical use cases

### Operating systems
A classic use case is process creation with `fork()`:
- parent and child initially share memory pages
- pages are copied only when one process writes to them

This makes process creation much cheaper than copying all memory up front.

### Persistent data structures
CoW works well for data structures where:
- most nodes stay unchanged
- only a small path or subset changes per update

Instead of rebuilding everything, the system copies only the changed parts and reuses the rest.

### Storage and filesystems
CoW is also useful in storage systems:
- unchanged blocks can be shared
- modified blocks are written elsewhere
- this enables efficient snapshots and versioning behavior

## Advantages
- cheap logical copies
- reduced memory usage when copies are read-only
- avoids unnecessary duplication
- efficient for read-heavy workloads
- enables structural sharing

## Costs and tradeoffs
CoW is not free. It introduces:
- extra bookkeeping to track shared ownership
- write-time overhead on the first mutation
- more complexity in implementation
- possible latency spikes when the deferred copy finally happens

## When CoW works well
Use CoW when:
- the copied object is large
- writes are infrequent
- many copies stay unchanged
- you want to optimize copy cost without losing isolation

## When CoW is a bad fit
Avoid CoW when:
- writes are frequent
- the object is small and cheap to copy
- predictable write latency matters
- implementation simplicity is more important than memory savings

In write-heavy workloads, deferred copying can become a net negative because the copy eventually happens anyway, plus the system pays the bookkeeping cost.

## Design intuition
CoW is best seen as a **pay-later strategy**:
- it converts eager copying cost into conditional copying cost
- that is great when the write may never happen
- that is wasteful when writes happen almost every time

## Main takeaway
Copy-on-write is a powerful optimization for systems where **copying is common but mutation is rare**. It saves memory and makes copies cheap, but it shifts cost to write time and adds implementation complexity. It is most effective in **read-heavy, sparsely mutated** workloads.

## Tags
#systems #operatingsystems #memory #copyonwrite #performance #datastructures #filesystems