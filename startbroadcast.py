#!/usr/bin/python2
#do it as a class
#working example

import dbus
from dbus.mainloop.glib import DBusGMainLoop


class StartBroadcast():  
    def __init__(self): 
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()
        self.proxy = self.bus.get_object('com.threedradio.MessagePlayer',
            '/MyDbus')
        self.control_interface = dbus.Interface(self.proxy,
            'com.threedradio.MessagePlayer')  
    
    def run(self):
        self.control_interface.signal_received()           

        
sw = StartBroadcast()
sw.run()

