
> [!summary]  
> Kafka’s exactly-once story is built in layers:
> 
> - **Retries + acks** → reliable delivery
>     
> - **Idempotent producer** → retries don’t create duplicate Kafka records
>     
> - **Transactions** → multiple Kafka writes and consumer offsets can commit atomically
>     
> - **`read_committed` consumers** → aborted transactional records stay invisible
>     
> 
> Exactly-once applies **within Kafka’s transactional boundary**, not automatically to external systems like databases, payment APIs, or email services.

---

## 1. Does Kafka guarantee exactly once?

**Yes, but only within specific boundaries.**

Kafka can provide exactly-once semantics for:

```text
Kafka topic
    ↓
consume
    ↓
process
    ↓
Kafka topic
```

using:

- idempotent producers
    
- transactions
    
- transactional offset commits
    
- `read_committed` consumers
    

Kafka does **not** automatically provide exactly-once side effects for:

```text
Kafka → PostgreSQL
Kafka → payment API
Kafka → email service
Kafka → arbitrary HTTP endpoint
```

because Kafka cannot atomically control those external systems.

> [!important]  
> A more accurate definition is:
> 
> **Exactly-once effects within a defined transactional boundary.**

---

# 2. Idempotent Producer

## The problem

Without idempotence:

```text
Producer                     Broker

send message  -------------> stores message
                  <---------- ACK lost

retry message  ------------> stores it again
```

Result:

```text
A
A
```

The producer retried because it could not know whether the first request succeeded.

---

## How Kafka prevents this

Kafka assigns the producer a:

- **Producer ID — PID**
    
- **Producer epoch**
    
- **sequence number per partition**
    

Example:

```text
PID = 42

partition-0:
seq=0
seq=1
seq=2
seq=3
```

The broker tracks the latest accepted sequence number for that producer.

If the same request is retried:

```text
Producer                     Broker

PID=42 seq=17  -----------> append
                 <---------- ACK lost

PID=42 seq=17  -----------> retry
                             already seen seq=17
                 <---------- success
```

Kafka does not append the record twice.

### Mental model

> [!tip]  
> **Idempotent producer = “Retrying the same Kafka write does not create a duplicate.”**

---

## Important limitation

Idempotence protects against **protocol-level retries**, not intentional application sends.

This:

```java
producer.send(record);
producer.send(record);
```

is still two writes.

Kafka will store both.

---

# 3. What happens during a producer GC pause?

A GC pause by itself does not break idempotence.

The Producer ID is not tied to a TCP connection.

Example:

```text
P1

PID = 42
epoch = 3
seq = 17
```

P1 sends:

```text
PID=42 seq=17
```

The broker stores it.

Then:

```text
P1 enters a 30 second GC pause
```

The network connection may disappear.

When P1 wakes up and retries:

```text
PID=42 seq=17
```

the broker recognizes it as the same request and does not append another copy.

---

## Delivery timeout caveat

If the pause lasts longer than:

```text
delivery.timeout.ms
```

the producer may report failure to the application.

You can therefore reach this state:

```text
Application:
"send failed"

Kafka:
"record may already exist"
```

This is a fundamental distributed-systems ambiguity.

Idempotence solves:

```text
duplicate retries
```

It does not always solve:

```text
perfect knowledge of whether a timed-out operation succeeded
```

---

# 4. Producer restart vs GC pause

A temporary pause and a full producer restart are different.

## Same process after pause

```text
P1
PID = 42
```

Still logically the same producer.

---

## New producer instance

After restart:

```text
Old producer:
PID = 42

New producer:
PID = 91
```

For a plain idempotent producer, Kafka sees these as different producer sessions.

Therefore:

```text
P1 sends OrderCreated(123)
P1 dies before application sees ACK

P2 starts
P2 sends OrderCreated(123)
```

Kafka may contain:

```text
OrderCreated(123)   PID=42
OrderCreated(123)   PID=91
```

Plain idempotence does not deduplicate arbitrary application-level retries across producer instances.

---

# 5. Zombie Producers and Fencing

Consider:

```text
P1 running
    ↓
long GC pause
    ↓
orchestrator thinks P1 is dead
    ↓
P2 starts
    ↓
P1 wakes up
```

Without stronger coordination:

```text
P1 → Kafka
P2 → Kafka
```

Both might produce concurrently.

Kafka transactions solve this with:

```text
transactional.id
```

Example:

```text
transactional.id = orders-worker-7
```

Initially:

```text
P1

PID = 42
epoch = 3
```

Replacement producer starts with the same transactional identity:

```text
P2

PID = 42
epoch = 4
```

P1 wakes up and sends:

```text
PID = 42
epoch = 3
```

