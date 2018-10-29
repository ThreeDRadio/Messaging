#!/usr/bin/python2
# do it as a class
# do it under systemd and specify differenc actions for the different ports
# hoping no need for log file as systemd 'prints' to journal - may not be the case

import time, os, gobject, dbus
from dbus.mainloop.glib import DBusGMainLoop
from serial import Serial
from fcntl import  ioctl
from termios import (
    TIOCMIWAIT,
    TIOCM_RNG,
    TIOCM_DSR,
    TIOCM_CD,
    TIOCM_CTS
)

#dev_ser = '/dev/ttyUSB0'
dev_ser = '/dev/ttyS0'
#logfile = "/var/log/serialwatch.log"


ser = Serial(dev_ser)

wait_signals = (TIOCM_RNG |
                TIOCM_DSR |
                TIOCM_CD  |
                TIOCM_CTS)

class SerialWatch():         
    def getdbus (self):
        #dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        print("initialising dbus")
        self.bus = dbus.SessionBus()
        try: 
            #print("attempting to connect to MessagePlayer")
            self.proxy = self.bus.get_object('com.threedradio.MessagePlayer',
            '/MyDbus')
            #print("setting the dbus control interface for MessagePlayer")
            self.control_interface = dbus.Interface(self.proxy,
            'com.threedradio.MessagePlayer') 
        except:
            self.control_interface = ""
            print("Failure to connect to ThreedPlayer via DBus")
        return self.control_interface
    
    def logging (self, logmessage):
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        self.logentry = timestamp + ": " + logmessage
        #f = open(logfile, 'w')
        #f.write(logentry)
        #f.close()
        print self.logentry
    
    def RI(self):
        logmessage = "Got the RI"
        print(logmessage)
        self.logging(logmessage)
        
    def DSR(self):
        logmessage = "Got the DSR"
        print(logmessage)
        self.logging(logmessage)

    def CD(self):    
        logmessage = "Got the CD"
        print(logmessage)
        self.logging(logmessage)
        control_interface = self.getdbus()
        if control_interface:
            print("Processing signal and attempting to trigger MessagePlayer")
            control_interface.signal_received() 
        else:
            print("Looks like the threedplayer is not running or script is buggy")
    
    def CTS(self):
        logmessage = "Got the CTS"
        print(logmessage)
        self.logging(logmessage)
    
    def run(self):
        print("Starting to watch")
        self.getdbus()
        while True:
            ioctl(ser.fd, TIOCMIWAIT, wait_signals)
            if ser.getRI():
                self.RI()
            if ser.getDSR():
                self.DSR()
            if ser.getCD():
                self.CD()
            if ser.getCTS():
                self.CTS()
          #self.control_interface.signal_received()           
            time.sleep(0.5)
        
sw = SerialWatch()
sw.run()

