# todo: add log rotation
set up log rotation:
Example:
```bash
/etc/logrotate.d/

/var/log/myapp/*.log {
    daily               # Rotate the logs every day
    rotate 14           # Keep up to 14 old log files before delete.  -1= never delete
    compress            # Compress rotated logs using gzip (.gz)
    delaycompress       # Delay compression until the next rotation cycle
    missingok           # Do not throw an error if the log file is missing
    notifempty          # Do not rotate the log if it is completely empty
    create 0640 app app # Create a new empty log file (perms user group)
    sharedscripts       # Run postrotate script only once per wildcard match
    copytruncate        # when compressing an active log, the run time proc to compress may loose a small bit of data
    size                # when log reaches size rotate
    maxsize             # files over a SIZE get rotated / compressed immediately.
    postrotate
        /usr/bin/systemctl reload myapp > /dev/null 2>&1 || true
    endscript
}
```


# testing example:
in /etc/logrotate.d/hpc
```bash
/var/log/hpc/data/*/*/*.csv {
    daily
    maxsize 100M
    # keep 20 years of logs before a delete
    rotate 7300 
    compress
    nodelaycompress
    missingok
    notifempty
    copytruncate  
}
```
--> # in-line commentary not allowed.

given the large number of logs we want to keep, and the limited space... 
it is possible that we want some auxiliary script to perform an action,
such as remove older logs, to free up space, or generate a notification.

# debugging:  
```bash
sudo logrotate --debug /etc/logrotate.d/hpc
```

# because I ran debug, I learned inline commments are not allowed.

# Example debugging:

```bash
eri@sys76:~/stock_hmi$ sudo logrotate --debug /etc/logrotate.d/hpc
warning: logrotate in debug mode does nothing except printing debug messages!  Consider using verbose mode (-v) instead if this is not what you want.

reading config file /etc/logrotate.d/hpc
note: 'size' overrides previously specified 'daily'
Reading state from file: /var/lib/logrotate/status
Allocating hash table for state file, size 64 entries

Creating new state
...
Creating new state
Creating new state
Creating new state
Creating new state

Handling 1 logs

rotating pattern: /var/log/hpc/data/*/*/*.csv  104857600 bytes (7300 rotations)
empty log files are not rotated, old logs are removed
considering log /var/log/hpc/data/*/*/*.csv
Creating new state

```
