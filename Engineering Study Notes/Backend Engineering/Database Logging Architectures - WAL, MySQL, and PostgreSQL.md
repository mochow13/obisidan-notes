---
tags:
  - database
  - architecture
  - system-design
  - backend
created: 2026-06-05
type: conceptual-note
---
The core rule of **Write-Ahead Logging (WAL)**: Database modifications must be written to a persistent, append-only log file on disk *before* they are applied to the actual database pages. This guarantees **Atomicity** and **Durability** ([[ACID]]) while maximizing write performance.

---

## 1. Anatomy of a WAL Record

At a low level, WAL is a binary stream of structured packets. A typical record contains:

* `LSN` (Log Sequence Number): A unique, ever-increasing 64-bit ID.
* `PrevLSN`: Pointer to the previous LSN for the same transaction (creates a reverse-linked list for easy rollback).
* `TxID`: The Transaction ID.
* `Type`: The operation (`START`, `INSERT`, `UPDATE`, `COMMIT`, `ABORT`).
* `Page ID`: The physical file/block location being changed.
* `Redo Data`: The "after-image" used to re-apply changes during **Crash Recovery**.
* `Undo Data`: The "before-image" used to reverse aborted changes.

---

## 2. MySQL: Dual-Log Architecture (Redo Log vs. Binlog)

MySQL stands out because it utilizes **two separate logs** simultaneously due to its pluggable storage engine architecture.

```
                    ┌──────────────────┐
                    │   MySQL Server   │ ───► [ Binlog ] (Logical)
                    └──────────────────┘
                              │
                    ┌──────────────────┐
                    │  InnoDB Engine   │ ───► [ Redo Log ] (Physical)
                    └──────────────────┘
```

### Why MySQL Needs Both
1. **Redo Log (InnoDB Level):** A **physical log** operating as a fixed-size circular buffer. It maps byte-level changes directly to disk blocks. Essential for **Crash Recovery**; it is too volatile for replication.
2. **Binlog (Server Level):** A **logical/row-based log** operating as an append-only archive. It tracks transactional intent (e.g., statements like `INSERT INTO...`). Essential for **Replication** and **Point-in-Time Recovery (PITR)**.

> [!warning] The Two-Phase Commit (2PC) Requirement
> Because MySQL manages two separate log files, it must run an internal **Two-Phase Commit** to prevent divergence (e.g., a transaction writing to the Redo log but missing from the Binlog, causing master/replica desync). 
> 1. InnoDB prepares Redo Log.
> 2. MySQL Server writes to Binlog.
> 3. InnoDB commits Redo Log.

---

## 3. PostgreSQL: Unified WAL Architecture

PostgreSQL uses exactly **ONE unified log** to handle both durability and replication, avoiding the overhead of multi-log synchronization.

```
  ┌──────────────────┐
  │ PostgreSQL Core  │ ───► [ Single WAL Stream ] ───► (Crash Recovery)
  └──────────────────┘               │
                                     ├─► (Physical Streaming Replication)
                                     └─► (Logical Decoding for Change Data Capture)
```

### How Postgres Consolidates Responsibilities
* **Crash Recovery:** Standard physical playback from the latest checkpoint.
* **Replication:** Uses *Physical Streaming Replication*. The primary server streams the raw binary WAL segments over the network, and replicas apply them directly to their own disk pages.
* **Logical Replication:** Handled via *Logical Decoding*. A background process reads the physical WAL stream retroactively and decodes the binary bits into logical events on the fly, eliminating the need for a separate physical binlog file.

---

## 4. Architectural Breakdown

| Feature | MySQL ([[InnoDB]]) | PostgreSQL |
| :--- | :--- | :--- |
| **Log Count** | **Two** (Redo Log + Binlog) | **One** (Unified WAL) |
| **Engine Layer** | Split between Server layer and Engine layer. | Tightly integrated single monolithic core. |
| **Commit Path** | Complex. Requires internal **2PC** coordination. | Lean. Transaction completes when written to the single WAL. |
| **Log Files Structure** | Circular Buffer (Redo) + Append-only files (Binlog). | Continuous 16MB append-only segments (`pg_wal`). |
| **Replication Type** | Logical / Row-based events. | Physical block streaming (or dynamically decoded logical streams). |

---

## 5. Summary Callout

> [!info] Summary Architectural Tradeoff
> * **MySQL** pays a complexity tax at the commit path (2PC coordination) to maintain architectural separation between its server layer and storage engine.
> * **PostgreSQL** leverages its single-engine design to streamline I/O paths, running crash recovery, replication, and archiving out of a single, highly-optimized file stream.

### Related Notes
* [[Database Internals]]
* [[ACID Guarantees]]
* [[Replication Topologies]]