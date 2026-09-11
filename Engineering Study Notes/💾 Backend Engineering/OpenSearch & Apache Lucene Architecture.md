## 1. Apache Lucene: Architecture & Core Mechanics

Apache Lucene is an open-source, high-performance Java search library. It operates fundamentally on an **Inverted Index** structure backed by an **LSM (Log-Structured Merge-tree)** engine design.

### 1.1 Inverted Index vs. Forward Index
* **Forward Index (RDBMS style):** Maps `Document ID -> Terms/Fields`. Fast for reading full records, slow for finding records containing specific terms.
* **Inverted Index (Lucene style):** Maps `Term -> Document IDs + Frequencies + Offsets`. Allows sub-millisecond term lookups across millions of records.

```
[ Raw Document ] ──> [ Analyzer (Tokenizer + Filters) ] ──> [ Inverted Index ]
Doc 1: "OpenSearch uses Lucene"  ==>  lucene     -> [Doc 1]
Doc 2: "Lucene searches fast"    ==>  opensearch -> [Doc 1]
                                      searches   -> [Doc 2]
```

### 1.2 Text Analysis Pipeline
Before indexing, text fields pass through an **Analyzer**:
1. **Character Filter:** Strips HTML tags or unwanted symbols.
2. **Tokenizer:** Breaks text into individual tokens (words).
3. **Token Filter:** Normalizes tokens (lowercasing, stemming, removing stop words).

### 1.3 Key Lucene Data Structures
A single Lucene index segment contains multiple sub-indices optimized for different access patterns:

* **Term Dictionary (`.tim`) & Term Index (`.tip`):**
  * Unique terms are stored alphabetically in `.tim`.
  * Lucene builds an in-memory **Finite State Transducer (FST)** prefix tree stored in `.tip`. This allows memory lookups to find exact disk offsets in `.tim` without random disk I/O.
* **Postings Lists (`.doc`, `.pos`):**
  * Sorted arrays of Document IDs containing the term.
  * Encoded using **Delta Encoding** and **Frame of Reference (FOR)** bit-packing for maximum RAM/disk compression.
* **BKD Trees (`.kdm`, `.kdi`):**
  * A multi-dimensional point tree structure used for numeric, spatial, and date range queries (`@timestamp >= now-2h`), far outperforming string-based inverted indexes for range checks.
* **Doc Values (`.dvd`, `.dvm`):**
  * A columnar storage format (`Document ID -> Term Value`) stored sequentially on disk. Fast for aggregations, sorting, and field scripts.
* **Vector Index (`.vec` / HNSW):**
  * Hierarchical Navigable Small World (HNSW) graphs used for low-latency k-NN vector search embeddings.

### 1.4 Lucene as an LSM Engine
Lucene is built around **immutable segments**, making it an LSM-tree variant:

```
[ Ingest ] ──> [ IndexWriter RAM Buffer ] ──(Flush)──> [ Immutable Disk Segment 1 ]
                                                    ──> [ Immutable Disk Segment 2 ]
                                                             │
                                                    (Background Segment Merge)
                                                             │
                                                             ▼
                                                        [ Merged Segment 3 ]
```

* **MemTable Equivalent:** `IndexWriter` RAM Buffer buffers writes in memory.
* **SSTable Equivalent:** **Lucene Segments** are written as contiguous, 100% immutable files on disk.
* **Tombstones (`.del`):** Deletions do not modify existing segment files; they flip a bit in a deletion bitset.
* **Segment Merging:** A background daemon periodically merges smaller segments into larger ones, physically purging deleted records during compaction.

---

## 2. OpenSearch Architecture & Lucene Integration

OpenSearch is a distributed system that manages and orchestrates thousands of Lucene instances across cluster nodes.

