stock HMI provissioner for edatech ED-HMI2220-070C
** This is an online installer, for now, it needs internet to retrive libx11-dev and libpaho-dev**
Work in Progress, multiple factors for confussion, addressed below.
Synopis:  
Download the package, and run the script on a stock installation of the 
edatech ED-HMI2220-070C
Config of OS and user parameters will be configured via script.

# structure:  
stock-hmi.py
bin/
├── HPC_LinuxGUI
├── assets/
└── settings.txt


# intent:
For builders and maintainers, the intent is that the HPC_LinuxGUI can be dropped in and recompiled.
For OS Configurations and Maintenance, edit the script. 

# Security: 
There are no passwords in the script, and the HPC program installation is done 
on the basis of having a precompiled binary, + the assets folder. 

# How the script actualy works:
in ~/$USER/hpc-hmi/bin
the HPC HMI code is placed, and service set up is for that location, with the binary executable 
having the name HPC_LinuxGUI. The service that autoruns the GUI is based on this assertion. 
We can change it. 

# build / rebuild:  
pyinstaller --onefile --name stock-hmi stock-hmi.py
(should workd, havent tested that.)
    
############## ISSUES ###############

# versioning: 
HPC Code depends on libc6, which is provided by the OS, but the version,   
is determined by the OS, and the stock OS provides version 2.36 in bookworm.  
while Trixie uses version 2.38. The variation is important, as updating can brick your OS.  
Why that matters:   
EDATEC support for the current stable linux version is not yet complete.   
   various driver related issues for different versions of the HMI seem to be effected.  

Versions of the HPC_LinuxGUI may not run on newer or older versions of libc6.   
(I havent figured out why yet)

########## Specific stuff ##########
BOOKWORM/ is where a version of the HPC_LinuxGUI was compiled on debian 12, with libc6 v2.36  
TRIXIE/  is where a version of the HPC_LinuxGUI was compiled on debian 13, with libc6 v2.38  

######### derivative notes ########
https://edatec.cn/docs/hmi2220-101c/um/6-installing-os/#_6-3-installing-firmware-package  
curl -s https://apt.edatec.cn/bsp/ed-install.sh | sudo bash -s hmi2220-101c  