Kafka sees:

```text
current epoch = 4
incoming epoch = 3
```

and fences P1.

```text
3 < 4
=> stale producer
=> reject
```

> [!important]  
> The **epoch** distinguishes generations of the same logical producer.

---

# 6. Why was PID still 42?

With a plain restarted idempotent producer:

```text
P1 → PID 42
P2 → PID 91
```

With the same `transactional.id`:

```text
P1 → PID 42, epoch 3
P2 → PID 42, epoch 4
```

The logical transactional producer identity is preserved while the epoch advances.

That epoch increment enables producer fencing.

---

# 7. Kafka Transactions

Kafka transactions extend idempotence from:

```text
"Don't duplicate this write"
```

to:

```text
"Commit this group of Kafka operations atomically"
```

---

## Producer-only transaction

A transaction does **not** require a consumer.

Example:

```java
producer.beginTransaction();

producer.send(orderRecord);
producer.send(inventoryRecord);
producer.send(paymentRecord);

producer.commitTransaction();
```

These writes can span:

```text
orders-0
inventory-4
payments-2
```

The transaction eventually becomes either:

```text
COMMIT
```

or:

```text
ABORT
```

---

# 8. The most important use case: Consume → Process → Produce

Consider:

```text
orders topic
    ↓
consumer
    ↓
process
    ↓
payments topic
```

Without transactions:

```text
1. consume order offset 42
2. produce PaymentRequested
3. crash
4. offset 42 was never committed
5. restart
6. consume offset 42 again
7. produce PaymentRequested again
```

Duplicate output.

---

## With a Kafka transaction

Conceptually:

```java
producer.beginTransaction();

consume(order);

producer.send(paymentRequested);

producer.sendOffsetsToTransaction(
    offsets,
    consumer.groupMetadata()
);

producer.commitTransaction();
```

Kafka atomically commits:

```text
output records
+
input consumer offsets
```

So:

```text
COMMIT
= output visible
+ offset advanced
```

or:

```text
ABORT
= output hidden
+ offset not advanced
```

If the application crashes, the input may be processed again, but the previous aborted output remains invisible to `read_committed` consumers.

---

# 9. Transaction Internals

Kafka transactions involve three main actors:

```text
Producer
Transaction Coordinator
Partition Leaders
```

Suppose transaction `T1` writes to:

```text
orders-0
orders-3
payments-2
audit-5
```

These may live across several brokers.

```text
Broker A          Broker B          Broker C

orders-0          orders-3          payments-2
audit-5
```

---

# 10. Transaction Coordinator

Kafka maps:

```text
transactional.id
```

to a partition of the internal topic:

```text
__transaction_state
```

The leader of that partition acts as the:

```text
Transaction Coordinator
```

The coordinator tracks metadata such as:

```text
transactional.id
PID
epoch
state
participating partitions
```

Example:

```text
transactional.id = payment-worker-7
PID = 42
epoch = 7

state = ONGOING

participants:
  orders-0
  orders-3
  payments-2
  audit-5
```

Important:

> [!note]  
> The coordinator does **not** carry the transaction’s actual records.
> 
> It is primarily control-plane metadata.

---

# 11. Transaction data goes directly to partitions

The producer sends records directly to partition leaders:

```text
                     +--> Broker A → orders-0
                     |
Producer ------------+--> Broker B → orders-3
                     |
                     +--> Broker C → payments-2
                     |
                     +--> Broker A → audit-5
```

Not:

```text
Producer
   ↓
Transaction Coordinator
   ↓
all records
```

This avoids turning the transaction coordinator into a data bottleneck.

---

# 12. Participating partitions are registered

When a partition joins the transaction, Kafka tracks it.

Conceptually:

```text
AddPartitionsToTxn

orders-0
orders-3
payments-2
audit-5
```

The coordinator therefore knows every partition that must later receive a commit or abort marker.

---

# 13. Transactional records are written immediately

Kafka does not keep transaction records in memory until commit.

They are physically appended to the normal Kafka log.

Example:

```text
orders-0

100 X
101 A [transactional]
102 Z
```

and:

```text
payments-2

900 C [transactional]
```

The unresolved question is whether those records will eventually be:

```text
COMMITTED
```

or:

```text
ABORTED
```

---

# 14. `commitTransaction()`

When the producer calls:

```java
producer.commitTransaction();
```

it sends an operation conceptually equivalent to:

```text
EndTxn(COMMIT)
```

to the Transaction Coordinator.

---

# 15. Kafka first records the decision durably

The coordinator first writes:

```text
PREPARE_COMMIT
```

into:

```text
__transaction_state
```

Example:

```text
T42

state = PREPARE_COMMIT

participants:
  orders-0
  orders-3
  payments-2
  audit-5
```

