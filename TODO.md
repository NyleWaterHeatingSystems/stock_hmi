# Todo:
- add logrotation


# maybe todo:
  
  When we get an HMI, in the 30+ or so, that we've gotten, they were all
  bookworm. that will change eventualy. I could write a detect os function.
  to install the package dependencies for the detected OS.
  
  From testing: 
  One of the functions of this script is to update from hpp_latest.
  that works great, but when we ran the provissioner script on a previously 
  configured unit with trixie, the dependencies / deb packages threw 
  version issues, and would not install. this did not prevent the 
  HPC software from running, as the dependencies were already installed.
  
  What I can do is:
     run a check for dependencies already being present / installed.
     include dependencies for other OS versions.
     install matching OS package dependencies per install. 
     
  its like 3 extra functions, it wouldnt be that bad, and it would mean 
  the provissioner works in every case we might see for quite some time.
  
  Alternatively, I have made a trixie version of this installer, 
  I just pulled it out to eliminate confussion. 
