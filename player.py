import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os


class Player:
    '''
    Gstreamer playbin with basic play, pause, stop and seek
    updates slider (slider) and label in gui.
    '''
    def __init__(self, time_label, slider, soundcard):
        Gst.init(None)
        self.player = Gst.ElementFactory.make("playbin", "player")
        fakesink = Gst.ElementFactory.make("fakesink", "fakesink")
        sink = Gst.ElementFactory.make("alsasink", "audio_sink")
        alsasink = Gst.ElementFactory.make("alsasink", "alsasink")
        alsasink.set_property("device", "hw:0")
        self.player.set_property("audio-sink", alsasink)
        
        self.player.set_property("video-sink", fakesink)
        self.player.set_property("audio-sink", sink)

        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
        
        self.time_format = Gst.Format(Gst.Format.TIME)
        
        #set statusbar ref.
        self.time_label = time_label
        self.slider = slider
        self.slider_handler_id = self.slider.connect("value-changed", self.slider_changed)
        
    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            print(message.parse_qos())
            #err, debug = message.parse_qos()
            #print ("Error: {0}").format (err, debug)
            self.is_playing = False
            self.player.set_state(Gst.State.NULL)
            self.time_label.set_text("00:00 / 00:00")
            self.slider.set_value(0)
                        
        elif t == Gst.MessageType.ERROR:
            self.is_playing = False
            self.player.set_state(Gst.State.NULL)
            err, debug = message.parse_error()
            print ("Error: {0}").format (err, debug)
            self.player.set_state(Gst.State.NULL)
            self.time_label.set_text("00:00 / 00:00")
            self.slider.set_value(0) 

    def set_filepath(self, filepath):
        uri = "file://" + filepath
        self.player.set_property("uri", uri)        
    
    def play(self):
        self.player.set_state(Gst.State.PLAYING)
        GLib.timeout_add(1000, self.update_gui)        
    
    def pause(self):
        self.player.set_state(Gst.State.PAUSED)        
    
    def stop(self):
        self.player.set_state(Gst.State.NULL)

    def get_state(self):
        state = self.player.get_state(0.005)[1]
        return state

    def slider_changed(self, slider):
        seek_value = self.slider.get_value()
        self.player.seek_simple(
            Gst.Format.TIME,  
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, 
            seek_value * Gst.SECOND
            )
        
    def update_gui(self):
        state = self.get_state()
        if state != Gst.State.PLAYING:
            return False # cancel timeout
        else:
            success, int_duration = self.player.query_duration(Gst.Format.TIME)
            success, int_position = self.player.query_position(Gst.Format.TIME)
            #update label and set slider range
            str_duration = self.convert_ns(int_duration)
            self.slider.set_range(0, int_duration / Gst.SECOND)
            
            str_position = self.convert_ns(int_position)
            self.slider.handler_block(self.slider_handler_id)
            self.slider.set_value(float(int_position) / Gst.SECOND)
            self.slider.handler_unblock(self.slider_handler_id)
            
            self.time_label.set_text(str_position + " / " + str_duration)
            
            return True
            
        
    def convert_ns(self, time_int):
        s,ns = divmod(time_int, 1000000000)
        m,s = divmod(s, 60)

        if m < 60:
            str_duration = "%02i:%02i" %(m,s)
            return str_duration
        else:
            h,m = divmod(m, 60)
            str_duration = "%i:%02i:%02i" %(h,m,s)
            return str_duration        

