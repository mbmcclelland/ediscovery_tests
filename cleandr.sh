#! /usr/bin/bash
SYSTEMD_LOG_LEVEL=debug systemctl stop drd
# License goes to /root/ — DR_freshinstall.exp's final step expects it there.
\cp -v /home/auraria/AHS/conf/license.lic /root/license.lic 2>/dev/null || \
  \cp -v license.lic /root/license.lic
rm -rfv /home/auraria/AHS*
rm -rfv /var/.com.zerog.registry.xml
rm -rfv /tmp/cbe* cpuinfo.txt artemis* install.dir.*
rm -rfv /data/docstorage/*
rm -rfv /data/indexstorage/*


