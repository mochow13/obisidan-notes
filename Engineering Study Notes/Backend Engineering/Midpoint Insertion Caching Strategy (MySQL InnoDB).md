Based on: [How MySQL Avoids Performance Hits from Table Scans](https://arpitbhayani.me/blogs/midpoint-insertion-caching-strategy)

## Summary
MySQL InnoDB uses a modified LRU-based buffer pool strategy called **midpoint insertion** to prevent **full table scans** from polluting the cache. Instead of inserting newly read pages at the most-recently-used end, it inserts them into the **old** portion of the list. Pages only get promoted to the **young** portion if they are accessed again.

## Why this matters
Disk reads are much slower than RAM reads, so databases rely heavily on caching pages in memory. Since the cache is much smaller than disk, the engine needs an eviction policy that keeps genuinely useful pages in memory while removing less useful ones.

## Core concepts

### Pages
- Databases move data between disk and RAM in **pages**
- A page may contain one or many rows depending on row size
- Typical page sizes are a few KBs, such as 4KB, 8KB, 16KB, or 32KB

### Locality of reference
#### Spatial locality
If one row is accessed, nearby rows are likely to be accessed soon. This is one reason page-based storage and read-ahead help performance.

#### Temporal locality
If a page was accessed recently, it is likely to be accessed again soon. Traditional caching strategies like LRU are built around this assumption.

## Standard LRU cache
A normal LRU cache keeps pages ordered by recency:
- **Head** = most recently used
- **Tail** = least recently used
- New pages are inserted at the head
- Eviction happens at the tail
- Re-accessed pages move back to the head

Typical implementation:
- **Hash map** for `O(1)` lookup by page ID
- **Doubly linked list** for `O(1)` insertion, movement, and eviction

## The problem with sequential scans
A strict LRU works well for normal workloads, but it breaks down during **large sequential scans** such as:
- full table scans
- DB dumps
- `SELECT` queries without a `WHERE` clause

If the scanned table is larger than the cache, each newly read page becomes “most recent,” pushing out useful cached pages. This can wipe out the buffer pool with one-time scan data and hurt performance.

## Midpoint insertion strategy
InnoDB avoids scan pollution by splitting the buffer pool LRU into two logical regions:
- **Young sublist**
- **Old sublist**

The full structure still represents recency overall, but the pool is treated as roughly:
- **5/8 young**
- **3/8 old** by default

### Key idea
Newly read pages are **not** inserted at the MRU head.  
They are inserted at the **head of the old sublist**, which is the “midpoint” of the overall list.

### Promotion rule
- First access: page enters at the midpoint (old sublist)
- Second access: page is promoted to the **head of the young sublist**
- If never accessed again, it ages out quickly from the old sublist

### Eviction rule
Eviction still happens from the **tail of the old sublist**, which is the true least-recently-used end.

## Why midpoint insertion helps
This makes the cache **scan resistant**:
- One-time scan pages do not immediately displace hot working-set pages
- Frequently reused pages migrate into the young list and stay longer
- Sequential scans mostly churn through the old list instead of polluting the young list

## Tuning
InnoDB exposes the old/young split through:

- `innodb_old_blocks_pct`

Default value:
- **37**
- corresponds to roughly **3/8 old** and **5/8 young**

## Useful observability
`SHOW ENGINE INNODB STATUS` can help inspect buffer pool behavior. Useful metrics include:
- pages made young
- eviction rate without access
- cache hit ratio
- read-ahead rate

## Main takeaway
Midpoint insertion is a small change to strict LRU, but it solves a major practical issue: **sequential scans no longer trash the cache as badly**. It preserves hot pages better and keeps InnoDB performant under mixed workloads.

## Tags
#databases #mysql #innodb #caching #lru #system-design #performance