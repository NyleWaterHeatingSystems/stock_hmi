# todo: at log rotation
set up log rotation:
Example:
```bash
/etc/logrotate.d/

/var/log/myapp/*.log {
    daily               # Rotate the logs every day
    rotate 14           # Keep up to 14 old log files before deleting
    compress            # Compress rotated logs using gzip (.gz)
    delaycompress       # Delay compression until the next rotation cycle
    missingok           # Do not throw an error if the log file is missing
    notifempty          # Do not rotate the log if it is completely empty
    create 0640 app app # Create a new empty log file (perms user group)
    sharedscripts       # Run postrotate script only once per wildcard match
    copytruncate        # when compressing an active log, the run time proc to compress may loose a small bit of data
    size                # files over a SIZE get rotated / compressed immediately.
    postrotate
        /usr/bin/systemctl reload myapp > /dev/null 2>&1 || true
    endscript
}
```

# debugging:  
```bash
sudo logrotate --debug /etc/logrotate.d/hpc
```

# closer:
in /etc/logrotate.d/hpc
```bash
/var/log/hpc/data/*/*/*.csv {
    daily
    size 100M
    rotate 7300 # keep 20 years of logs before a delete
    #rotate -1  # never delete
    compress
    nodelaycompress
    missingok
    notifempty
    copytruncate  
}
```

given the large number of logs we want to keep, and the limited space... 
it is possible that we want some auxiliary script to perform an action,
such as remove older logs, to free up space, or generate a notification.
