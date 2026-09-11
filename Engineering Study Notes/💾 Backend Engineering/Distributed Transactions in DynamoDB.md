Based on: https://www.usenix.org/system/files/atc23-idziorek.pdf
## Features of DDB Transactions
#### Single Request
In traditional transactional database like PostgreSQL, transaction starts with `BEGIN` and ends with `COMMIT` and in between, there can be a long time. Long running transactions are not suitable in multi-tenant database like DDB. Rather, transactions are comprised of a set of operations that succeed or fail without blocking.
#### Transaction Coordinator
Transactions rely on a transaction coordinator while non-transaction operations bypass the coordination. This coordinator uses 2-phase protocol.
#### Updates in Place
In DDB, transactions update items in-place. While many databases use multi-version concurrency control (MVCC), DDB doesn't support this. The implication is read-only and write-only transactions might conflict. The reason for not using MVCC are major changes in storage servers, complexities around version-retention policies, and additional storage costs.
#### Optimistic Concurrency Control (OCC)
DDB avoids locking by implementing optimistic concurrency control.
#### Serial Order by Timestamps
Each transaction has a timestamp associated with it. As long as transactions appear to execute in their assigned time, serialisability is achieved.
# Transaction APIs
- `TransactGetItems` - Retrieves a set of items from a consistent snapshot. If there is a conflicting operation running, returns failure.
- `TransactWriteItems` - Synchronously write or update one or more items across one or more tables—could be optionally executed based on some preconditions.
- `CheckItem` - Checks that the latest value of an item matches the condition.
## Example

```java
// Check if customer exists
Check checkItem = new Check()
    .withTableName("Customers")
    .withKey(" CustomerUniqueId ")
    .withConditionExpression(" attribute_exists (CustomerId)");

// Update status of the item in Products
Update updateItem = new Update()
    .withTableName("Products")
    .withKey(" BookUniqueId ")
    .withConditionExpression(" expected_status " = "IN_STOCK")
    .withUpdateExpression("SET ProductStatus = SOLD");

// Insert the order item in the orders table
Put putItem = new Put()
    .withTableName("Orders")
    .withItem("{"
        OrderId ": " OrderUniqueId ", "
        ProductId " :" BookUniqueId ", "
        CustomerId ": " CustomerUniqueId ", "
        OrderStatus": "CONFIRMED", "OrderCost": 100
    }")
	.withConditionExpression(" attribute_not_exists (OrderId)")

TransactWriteItemsRequest twiReq = new TransactWriteItemsRequest()
    .withTransactItems([checkItem, putItem, updateItem]);

// Single transaction call to DynamoDB
DynamoDBclient.transactWriteItems(twiReq);
```
# Transaction Execution
## Routing

![[Screenshot 2026-01-10 at 20.07.57.png]]

- Each transaction lands on Request Router, just like all the other requests to DDB
- Request Router authenticates the request and figures out which Transaction Coordinator to send the transaction to from Metadata System
- Transaction Coordinator (TC) breaks the transaction into item-level operations and runs a distributed protocol in which the storage nodes for these items participate.
## Ordering
- Each TC assigns a timestamp to the incoming transactions
- As long as transactions are executed in the timestamp order, serialisability can be achieved
- But of course, there can be clock skew since there are many TCs to handle the scale
- TCs use AWS time-sync service to synchronise local time
- Even if the clock is accurate, there can be transactions coming out of order due to slowness of some message or so
- When a conflict rises, DDB doesn't wait or tries to merge versions (there is no versions anyway)—it aborts the transaction with `TransactionCanceledException`
## Write Transaction Protocol
DDB uses 2-phase protocol where the coordinator first asks every storage node to *prepare* the items they are responsible for in the first phase. If every storage node accepts the request, TC then commits the transaction and asks all the storage nodes to perform the write.