```
┌────────────────────────────────────────────────────────────────────────┐
│                          OPENSEARCH CLUSTER                            │
│                                                                        │
│ ┌────────────────────────────────┐    ┌──────────────────────────────┐ │
│ │     Cluster Manager Node       │    │        Coordinating Node     │ │
│ │ (Cluster state, shard mapping) │    │  (Query routing, gathering)  │ │
│ └────────────────────────────────┘    └──────────────────────────────┘ │
│                                                                        │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │                           DATA NODES                               │ │
│ │ ┌────────────────────────────────────────────────────────────────┐ │ │
│ │ │                       Index: "logs-2026"                       │ │ │
│ │ │  ┌─────────────────────────────┐  ┌──────────────────────────┐ │ │ │
│ │ │  │       Primary Shard 0        │  │      Replica Shard 1     │ │ │ │
│ │ │  │ ┌─────────────────────────┐ │  │ ┌──────────────────────┐ │ │ │ │
│ │ │  │ │   Lucene Index Engine   │ │  │ │  Lucene Index Engine │ │ │ │ │
│ │ │  │ │  (Seg 1) (Seg 2) (Seg 3)│ │  │ │  (Seg 1) (Seg 2)     │ │ │ │ │
│ │ │  │ └─────────────────────────┘ │  │ └──────────────────────┘ │ │ │ │
│ │ │  └─────────────────────────────┘  └──────────────────────────┘ │ │ │
│ │ └────────────────────────────────────────────────────────────────┘ │ │
│ └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Cluster Node Roles
* **Cluster Manager:** Maintains the active state of the cluster, index metadata, and shard allocation.
* **Data Nodes:** Hold primary and replica shards; perform document indexing and search query execution.
* **Ingest Nodes:** Execute pre-processing pipelines (parsing JSON, grok patterns, enrichments) prior to indexing.
* **Coordinating Nodes:** Act as smart load balancers that scatter requests across relevant data nodes and gather aggregated results.
* **Search Nodes:** Dedicated compute nodes designed specifically for search queries without storing primary write replicas.

### 2.2 Relationship: Index -> Shard -> Lucene
* An **Index** in OpenSearch is a logical namespace.
* An Index is split into one or more physical **Shards** for horizontal scaling.
* Each **Shard** is an independent, fully functioning **Apache Lucene index instance**.

### 2.3 Replication Modes
* **Document Replication (Traditional):** Ingestion requests are processed on the Primary shard, which then forwards raw JSON documents to Replica shards, requiring each replica to rerun Lucene analysis and indexing independently.
* **Segment Replication (Modern):** The Primary shard handles indexing and builds compiled Lucene segments directly. It then ships compiled segment files across the network (or via Object Storage) to Replicas, drastically cutting replica CPU utilization.
* **Remote-Backed Storage:** Offloads primary and replica Lucene segments to durable cloud object storage (e.g., AWS S3, Google Cloud Storage, MinIO), decoupling compute from persistent storage.

---

## 3. Lifecycle of a Request in OpenSearch

### 3.1 The Write Path (Document Indexing)

```
[ Client ] ──(1. Index Request)──> [ Coordinating Node ]
                                            │
                                  (2. Hash ID to Shard)
                                            │
                                            ▼
                                  [ Primary Data Node ]
                                     ├── (3a. Write to Translog)
                                     ├── (3b. Buffer in RAM)
                                     └── (4. Forward to Replicas)
                                            │
                                            ▼
                                   [ Replica Data Nodes ]
```

1. **Client Request:** Client sends a JSON document write request.
2. **Routing:** The Coordinating Node hashes the document ID (`hash(_id) % primary_shards`) to find the target Primary shard.
3. **Primary Processing:**
   * Writes the operation to the **Translog** (Write-Ahead Log) on disk for crash durability.
   * Ingests the document into the Lucene `IndexWriter` RAM buffer.
4. **Replication:**
   * **Document Mode:** Raw document is forwarded to Replica shards.
   * **Segment Mode:** Compiled segments are pushed to Replicas or uploaded to Remote Store.
5. **Acknowledge:** Primary returns success once the write consistency requirement (`wait_for_active_shards`) is satisfied.

### 3.2 The Read Path (Search Query)

Search operates via a two-phase process: **Query Phase (Scatter-Gather)** and **Fetch Phase**.

```
[ Client ] ───(1. POST /_search)───> [ Coordinating Node ]
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │ (Scatter Query Phase)   │                         │
                    ▼                         ▼                         ▼
            [ Data Node 1 ]           [ Data Node 2 ]           [ Data Node 3 ]
             (Lucene Match)            (Lucene Match)            (Lucene Match)
                    │                         │                         │
                    └─────────────────────────┼─────────────────────────┘
                                              │
                                   (2. Gather Top N Doc IDs)
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │ (Fetch Phase)           │                         │
                    ▼                         ▼                         ▼
            [ Fetch Raw JSON ]        [ Fetch Raw JSON ]        [ Fetch Raw JSON ]
                    │                         │                         │
                    └─────────────────────────┼─────────────────────────┘
                                              │
                                    (3. Return JSON Hits)
                                              │
                                              ▼
                                          [ Client ]
