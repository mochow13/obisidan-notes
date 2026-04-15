#### `kubectel`
- `ssh` into a container in a pod
```
exec -it -c <container> <pod> -- bash
```
#### Updating `prod` db
- `ssh` into `app` container
- Copy id-pass for the db:
```
cat /etc/bookings/db.json
```
- `ssh` into `app-staging`
```
ssh app-staging 
or 
ssh http://app-staging.prod.booking.com/
```
- Login using the db id and pass:
```
mysql -h<host> -u<user> -p (don't put password directly, it will be prompted)
Example: mysql -hpartnershipnosoxmdb-vip.dbmaster.booking.com -uapp_bexreward_rw1 -p
```

#### Reading Prod Database

```
mysqly -m rdbprod --fancy bexreward
```