- **Timestamp on item**: To implement timestamp ordering, each item in DDB has a timestamp attached. This field is updated during `TransactWriteItems`.
- **Per-transaction metadata**: Storage nodes persist per-transaction metadata (including transaction timestamp, identifier) which is attached to each item that are part of the transaction.
- **Accepting a transaction**: Storage nodes accept a transaction if all the following are true for every local item that are part of the transaction:
	- All preconditions on the item are met (using `CheckItem`)
	- No system constraint is violated—for example, exceeding the maximum item size
	- Transactions timestamp > item's last written timestamp
	- The set of previously accepted in-flight transactions to write the same item is empty
- **Updating timestamps**: To commit the transaction, each participating storage node updates the relevant items and records the timestamp of the transaction as the last write timestamp for those items. Same is also done for items that were checked as a part of the preconditioning but not updated.
- **Handling deleted items**: If an item is deleted, there is no longer a last write timestamp. DDB doesn't have *tombstone* deletion. It maintains a per-partition `max_delete_timestamp`.

```python
  if transaction_timestamp > max_delete_timestamp:
	  max_delete_timestamp = transaction_timestamp
  ```

- **Accepting transaction non-existent items**: When a storage node receives a prepare message for a non-existent item, it compares the above `max_delete_timestamp` to decide whether to accept or reject the message.

Following code shows how storage nodes handle a prepare request:

```python
def process_prepare(input_data):
    # Retrieve the item from storage based on the input
    item = read_item(input_data)
    
    if item is not None:
        # Check if item meets all criteria for a successful transaction prepare
        if (evaluate_conditions_on_item(item, input_data.conditions) and 
            evaluate_system_restrictions(item, input_data) and 
            item.timestamp < input_data.timestamp and 
            item.ongoing_transactions is None):
            
            # Lock the item for the current transaction
            item.ongoing_transaction = input_data.transaction_id
            return "SUCCESS"
        else:
            return "FAILED"
            
    else:
        # Item does not exist; attempt to prepare a new item entry
        item = new_item(input_data.item)
        
        if (evaluate_conditions_on_item(input_data.conditions) and 
            evaluate_system_restrictions(input_data) and 
            partition.max_delete_timestamp < input_data.timestamp):
            
            # Associate the new item placeholder with the transaction
            item.ongoing_transaction = input_data.transaction_id
            return "SUCCESS"
        
    return "FAILED"
```

## Read Transaction Protocol
Read transactions are also executed in 2-phase using the `TransactGetItem` API. In the first phase, coordinator reads all the items along with Log Sequence Number (LSN) for each item.

> *Log Sequence Number (LSN) is a monotonically increasing number assigned to an item every time it is successfully written or updated. It serves as a unique version for that specific state of the item.*

In the second phase, coordinator reads the items again. If no LSN for any item has changed, the transaction succeeds. Otherwise DDB throws an exception. DDB also avoids updating the last timestamp for items while reading to avoid making each read a write operation!

While reading an item in a read transaction, if there is an ongoing write transaction on that item, DDB also rejects the read transaction.

By reading in 2-phase, read transaction avoids changes to an item that is part of the read transaction. If a write transaction updates an item while the read transaction is ongoing, it is easily spotted and the transaction fails.

But, **why not send back the items read in the first phase directly?**
## The "Split Transaction" Problem
Imagine you are performing a `TransactGetItems` for two items: **Account A** and **Account B**. You want to see their balances.

1. **Phase 1 starts:** The Coordinator asks for the data of Account A. The storage node responds: `no writes pending; balance: $100, lsn: 5`
2. **The "race" happens:** In the millisecond _after_ the coordinator reads Account A but _before_ it reads Account B, a separate `TransactWriteItems` occurs. This transaction moves `$50` from Account A to Account B.
	- Account A is now `$50 (LSN 6)`
	- Account B is now `$150 (LSN 6)`
