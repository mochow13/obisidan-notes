# Availability in S3
The talk focuses on how S3 ensures availability after introducing read-after-write consistency. It discusses how S3 availability looked like before this consistency guarantee was introduced. And then discusses how things changed later.
## Metada Storage
- S3 has a indexing subsystem that holds metadata for objects
- Index entries are stored in a metadata storage—part of the indexing subsystem
- Index storage has a quorum based architecture
## Caching
- Due to the caching layer for object metadata, S3 didn't have read-after-write consistency before
- Cache didn't have quorum—one cache node could store stale metadata
## Replicated Journal
To provide read-after-write consistency with the same availability guarantee, Amazon introduced Replicated Journal—a chain of nodes where a write flows from one node to another sequentially. If there are two writes A and B, journal nodes store them in-order: `AB`.

![[Screenshot 2026-01-19 at 22.13.48.png]]

All writes also have a sequence number (SN) that helps to establish a watermark on writes. The SNs are monotonically increasing. So for A and B, it will look like `A@1`, `B@2`. And caches retain this sequence number apart from storing the object metadata. Caches can ask this question—*is there any write for this object after this sequence number*.

![[Screenshot 2026-01-19 at 22.59.34.png]]

Replicated journal uses a quorum based config system to get reconfigured if a node in the journal is down.
## Witness
The question that cache asks is served by Witness, a system that stores the key and SN in-memory.

![[Screenshot 2026-01-19 at 23.02.20.png]]

So the SN stored in a cache is compared against the SN stored in Witness for that key. And if it's smaller, the data is fetched from the storage.

%% I have no idea how this is good for latency. The talk says replicated journal forwards the write from one node to another. So it should be slow! %%
# Failure Modes
###### The switch between two AZs failed
Go through the third AZ.

![[Screenshot 2026-01-19 at 23.31.51.png]]
###### Retry amplification
Design retries to reduce impact down the stream.

![[Screenshot 2026-01-19 at 23.34.17.png]]
###### Queuing of requests due to retries

- Client sends a request but it gets queued because the server is overloaded
- Client goes to another server and gets served
- But the request the client initially sent is still in the queue
- If it happens for many requests, the queue is now full of requests for which clients gave up but the server is processing them

![[Screenshot 2026-01-19 at 23.38.16.png]]

There are two approaches:
- Server can process the request queue from the back—some clients now see success
- Backoff and jitter of retries from clients so that clients don't go to another server immediately