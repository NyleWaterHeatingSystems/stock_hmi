# expiramental:

- Update a previously provissioned software with --patch option  

This is to add the logrotate, log compression function, but may include   
other OS updates and system changes, post install.  

stock-hmi.py --patch will report kernel version and OS install version  
for informational purposes, and add the "hpc" config file to /etc/logrotate.d/  

PROVIDED: The user is now nwhs, and the password corrosponds to the encrypted  
password in APP_PASSWORD_HASH


check boot time
check spash screen
add logrotate to stock-hmi.py (auto install )

investigate labwc touchscreen issues / default screen / session.

investigate services.
check log rotation. 

look at nmcli configs / networking

prevent tty terminal currsor from interupting HPCLinuxGUI interface. 


e180 has a boottime of ~=30s, with ed-lte-daemon.service (20.047s)