3. **Phase 1 continues:** The Coordinator now asks for the data of Account B. The storage node says `no writes pending; balance: $150, lsn: 6

Now, if the coordinator sent you that data immediately, you would see:

```
Account A: $100
Account B: $150
Total: $250 <-- $50 from thin air!
```

Even though no transaction was ongoing, at the exact moment each individual item was read, the **set** of items you received is mathematically impossible. It does not represent a single point in time.
# Recovering Coordinator Failures
The most complex failure surface is the transaction coordinator. To ensure atomicity of transactions and failure recovery, each coordinator has a ledger. A ledger is a DDB table where transactions are stored by their unique transaction id.

- Recovery manager processes periodically checks for stalled transaction in the ledger
- If there are stalled transactions, they are assigned to a new coordinator
- In case a coordinator is incorrectly determined to have failed a transaction, duplicate transaction will be attempted by the both old and new coordinator
- If storage nodes receive the same transaction (probably identified by the id), they reject the second one which means duplicate attempts are safe
- Apart from periodic scans, recovery managers can also be invoked by storage nodes if they see an item has a pending transaction for more than a threshold duration
# Handling Timestamp Ordering

> *Reads to individual items can always be performed successfully even if there is a prepared transaction that is attempting to write that item.*

- For a `get` request that is not a part of a transaction, TC is bypassed and storage node immediately returns the response—even if there is a transaction prepared for that item. Implicitly, this `get` request receives a timestamp ordering between the last write timestamp of the item and the prepared transaction's committed timestamp, hence serialising the request.

%% I don't know how the timestamp for the read request is decided though. We know the last write timestamp. But for the prepared transaction, we don't know the committed transaction since it's in prepared stage. How is the serialised timestamp decided for the get request? %%

> *Writes to individual items can be performed immediately and serialized before any prepared transactions in many cases*.

- Similarly, storage nodes directly receives non-transactional `put` requests and the primary storage node assigns it a write timestamp that is earlier than any transactions in the prepared stage. So this non-transactional writes can jump ahead of the transactional write since the prepared transaction has not been committed.
- This approach of jumping ahead doesn't always work. If a prepared transaction has been conditioned on an item but the non-transactional write violates the condition by changing it, then jumping that write ahead will break the invariant. So in such a case, the write might be rejected.

> *Writes to individual items can be performed immediately or delayed and serialised after any prepared transactions in other cases.*

- Non-transactional writes don't always have to be rejected due to precondition conflict. The storage node can buffer them until the prepared transaction completes. Once it completes, a queued write operation can be given a later timestamp and serialised after the transaction.
- Another optimisation is for non-transactional `put/delete` operations without any preconditions. DynamoDB assigns a later timestamp than any prepared transaction timestamp for that item and executes immediately. If and when the prepared transaction commits, its write can be ignored if if the commit timestamp is earlier than the last write timestamp on the item.

> *Write transactions can be accepted even with an old timestamp.*

- A write operation with an older timestamp can enter the prepared state. When committing, the write will be ignored since the put or transactional put operation that occurs later would overwrite this transaction's change. The benefit is, if this transaction changes some other items that don't have a later write timestamp, the change is allowed to happen.

> *Multiple transactions that write the same item may be prepared at the same time.*

- More than one transactions on the same item can be accepted. If a `put` or `delete` transaction completely overwrite the item, then other transactions can be committed in any order as long as the transaction with latest timestamp with such a `put` or `delete` operation executes last.

> *Read transactions can be executed in a single round rather than using a two-phase protocol.*

- This is possible if the read transaction has a timestamp greater than the last write timestamp for that item and less than any prepared transactions. But a subtle problem is if another write transaction is accepted in the storage node with an older timestamp than the read transaction and later than the last write timestamp! This causes serialisability to be broken.
- A solution to the above problem is to have a last read timestamp and reject any write transaction with an earlier timestamp than the read timestamp.

%% DynamoDB probably doesn't use this solution, hence avoids single-phase read transaction. It's because in section 3.4 of the paper, the authors mention that they use a "2-phase write-less protocol for read transactions".%%

> *Transactions that write multiple items in a single partition can be executed in a single round rather than using a two-phase protocol.*

- If only one primary storage node is participating in the transaction, DynamoDB can avoid 2-phase protocol and commit the transaction in a single phase.