```

#### Phase 1: The Query Phase (Scatter)
1. **Routing:** Coordinating Node receives query, identifies relevant index shards, and selects one copy (primary or replica) of each shard.
2. **Scatter:** Broadcasts a lightweight query request to data nodes.
3. **Lucene Local Execution (on each Shard):**
   * **Filters:** BKD tree scans ranges (`@timestamp`), Term FST retrieves keyword posting lists.
   * **Match Phrase:** Intersects word position lists (`.pos`) to enforce exact word ordering.
   * **Scoring/Sorting:** Reads values directly from Doc Values or calculates BM25 scores using Block-Max WAND optimizations.
4. **Local Response:** Each shard returns only matching **Doc IDs** and **Sort/Score Values** (e.g., top 10 local IDs) to the Coordinating Node.

#### Phase 2: The Fetch Phase (Gather)
1. **Global Merge:** Coordinating Node runs a priority queue merge sort across all shard responses to find the global top N documents.
2. **Fetch Request:** Makes targeted RPC requests to the exact shards hosting the winning Doc IDs to pull their full raw source payloads (`_source`).
3. **Client Response:** Combines the JSON payloads into the final API output.

---

## 4. Managing Large-Scale OpenSearch & Operational Challenges

### 4.1 System Guardrails & Limits
To prevent Out-Of-Memory (OOM) crashes, OpenSearch enforces strict limits:

* **`index.max_result_window` (10,000 docs default):** Blocks deep pagination using `from + size > 10000`. Deep pagination forces coordinating nodes to hold quadratic priority queues in memory.
* **`track_total_hits` (10,000 docs default):** Terminates accurate hit counting early once 10,000 matches are evaluated.
* **Max Clause Count (1024 default):** Caps boolean clauses / expanded wildcard terms to prevent opening excessive posting lists in Lucene.
* **Circuit Breakers:**
  * **Parent Breaker (95% Heap):** Aborts memory-intensive queries if overall cluster heap usage exceeds safety limits.
  * **Request Breaker (60% Heap):** Cancels individual requests creating large intermediate memory structures.

### 4.2 Hot-Warm-Cold Tiering
Optimizes infrastructure costs by matching hardware profiles with log data age:

```
[ Ingestion ] ──> [ HOT Tier ] ──────────> [ WARM Tier ] ──────────> [ COLD Tier ]
               • NVMe SSDs               • HDD / Dense Storage     • Object Store (S3)
               • High CPU/RAM            • Lower Compute           • Searchable Snapshots
               • Active Ingest           • Force-merged (1 seg)   • Archival
```

* **Hot Tier:** Handles active ingestion and dashboard queries. Requires high CPU and fast NVMe storage.
* **Warm Tier:** Read-only data. Indices are **force-merged down to 1 segment per shard** to reclaim space and release term dictionary overhead.
* **Cold/Frozen Tier:** Decoupled storage using object storage (S3/GCS). Uses Searchable Snapshots or Remote Store to read data on demand.

### 4.3 Disk Watermarks & Emergency States
OpenSearch uses disk watermarks to preserve stability as storage fills:

```
0% ───────────────── 85% ────────────── 90% ────────────── 95% ───────── 100%
                      │                  │                  │
                Low Watermark      High Watermark     Flood Stage
               (No new shards)  (Relocate shards)  (READ-ONLY BLOCK)
```

1. **Low Watermark (85% default):** Stops allocating new shards to the node.
2. **High Watermark (90% default):** Attempts to relocate existing shards away to other nodes under 85%.
3. **Flood Stage Watermark (95% default):** Enforces a global write lock (`index.blocks.read_only_allow_delete: true`) on all indices sitting on the affected node.
   * **Note:** The cluster **will not auto-clear** this block after space is freed. It must be manually cleared via:
     `PUT */_settings { "index.blocks.read_only_allow_delete": null }`.

### 4.4 The Hot-Node Disk Full Risk
If write throughput exceeds offload throughput to Warm/Remote tiers:
* Force merges fail due to lack of temporary scratch space (requires ~2x space of the merged segments).
* Unmerged Lucene segments accumulate, increasing file handles and JVM heap pressure.
* Cluster breaches the 95% threshold, blocking upstream ingestion pipelines (e.g., Logstash/FluentBit buffers fill, leading to dropped logs).

---

## 5. Key Architecture Reference Summary

| Feature / Concept | OpenSearch / Lucene Mechanism | Best Practice / Solution |
| :--- | :--- | :--- |
| **Deep Pagination** | `from` + `size` breaks at 10k | Use `search_after` with PIT (Point In Time) or Scroll API |
| **Numeric Range Search** | BKD Trees (`.kdm`, `.kdi`) | Map timestamps and numeric values to `date`, `long`, `integer` |
| **Aggregations & Sorting** | Columnar Doc Values (`.dvd`) | Enable `doc_values: true` (default) on non-analyzed fields |
| **Cluster Memory Protection** | JVM Circuit Breakers | Set heap size to max 32GB (Compressed OOPs limit) |
| **Write Throughput Boost** | Segment Replication & Translog Async | Use `replication.type: SEGMENT` with Remote-Backed Storage |