This is crucial.

If the coordinator crashes now, the replacement coordinator can recover:

```text
T42 = PREPARE_COMMIT
```

and knows:

```text
"Finish committing this transaction."
```

It does not have to guess.

---

# 16. Commit markers

The coordinator then sends commit markers to every partition involved.

Conceptually:

```text
Coordinator
     |
     +--> orders-0
     +--> orders-3
     +--> payments-2
     +--> audit-5
```

Each partition appends a special control record:

```text
orders-0

100 X
101 A [transactional]
102 COMMIT PID=42
```

Another partition:

```text
payments-2

900 C [transactional]
901 COMMIT PID=42
```

These are Kafka **control records**.

Applications do not receive them as normal messages.

---

# 17. Abort works similarly

Instead of:

```text
COMMIT
```

Kafka may append:

```text
ABORT
```

Example:

```text
100 A [transactional]
101 B [transactional]
102 ABORT
```

The records still physically exist.

Kafka does **not** delete or roll them back.

For a `read_committed` consumer:

```text
A and B effectively never happened
```

---

# 18. `read_committed` vs `read_uncommitted`

## `read_uncommitted`

May read records even from currently open or eventually aborted transactions.

```text
A [open tx]
B [open tx]
X [normal]
```

Consumer may see:

```text
A
B
X
```

---

## `read_committed`

Only exposes records whose transactional status is stable.

This is where Kafka’s:

```text
Last Stable Offset
```

becomes important.

---

# 19. Open transaction + later non-transactional messages

Suppose:

```text
100 A [transaction T1]
101 B [transaction T1]
102 X [normal]
103 Y [normal]
```

`T1` is still open.

Other producers are completely free to continue writing:

```text
102 X
103 Y
104 Z
```

An open transaction does **not block producers**.

However, for a:

```text
read_committed
```

consumer, the open transaction can temporarily prevent later records from becoming visible.

Why?

Kafka preserves partition ordering.

It cannot expose:

```text
102 X
103 Y
```

while hiding:

```text
100 A
101 B
```

and still present a clean sequential view.

So:

```text
open transaction
      ↓
later records can be appended
      ↓
but read_committed visibility may stall
```

This is effectively **head-of-line blocking** for `read_committed` consumers.

---

# 20. Last Stable Offset

The **Last Stable Offset — LSO** is the boundary up to which a `read_committed` consumer can safely read.

Example:

```text
98
99
100 A [T1 open]
101 B
102 X
103 Y
```

If the earliest unresolved transaction starts at `100`, records beyond that point may not yet be exposed to `read_committed` consumers.

When `T1` resolves:

```text
COMMIT
```

or:

```text
ABORT
```

the stable boundary can advance.

---

# 21. What if only some partitions receive the commit marker?

Suppose Kafka already decided:

```text
PREPARE_COMMIT
```

but then:

```text
orders-0    ✓
orders-3    ✓
payments-2  ✗ broker unavailable
audit-5     ✓
```

Kafka does **not** change the transaction to an abort.

The decision is already durable.

The coordinator keeps trying to finish:

```text
payments-2 → retry commit marker
```

If leadership moves:

```text
Broker C dies
Broker D becomes payments-2 leader
```

the coordinator sends the marker to Broker D.

---

# 22. What if the Transaction Coordinator dies?

The transaction state lives in:

```text
__transaction_state
```

which is itself replicated.

Suppose:

```text
Broker B = coordinator
```

and crashes.

Another broker becomes leader for the relevant `__transaction_state` partition.

It reconstructs:

```text
transaction T42
state = PREPARE_COMMIT
participants = [...]
```

and continues the transaction.

Kafka therefore recovers transaction coordination from a replicated log rather than relying on coordinator memory.

---

# 23. Transaction state machine

Simplified commit path:

```text
EMPTY
  ↓
ONGOING
  ↓
PREPARE_COMMIT
  ↓
COMPLETE_COMMIT
```

Abort path:

```text
ONGOING
  ↓
PREPARE_ABORT
  ↓
COMPLETE_ABORT
```

---

# 24. Consumer offsets are transactional too

For consume-process-produce, Kafka can include the consumer offset update in the same transaction.

Conceptually:

```text
Transaction T1
   |
   +-- output-topic-2
   +-- audit-topic-1
   +-- __consumer_offsets-17
```

So:

```text
produce output
+
advance consumer offset
```

becomes one atomic Kafka transaction.

This is the essential mechanism behind Kafka exactly-once processing.

---

# 25. Multi-partition atomicity does NOT mean global instantaneous visibility

Suppose commit markers arrive at:

```text
orders-0      t=10 ms
orders-3      t=20 ms
payments-2    t=70 ms
audit-5       t=90 ms
```

Kafka does not guarantee that every consumer on every partition observes the entire transaction at the exact same wall-clock instant.

The guarantee is:

```text
eventual transaction outcome
=
COMMIT everything
or
ABORT everything
```

not:

```text
every partition becomes visible simultaneously
```

This is an important difference from imagining Kafka as a globally locked distributed database.

---

# 26. Kafka transactions do not cover arbitrary external systems

This:

```text
Kafka input
    ↓
process
    ↓
Kafka output
```

can be transactional.

This:

```text
Kafka input
    ↓
charge credit card
    ↓
Kafka output
```

cannot be made fully atomic by Kafka alone.

Example failure:

```text
1. charge card succeeds
2. service crashes
3. Kafka transaction aborts
4. input is processed again
5. card may be charged twice
```

Kafka cannot roll back the payment processor.

Common solutions include:

- idempotency keys
    
- transactional outbox
    
- inbox/deduplication tables
    
- external system idempotence
    

---

# 27. Relationship Between the Concepts

```text
acks + retries
      ↓
reliable delivery

idempotent producer
      ↓
safe retries
      ↓
no duplicate Kafka writes caused by retries

producer epoch
      ↓
identify stale generations

transactional.id
      ↓
stable logical transactional producer identity

producer fencing
      ↓
prevent zombie producers

Kafka transaction
      ↓
atomically group multiple Kafka operations

sendOffsetsToTransaction()
      ↓
atomically bind output + consumed offsets

read_committed
      ↓
hide aborted/unresolved transactional records

Together
      ↓
Kafka exactly-once processing
```

---

# 28. Version History

Kafka transactions and idempotent producers were introduced in:

```text
Apache Kafka 0.11.0.0
```

Released:

```text
June 28, 2017
```

The feature came from:

```text
KIP-98
Exactly Once Delivery and Transactional Messaging
```

As of September 2026, Kafka transactions have existed for roughly:

```text
9 years
```

---

# 29. Key Mental Models

> [!tip] Idempotence  
> **“Retrying the same Kafka write should not append it twice.”**

> [!tip] Transactions  
> **“This group of Kafka changes should either commit together or abort together.”**

> [!tip] Producer fencing  
> **“An old producer generation must not continue writing after its replacement takes over.”**

> [!tip] `read_committed`  
> **“Only show me transactional data once Kafka knows its final outcome.”**

> [!tip] Exactly-once  
> **“Exactly-once effects within Kafka’s transactional boundary.”**

---

# 30. Cheat Sheet

|Mechanism|Solves|
|---|---|
|`acks`|How strongly Kafka confirms persistence|
|retries|Transient send failures|
|idempotent producer|Duplicate writes caused by retries|
|PID|Producer protocol identity|
|sequence number|Detect duplicate/reordered writes per partition|
|producer epoch|Distinguish producer generations|
|`transactional.id`|Stable logical transactional producer identity|
|fencing|Stops stale/zombie producers|
|Kafka transaction|Atomic Kafka writes across partitions/topics|
|`sendOffsetsToTransaction()`|Atomic output + consumer offset commit|
|`read_committed`|Hides aborted/unresolved transactional data|
|LSO|Controls stable read visibility|
|`__transaction_state`|Stores coordinator transaction metadata|
|commit/abort markers|Record transaction outcome in participating partitions|

---

# 31. Final Architecture

```text
                         Producer
                            |
                 transactional.id
                            |
                            v
                  Transaction Coordinator
                  (__transaction_state)
                            |
                  tracks participants
                            |
       +--------------------+--------------------+
       |                    |                    |
       v                    v                    v

    Broker A             Broker B             Broker C

    orders-0             orders-3             payments-2
    audit-5

       ^                    ^                    ^
       |                    |                    |
       +--------- transactional records --------+
                            |
                            |
                     commitTransaction()
                            |
                            v
                    PREPARE_COMMIT
                            |
             +--------------+--------------+
             |              |              |
             v              v              v

        COMMIT marker   COMMIT marker   COMMIT marker

             \              |              /
              +-------------+-------------+
                            |
                            v
                   COMPLETE_COMMIT
```

---

## Bottom Line

Kafka’s exactly-once implementation is not based on locking all partitions or buffering an entire distributed transaction centrally.

Instead, Kafka combines:

```text
distributed append-only logs
+
idempotent producer sequencing
+
transaction coordinator
+
durable transaction state
+
per-partition commit/abort markers
+
consumer visibility rules
```

This lets Kafka provide efficient atomic transactions across many topics and partitions while keeping the actual data distributed across normal Kafka partition leaders.