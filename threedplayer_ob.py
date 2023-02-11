#!/usr/bin/python2
'''message_player-0.2.py
retrieves message info from database.
Displays message types as buttons on left pane.
displays messages of a given type on centre pane
Displays selected/dragged messages ona left pane
Functioning scheduler
playback working from preview and broadcast
implements broadcast from serial signal 
using subprocess and dbus
has 'join' feature to link tracks. integrates with dnd
'''
import fcntl, sys
pid_file = 'threedplayer.pid'
fp = open(pid_file, 'w')
try:
    fcntl.lockf(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    # another instance is running
    sys.exit(0)

import pygtk
import gtk
import gobject
import pango
import sys
import psycopg2
import psycopg2.extras
import pickle
import subprocess
import datetime
import os
import time
import gst
import pygst
import socket
import threading
import thread
import dbus
import ConfigParser
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from subprocess import Popen
from operator import itemgetter
from lxml import etree
from psycopg2 import sql

#other variables
sfx = ".p3d"
sfx_old = ".p3d"

#lists       

tup_day = ("Monday", 
            "Tuesday", 
            "Wednesday", 
            "Thursday", 
            "Friday", 
            "Saturday", 
            "Sunday")

unys = ("unknown", "no", "yes", "some")

select_items = (
    "cd.title",
    "cd.artist",
    "cd.company",
    "cd.year",
    "cd.arrivaldate",
    "cd.demo",
    "cd.local",
    "cd.female",
    "cd.compilation",
    "cd.createwho",
    "cd.createwhen",
    "cd.genre",
    "cd.cpa",
    "cdtrack.trackid",
    "cdtrack.cdid",
    "cdtrack.tracknum",
    "cdtrack.tracktitle",
    "cdtrack.trackartist",
    "cdtrack.tracklength",
    "cdcomment.comment"
    )


order_results = {
            "Newest Albums First": (("year", "DESC"), ("id", "DESC")),
            "Oldest Albums First": (("year", "ASC"), ("id", "ASC")),
            "Artist Alphabetical": (("artist", "ASC"), ("id", "DESC")),
            "Album Alphabetical": (("title", "ASC"), ("id", "DESC")),
            "Most Recently Added":(("createwhen", "DESC"), ("id", "DESC"))
}
where_items = (
    "cdtrack.trackartist",
    "cdtrack.tracktitle",
    "cd.title",
    "cd.artist"
    )

        ### Styles ###

header_font = pango.FontDescription("Sans Bold 18")
subheader_font = pango.FontDescription("Sans Bold 14")
subheader_font_1 = pango.FontDescription("Sans Bold 12")
subheader_font_2 = pango.FontDescription("Sans Bold 11")
            
#get variables from config file
config = ConfigParser.SafeConfigParser()
config.read('/usr/local/etc/threedradio.conf')

#the serialwatch script to be run as a subprocess
# may not be required, serialwatch now running as a service.
dir_serialwatch = config.get('Paths', 'dir_serialwatch')
file_serialwatch = config.get('ThreeDPlayer', 'file_serialwatch')

dir_p3d = config.get('Paths', 'dir_pl3d')

dir_msg = config.get('Paths', 'dir_msg')
dir_mus = config.get('Paths', 'dir_mus')
dir_img = config.get('Paths', 'dir_img')
logo = config.get('Images', 'logo')

query_limit = config.getint('ThreeDPlayer', 'query_limit')

pg_server = config.get('Common', 'pg_server')
pg_cat_user = config.get('ThreeDPlayer', 'pg_cat_user')
pg_cat_password = config.get('ThreeDPlayer', 'pg_cat_password')
pg_cat_database = config.get('Common', 'pg_cat_database')
pg_msg_user = config.get('ThreeDPlayer', 'pg_msg_user')
pg_msg_password = config.get('ThreeDPlayer', 'pg_msg_password')
pg_msg_database = config.get('Common', 'pg_msg_database')


#image files for the 'join' feature
img_blank = config.get('Images', 'img_blank')
img_top = config.get('Images', 'img_top')
img_mid = config.get('Images', 'img_mid')
img_btm = config.get('Images', 'img_btm')


class CellRendererPixbufXt(gtk.CellRendererPixbuf):
    '''
    A special class of cell to be used in treeview rows. It will
    activate a signal when clicked which can be connected to a method.
    It is used for the 'join' feature.
    '''
    __gproperties__ = { 'active-state' :                                      
                        (gobject.TYPE_STRING, 'pixmap/active widget state',  
                        'stock-icon name representing active widget state',  
                        None, gobject.PARAM_READWRITE) }                      
    __gsignals__    = { 'clicked' :                                          
                        (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()) , } 

    def __init__( self ):                                                    
        gtk.CellRendererPixbuf.__init__( self )                              
        self.set_property( 'mode', gtk.CELL_RENDERER_MODE_ACTIVATABLE )      
                                                                              
    def do_get_property( self, property ):                                    
        if property.name == 'active-state':                                  
            return self.active_state                                          
        else:                                                                
            raise AttributeError, 'unknown property %s' % property.name      
                                                                              
    def do_set_property( self, property, value ):                            
        if property.name == 'active-state':                                  
            self.active_state = value                                        
        else:                                                                
            raise AttributeError, 'unknown property %s' % property.name      
                                                                              
    def do_activate( self, event, widget, path,  background_area, cell_area, 
        flags ):                                                 
        if event.type == gtk.gdk.BUTTON_PRESS:                                
            self.emit('clicked')       
                                             
    def do_clicked(self):                                        
        #print "do_clicked"                                          
        pass
    
gobject.type_register(CellRendererPixbufXt)

class MyDbus(dbus.service.Object):
    '''
    This enables a dbus signal to activate the broadcast player. 
    The serialwatch script/service is used to send the signal.
    '''
    @dbus.service.method('com.threedradio.MessagePlayer')
    def signal_received(self):
        '''
        specify the dbus service for threedplayer
        '''
        self.tdp = ThreeD_Player()
        tdp.serial_signal()

class Preview_Player:
    '''
    Adapted from Benny Malev's DamnSimplePlayer. 
    Plays the selected track, outputs to the souncard with the 
    alias 'preview' as defined in /etc/asound.conf
    '''
    def __init__(self, time_label, hscale, reset_playbutton):
        '''
        Calls the class with arguments. 
        Creates the pipe using a playbin and 
        specifies the alsa pcm device as 'preview' 
        '''
        self.player = gst.element_factory_make("playbin2", "player")
        fakesink = gst.element_factory_make("fakesink", "fakesink")
        alsa_card0 = gst.element_factory_make("alsasink", "preview")
        alsa_card0.set_property("device", "preview")
        self.player.set_property("video-sink", fakesink)
        self.player.set_property("audio-sink", alsa_card0)
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
        
        self.time_format = gst.Format(gst.FORMAT_TIME)
        
        #set statusbar ref.
        self.time_label = time_label
        self.hscale = hscale
        self.reset_playbutton = reset_playbutton
        
        #to hold place on change event in gui
        self.place_in_file = None
        self.progress_updatable = True
       
    def set_place_in_file(self,place_in_file):
        self.place_in_file = place_in_file
    
    def start(self, filepath):
        '''
        Start playing an audio file
        '''
        self.player.set_property("uri", "file://" + filepath)
        self.player.set_state(gst.STATE_PLAYING)
        self.play_thread_id = thread.start_new_thread(self.play_thread, ())
             
    def stop(self):
        '''
        Stop playing
        '''
        self.play_thread_id = None
        self.player.set_state(gst.STATE_NULL)
        self.reset_components()
        
    def pause(self):
        '''
        Pause playing
        '''
        self.player.set_state(gst.STATE_PAUSED)
                        
    def on_message(self, bus, message):
        '''
        resets the state when reaching the end of the audio file
        '''
        t = message.type
        if t == gst.MESSAGE_EOS:
            self.play_thread_id = None
            self.player.set_state(gst.STATE_NULL)
            self.reset_components()
                        
        elif t == gst.MESSAGE_ERROR:
            self.play_thread_id = None
            self.player.set_state(gst.STATE_NULL)
            err, debug = message.parse_error()
            print ("Error: {0}").format (err, debug)
            self.reset_components()

    def convert_ns(self, time_int):
        '''
        Changes the time fraction to human readable minutes and seconds.
        '''
        s,ns = divmod(time_int, 1000000000)
        m,s = divmod(s, 60)

        if m < 60:
            str_dur = "%02i:%02i" %(m,s)
            return str_dur
        else:
            h,m = divmod(m, 60)
            str_dur = "%i:%02i:%02i" %(h,m,s)
            return str_dur
        
    def get_duration(self):
        '''
        Get the length of the file        
        '''
        dur_int = self.player.query_duration(self.time_format, None)[0]
        return self.convert_ns(dur_int)
        
    def set_updateable_progress(self,flag):
        self.progress_updatable = flag 
        
    def rewind_callback(self):
        pos_int = self.player.query_position(self.time_format, None)[0]
        seek_ns = pos_int - (10 * 1000000000)
        self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH, seek_ns)
        
    def forward_callback(self):
        pos_int = self.player.query_position(self.time_format, None)[0]
        seek_ns = pos_int + (10 * 1000000000)
        self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH, seek_ns)
        
    def get_state(self):
        play_state = self.player.get_state(1)[1]
        return play_state
        
    #duration updating func
    def play_thread(self):
        play_thread_id = self.play_thread_id
        
        while play_thread_id == self.play_thread_id:
            try:
                time.sleep(0.2)
                dur_int = self.player.query_duration(self.time_format, None)[0]
                dur_str = self.convert_ns(dur_int)
                
                self.duration_time = dur_int / 1000000000
                
                gtk.gdk.threads_enter()
                self.time_label.set_text("00:00 / " + dur_str)
                
                #set hscale
                self.hscale.set_range(0,self.duration_time)
                
                gtk.gdk.threads_leave()
                break
            except:
                pass
                
        time.sleep(0.2)
        while play_thread_id == self.play_thread_id:
            
            #update position
            if self.place_in_file:
                self.player.seek_simple(self.time_format ,gst.SEEK_FLAG_FLUSH | gst.SEEK_FLAG_KEY_UNIT | gst.SEEK_TYPE_SET ,self.place_in_file*1000000000)
                self.place_in_file = None
                #let the seek enough time to complete
                time.sleep(0.1)
            
            pos_int = self.player.query_position(self.time_format, None)[0]
            pos_str = self.convert_ns(pos_int)
            
            self.current_time = pos_int / 1000000000
            
            if play_thread_id == self.play_thread_id:
                gtk.gdk.threads_enter()
                
                if self.progress_updatable:
                    #update hscale
                    self.hscale.set_value(self.current_time)
                
                self.time_label.set_text(pos_str + " / " + dur_str)
                
                gtk.gdk.threads_leave()
            time.sleep(1)
    def reset_components(self):  
        self.time_label.set_text("00:00 / 00:00")
        self.hscale.set_value(0)
        self.reset_playbutton()

class Broadcast_Player:
    '''
    adapted from Benny Malev's DamnSimplePlayer
    Plays the selected track, outputs to the souncard with the 
    alias 'broadcast' as defined in /etc/asound.conf
    '''
    def __init__(self, time_label, label_length, progressbar, label_air_warning, check_join):
        self.player = gst.element_factory_make("playbin2", "player")
        fakesink = gst.element_factory_make("fakesink", "fakesink")
        alsa_card0 = gst.element_factory_make("alsasink", "broadcast") 
        alsa_card0.set_property("device", "broadcast")
        self.player.set_property("video-sink", fakesink)
        self.player.set_property("audio-sink", alsa_card0)
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
      
        self.time_format = gst.Format(gst.FORMAT_TIME)
        
        #set statusbar ref.
        self.time_label = time_label
        self.label_length = label_length
        self.progressbar = progressbar
        self.label_air_warning = label_air_warning
        self.check_join = check_join
        #to hold place on change event in gui
        self.place_in_file = None
        self.progress_updatable = True
       
    def set_place_in_file(self,place_in_file):
        self.place_in_file = place_in_file
    
    def start(self, filepath):
        self.player.set_property("uri", "file://" + filepath)
        self.player.set_state(gst.STATE_PLAYING)
        self.play_thread_id = thread.start_new_thread(self.play_thread, ())
             
    def stop(self):
        self.play_thread_id = None
        self.player.set_state(gst.STATE_NULL)
        self.reset_components()
        
    def pause(self):
        self.player.set_state(gst.STATE_PAUSED)
                        
    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_EOS:
            self.play_thread_id = None
            self.player.set_state(gst.STATE_NULL)
            self.reset_components()
            self.check_join()
                        
        elif t == gst.MESSAGE_ERROR:
            self.play_thread_id = None
            self.player.set_state(gst.STATE_NULL)
            err, debug = message.parse_error()
            print ("Error: {0}").format (err, debug)
            self.reset_components()

    def convert_ns(self, time_int):
        s,ns = divmod(time_int, 1000000000)
        m,s = divmod(s, 60)

        if m < 60:
            str_dur = "%02i:%02i" %(m,s)
            return str_dur
        else:
            h,m = divmod(m, 60)
            str_dur = "%i:%02i:%02i" %(h,m,s)
            return str_dur
        
    def get_duration(self):
        dur_int = self.player.query_duration(self.time_format, None)[0]
        return self.convert_ns(dur_int)
        
    def set_updateable_progress(self,flag):
        self.progress_updatable = flag 
        

    def get_state(self):
        play_state = self.player.get_state(1)[1]

        return play_state
        
    #progress updating func
    def play_thread(self):
        play_thread_id = self.play_thread_id
        
        while play_thread_id == self.play_thread_id:
            try:
                time.sleep(0.2)
                dur_int = self.player.query_duration(self.time_format, None)[0]
                dur_str = self.convert_ns(dur_int)
                
                self.duration_time = dur_int / 1000000000
                
                gtk.gdk.threads_enter()
                self.time_label.set_text(dur_str)
                
                #set progressbar
                self.progressbar.set_fraction(0)
                
                gtk.gdk.threads_leave()
                break
            except:
                pass
                
        time.sleep(0.2)
        while play_thread_id == self.play_thread_id:
            
            #update position
            if self.place_in_file:
                self.player.seek_simple(self.time_format ,gst.SEEK_FLAG_FLUSH | gst.SEEK_FLAG_KEY_UNIT | gst.SEEK_TYPE_SET ,self.place_in_file*1000000000)
                self.place_in_file = None
                #let the seek enough time to complete
                time.sleep(0.1)
            
            pos_int = self.player.query_position(self.time_format, None)[0]
            rem_int = dur_int - pos_int
            rem_str = self.convert_ns(rem_int)
            
            self.current_time = pos_int / 1000000000
            
            if play_thread_id == self.play_thread_id:
                gtk.gdk.threads_enter()
                
                if self.progress_updatable:
                    #update progressbar
                    
                    fraction = float(pos_int) / dur_int
                    self.progressbar.set_fraction(fraction)
                
                self.time_label.set_text(rem_str)
                
                gtk.gdk.threads_leave()
            time.sleep(1)
      
    def reset_components(self):  
        self.time_label.set_text("00:00")
        self.label_length.set_text("00:00")
        self.progressbar.set_fraction(0)
        self.progressbar.set_text("")
        self.label_air_warning("not playing")

class ThreeD_Player():
    
    def delete_event(self, widget, event, data=None):
        return False

    def destroy(self, widget, data=None):
        gtk.main_quit()

    def main(self):
        '''
        the GUI layout, connections and dnd.
        '''
        # global variables

        self.list_messages = []
        self.list_search = []
        self.list_playlist = []
        self.list_schedule = []
        self.column_width = 80

       # The GUI
        window = gtk.Window(gtk.WINDOW_TOPLEVEL) 
        window.set_position(gtk.WIN_POS_CENTER)
        filepath_logo = dir_img + logo
        window.set_icon_from_file(filepath_logo)
        #window.set_resizable(False)
        window.set_size_request(800, 600)
        
        ###   create containers - boxes and scrolled windows  ###
        #top level vbox - holds menubar, messages scheduler/preview and air list
        vbox_main = gtk.VBox(False, 0)
        #top level hbox holds messages scheduler/preview and air list
        hbox_main = gtk.HBox(False, 0)
        #vbox to hold the notebook and the scheduler/preview
        vbox_nb = gtk.VBox(False, 0)
        #notebook for tabbed interface
        notebook = gtk.Notebook()
        #notebook.set_size_request(940, 600)
        #hbox for message buttons and list
        hbox_msg = gtk.HBox(False, 5)
        #vbox for label and message buttons
        vbox_msg_btn = gtk.VBox(False, 0)
        vbox_msg_btn.set_size_request(200, 200)
        #vbox for buttons inside the scroll window
        self.vbox_sw_msg_btn = gtk.VBox(False, 0)
        #scrolled window for buttons
        sw_msg_btn = gtk.ScrolledWindow(hadjustment=None)
        sw_msg_btn.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_msg_btn.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)
        #vbox for message list
        vbox_msg_lst = gtk.VBox(False, 0)
        #scrolled window for message list treeview
        sw_msg_lst = gtk.ScrolledWindow()
        sw_msg_lst.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_msg_lst.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        #hbox for music catalogue
        hbox_cat = gtk.HBox(False, 5)
        #vbox for catalogue search
        vbox_cat_search = gtk.VBox(False, 5)
        #hbox for simple search button and result label
        hbox_simple_search = gtk.HBox(False, 5)
        #hbox for advanced search button and result label
        hbox_adv_search = gtk.HBox(False, 5)
        #table for music catalogue search
        table_search = gtk.Table(20, 2, False)
        # hbox for catalogue order selection
        hbox_search_order = gtk.HBox(False, 5)
        # hbox for catalogue maximum result limit selection
        hbox_search_max = gtk.HBox(False, 5)
        #vbox for catalogue list
        vbox_search_lst = gtk.VBox(False, 0)
        #scrolled window for catalogue list treeview
        sw_cat_list = gtk.ScrolledWindow()
        sw_cat_list.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_cat_list.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        #hbox for list import
        hbox_p3d = gtk.HBox(False, 5)
        # vbox for buttons and option for list import
        vbox_p3d_opt = gtk.VBox(False, 5)
        #vbox for the imported list
        vbox_p3d_lst = gtk.VBox(False, 5)
        #scrolled window for browsing p3d files
        sw_p3d_opt = gtk.ScrolledWindow()
        sw_p3d_opt.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_p3d_opt.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        #scrolled window for imported list
        sw_p3d_lst = gtk.ScrolledWindow()
        sw_p3d_lst.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_p3d_lst.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        #hbox for the copy buttons below the imported list
        hbox_p3d_btn = gtk.HBox(False, 5)      
        #hbox  for scheduler and preview
        #vbox_sch = gtk.HBox(False, 0)
        #vbox for the playing and queued messages 
        vbox_bc = gtk.VBox(False, 5)    
        #hbox for progress label and skip button in the broadcast pane
        hbox_bc_0 = gtk.HBox(False, 0)
        #hbox for list option buttons in the broadcast pane
        hbox_bc_1 = gtk.HBox(False, 0)
        #scrolled holder for the broadcast message treelist
        sw_bc = gtk.ScrolledWindow()
        sw_bc.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_bc.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        #hbox for displaying total time of listed tracks
        hbox_bc_time = gtk.HBox(False, 0)
        # hbox  for scheduler and preview
        vbox_sch = gtk.VBox(False, 5)
        # vbox for buttons and drop-down list
        hbox_sch = gtk.HBox(False, 0)
        #scrolled window for the schedule list
        sw_sch = gtk.ScrolledWindow()
        sw_sch.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_sch.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        # vbox for preview section
        vbox_pre = gtk.VBox(False, 2)  
        # hbox for preview player buttons
        hbox_pre_btn = gtk.HBox(False, 0)
        # hbox for track detail
        hbox_pre_play = gtk.HBox(False, 0)  
        # hbox for the clock
        hbox_pre_time = gtk.HBox(False, 0)
        # hbox for the countdown
        hbox_pre_cdn = gtk.HBox(False, 0)
        
        ### ----------------Message List Section---------------- ###   
             
        # images for buttons
        self.image_play = gtk.Image()
        self.image_play.set_from_stock(gtk.STOCK_MEDIA_PLAY, gtk.ICON_SIZE_BUTTON)
        self.image_play.set_name("play")
        self.image_pause = gtk.Image()
        self.image_pause.set_from_stock(gtk.STOCK_MEDIA_PAUSE, gtk.ICON_SIZE_BUTTON)
        self.image_pause.set_name("pause")
        image_stop = gtk.Image()
        image_stop.set_from_stock(gtk.STOCK_MEDIA_STOP, gtk.ICON_SIZE_BUTTON)

        #label for buttons
        label_msg_btn = gtk.Label(" Messages ")
        label_msg_btn.modify_font(header_font)
        #label_msg_btn.set_size_request(180, 26)
        
        #make the buttons
        self.make_buttons()
  
        #make the list
        store_msg = gtk.ListStore(str, str, str, str)
        self.treeview_msg = gtk.TreeView(store_msg)
        self.treeview_msg.set_rules_hint(True)
        treeselection_msg = self.treeview_msg.get_selection()
        self.add_msg_columns(self.treeview_msg)
        
        ### ----------------Music Catalogue Section---------------- ###
        
        label_cat = gtk.Label(" Catalogue ")
        label_cat.modify_font(header_font)        
        sep_search_0 = gtk.HSeparator()
        label_search_simple = gtk.Label("Simple Search")
        label_search_simple.modify_font(subheader_font_1)
        self.entry_search_simple = gtk.Entry(50)
        btn_search_simple = gtk.Button("Search")
        btn_search_simple.set_tooltip_text("Simple search")
        btn_search_simple.set_size_request(80, 30)
        self.label_result_simple = gtk.Label()
        sep_search_1 = gtk.HSeparator()
        label_search_adv = gtk.Label("Advanced Search")
        label_search_adv.modify_font(subheader_font_1)
        label_search_artist = gtk.Label("Artist")
        self.entry_search_artist = gtk.Entry(50)
        label_search_album = gtk.Label("Album")
        self.entry_search_album = gtk.Entry(50)
        label_search_track = gtk.Label("Track")
        self.entry_search_track = gtk.Entry(50)
        label_search_cmpy = gtk.Label("Company")
        self.entry_search_cmpy = gtk.Entry(50)
        label_search_genre = gtk.Label("Genre")
        self.entry_search_genre = gtk.Entry(50)        
        label_search_com = gtk.Label("Comments")
        self.entry_search_com = gtk.Entry(50)
        label_search_cpa = gtk.Label("Country")
        self.entry_search_cpa = gtk.Entry(50)
        label_search_year = gtk.Label("Release year")
        self.entry_search_year = gtk.Entry(4)
        label_search_creator = gtk.Label("Added by")
        self.cb_search_creator = gtk.combo_box_new_text()
        style = gtk.rc_parse_string('''
            style "my-style" { GtkComboBox::appears-as-list = 1 }
            widget "*.mycombo" style "my-style"
        ''')
        self.cb_search_creator.set_name('mycombo')
        self.cb_search_creator.set_style(style)
        self.dict_creator = self.get_dict_creator()
        self.cb_search_creator_add(self.dict_creator) 
        
        self.chk_search_comp = gtk.CheckButton("Compilation", True)
        self.chk_search_demo = gtk.CheckButton("Demo", True)
        self.chk_search_local = gtk.CheckButton("Local", True)       
        self.chk_search_fem = gtk.CheckButton("Female", True)
        self.chk_search_nr = gtk.CheckButton("New Entries", True)
        label_search_order = gtk.Label("Order by")
        self.cb_search_order = gtk.combo_box_new_text()
        self.cb_order_add()
        label_search_max = gtk.Label("Maximum Results")
        adjustment_max = gtk.Adjustment(query_limit, 1.0, 10000.0, 50.0, 500.0, 0.0)
        self.spin_search_max = gtk.SpinButton(adjustment_max, 0, 0)        
        btn_search_adv = gtk.Button("Search")
        btn_search_adv.set_tooltip_text("Advanced Search")
        self.label_result_adv = gtk.Label()
        
        ### ----------- Search Results Section -----------###

        label_results = gtk.Label("Search Results")
        label_results.modify_font(subheader_font_1)
        label_results.set_size_request(80, 30)

        #make the list
        self.store_cat = gtk.TreeStore(str ,str ,str ,str ,str)
        self.treeview_cat = gtk.TreeView(self.store_cat)
        self.treeview_cat.set_rules_hint(True)
        treeselection_cat = self.treeview_cat.get_selection()
        self.add_search_columns(self.treeview_cat)
        
        ### ----------- Playlist Import Section -----------###
        
        label_p3d =  gtk.Label(" Playlist ")
        label_p3d.modify_font(header_font)
        label_p3d_browse =  gtk.Label("Select a Playlist")
        label_p3d_browse.set_size_request(200, 28)
        label_p3d_browse.modify_font(subheader_font_1)
        
        # treeview for browsing playlists
        self.store_p3d_browse = gtk.TreeStore(str)
        self.treeview_p3d_browse = gtk.TreeView(self.store_p3d_browse)
        self.treeview_p3d_browse.set_rules_hint(True)
        treeselection_p3d_browse = self.treeview_p3d_browse.get_selection()
        column = gtk.TreeViewColumn('Select a Playlist', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_clickable(False)
        self.treeview_p3d_browse.append_column(column)

        btn_p3d_select = gtk.Button("Browse for a p3d playlist")
        
        #treeview to display playlist
        store_p3d_lst = gtk.ListStore(str ,str ,str ,str, str)
        self.treeview_p3d_lst = gtk.TreeView(store_p3d_lst)        
        self.treeview_p3d_lst.set_rules_hint(True)        
        self.treeview_p3d_lst.set_rubber_banding(True)
        treeselection_p3d_lst = self.treeview_p3d_lst.get_selection()
        treeselection_p3d_lst.set_mode(gtk.SELECTION_MULTIPLE)
        self.add_p3d_columns(self.treeview_p3d_lst)    
        btn_p3d_copysel = gtk.Button("Add Selected")
        btn_p3d_copyall = gtk.Button("Add All")   


        ### ----------------Broadcast section---------------- ###

        #Set up track joining
        path_blank = dir_img + img_blank
        pix_blank = gtk.gdk.pixbuf_new_from_file(path_blank)
        path_top = dir_img + img_top
        pix_top = gtk.gdk.pixbuf_new_from_file(path_top)
        path_mid = dir_img + img_mid
        pix_mid = gtk.gdk.pixbuf_new_from_file(path_mid)
        path_btm = dir_img + img_btm
        pix_btm = gtk.gdk.pixbuf_new_from_file(path_btm)
        
        #reference to be set by click on pix cell and used by selected row
        self.joinme = False
        #label
        label_bc = gtk.Label("Broadcast to Air")
        label_bc.set_size_request(30, 30)        
      
        #make the list
        bc_store = gtk.ListStore(str ,str ,str, 
            gobject.TYPE_BOOLEAN, gtk.gdk.Pixbuf)
        self.treeview_bc = gtk.TreeView(bc_store)
        self.treeview_bc.set_rules_hint(True)
        treeselection_bc = self.treeview_bc.get_selection()        
        self.add_bc_columns(self.treeview_bc)
        
        label_bc = gtk.Label("Broadcast List")
        label_bc.modify_font(header_font)
        
        self.label_air = gtk.Label("")
        self.label_air.set_size_request(50, 50)
        self.label_air_warning("not playing")
        
        btn_testing = gtk.Button("Testing")
        self.progressbar = gtk.ProgressBar()
        self.progressbar.set_size_request(280, 20)
        
        self.label_bc_time = gtk.Label("00:00")
        self.label_bc_time.modify_font(subheader_font)
        self.label_bc_length = gtk.Label("00:00")
        self.label_bc_length.set_selectable(True)
        
        self.player_bc = Broadcast_Player(
            self.label_bc_time, 
            self.label_bc_length,
            self.progressbar, 
            self.label_air_warning, 
            self.check_join)

        btn_inf = gtk.Button("Details")
        btn_rem = gtk.Button("Remove")
        btn_hist = gtk.Button("History")
        btn_hist.set_tooltip_text("Show details of the music tracks played for back-announcing")
        btn_skip = gtk.Button("Skip to End")
        
        adj_spin = gtk.Adjustment(3, 1, 120, 1, 5, 0)
        self.spinbutton = gtk.SpinButton(adj_spin, 0, 0)
        self.spinbutton.set_numeric(True)
        self.spinbutton.set_tooltip_text("How many tracks to be shown in the history")
        
        btn_msg_3hr = gtk.Button("Msg 3hr")
        
        label_time_0 = gtk.Label("Total Broadcast Time - ")
        self.label_time_1 = gtk.Label("00:00  ")
        sep_bc_pre = gtk.HSeparator()

        ### ----------------Scheduler Section ---------------- ###

        # Label
        label_sch = gtk.Label("Schedule")
        label_sch.modify_font(header_font)
        label_sch.set_size_request(200, 30)   
             
        # Buttons
        btn_sch_refresh = gtk.Button(stock=gtk.STOCK_REFRESH)

        btn_sch_now = gtk.Button("Now")
        btn_sch_add = gtk.Button(stock=gtk.STOCK_ADD)

        # make the scheduler list display
        self.store_sch = gtk.ListStore(str ,str, str, str, str)         
        self.treeview_sch = gtk.TreeView(self.store_sch)
        self.treeview_sch.set_rules_hint(True)
        treeselection_sch = self.treeview_sch.get_selection()
        self.add_sch_columns(self.treeview_sch)
        self.set_up_sch()
        self.go_to_now(None)

        ### ----------------Preview Section---------------- ###

        #preview Label
        label_pre = gtk.Label(" Preview")
        label_pre.modify_font(subheader_font)
        label_pre.set_alignment(0, 0.5)
        #label_pre.set_size_request(200, 30)
        # preview player buttons
        self.btn_pre_play_pause = gtk.Button()
        self.btn_pre_play_pause.set_image(self.image_play)
        btn_pre_stop = gtk.Button()
        btn_pre_stop.set_image(image_stop)
         
        #Label of track to preview
        self.str_dur="00:00"
        self.label_pre_play = gtk.Label()
        self.label_pre_play.set_width_chars(20)
        self.label_pre_play.set_tooltip_text("")
        self.label_pre_time = gtk.Label("00:00 / 00:00")        
        #create a dictionary for holding details of message to play
        self.dict_pre = {}
        #hscale slider fer position in track
        #both lambdas toggle progressbar to be not updatable by player_pre while valve is dragged
        self.progress_pressed = lambda widget, param: self.player_pre.set_updateable_progress(False)

        self.hscale_pre = gtk.HScale() 
        self.hscale_pre.set_range(0, 100)
        self.hscale_pre.set_increments(1, 10)
        self.hscale_pre.set_digits(0)
        self.hscale_pre.set_draw_value(False)
        self.hscale_pre.set_update_policy(gtk.UPDATE_DISCONTINUOUS) 

        # the preview player
        self.player_pre = Preview_Player(self.label_pre_time, self.hscale_pre, self.reset_playbutton)
        
        sep_pre = gtk.HSeparator()

        ### Date and Time ###
        # date label
        self.label_date = gtk.Label()
        self.label_date.modify_font(subheader_font_2)
        #time label
        self.label_time = gtk.Label()
        self.label_time.modify_font(subheader_font_2)

        # countdown labels
        self.label_cdn_prg = gtk.Label("The next show starts in:")
        self.label_cdn_prg.set_tooltip_text("")
        self.label_cdn_time = gtk.Label()
        now = datetime.datetime.now()
        next_start_datetime = datetime.datetime.now()
        self.update_countdown(next_start_datetime)

        ### dnd and connections ###
        self.treeview_cat.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                              [("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_p3d_lst.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                              [("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_msg.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                              [("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_bc.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                              [("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_bc.enable_model_drag_dest([("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_msg.connect("drag_data_get", self.msg_drag_data_get_data)
        self.treeview_cat.connect("drag_data_get", self.cat_drag_data_get_data)
        self.treeview_p3d_lst.connect("drag_data_get", self.p3d_drag_data_get_data)
        self.treeview_bc.connect("drag_data_get", self.bc_drag_data_get_data)
        self.treeview_sch.connect("drag_data_get", self.sch_drag_data_get_data)
        self.treeview_bc.connect("drag_data_received",
                              self.drag_data_received_data)
        self.treeview_sch.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                      [("copy-row", 0, 0)], 
                                      gtk.gdk.ACTION_COPY)

        ### mouse button release for right-click menu

        self.treeview_msg.connect(
            'button-release-event', 
            self.right_click_msg_list_menu
            )
        self.treeview_cat.connect(
            'button-release-event', 
            self.right_click_cat_list_menu
            )
        self.treeview_p3d_lst.connect(
            'button-release-event', 
            self.right_click_p3d_list_menu
            )
        self.treeview_bc.connect(
            'button-release-event', 
            self.right_click_bc_list_menu
            )
        self.treeview_sch.connect(
            'button-release-event', 
            self.right_click_sch_list_menu
            )

        window.connect("delete_event", self.delete_event)
        window.connect("destroy", self.destroy)
        #sw_cat_list.connect("size-allocate", self.resize_check)
        notebook.connect("size-allocate", self.resize_check)
        notebook.connect('switch-page', self.get_p3d_browse)
        treeselection_msg.connect('changed', self.msg_selection_changed)
        treeselection_cat.connect('changed', self.cat_selection_changed)
        treeselection_p3d_browse.connect('changed', self.p3d_browse_selection_changed)
        treeselection_p3d_lst.connect('changed', self.p3d_selection_changed)
        btn_search_simple.connect("clicked", self.simple_search)
        self.entry_search_simple.connect("activate", self.simple_search)        
        btn_search_adv.connect("clicked", self.advanced_search)
        self.entry_search_artist.connect("activate", self.advanced_search)
        self.entry_search_album.connect("activate", self.advanced_search)
        self.entry_search_track.connect("activate", self.advanced_search)
        self.entry_search_cmpy.connect("activate", self.advanced_search)
        self.entry_search_genre.connect("activate", self.advanced_search)
        self.entry_search_com.connect("activate", self.advanced_search)
        self.entry_search_year.connect("activate", self.advanced_search)
    

        btn_p3d_select.connect("clicked", self.get_p3d)
        btn_p3d_copysel.connect("clicked", self.copy_p3d_sel)
        btn_p3d_copyall.connect("clicked", self.copy_p3d_all)
        treeselection_bc.connect('changed', self.bc_selection_changed)
        btn_testing.connect("clicked", self.test_bc)
        btn_inf.connect("clicked", self.info_row)
        btn_rem.connect("clicked", self.remove_row)
        btn_hist.connect("clicked", self.show_history)
        btn_skip.connect("clicked", self.skip_track)
        btn_msg_3hr.connect("clicked", self.show_msg_3hr)
        #btn_sch_refresh.connect("clicked", self.refresh_sch)
        btn_sch_now.connect("clicked",self.go_to_now)
        btn_sch_add.connect("clicked",self.add_sch_sel)
        self.btn_pre_play_pause.connect("clicked", self.play_pause_clicked)
        btn_pre_stop.connect("clicked", self.on_stop_clicked)
        treeselection_sch.connect('changed', self.sch_selection_changed)
        self.hscale_pre.connect("button-release-event", self.on_seek_changed)
        self.hscale_pre.connect("button-press-event", self.progress_pressed)
        
        ### do the packing ###
        sw_msg_lst.add(self.treeview_msg)
        sw_bc.add(self.treeview_bc)
        vbox_msg_btn.pack_end(sw_msg_btn, True)
        sw_msg_btn.add_with_viewport(self.vbox_sw_msg_btn)
        hbox_msg.pack_start(vbox_msg_btn, False)
        vbox_msg_lst.add(sw_msg_lst)
        hbox_msg.add(vbox_msg_lst)

        hbox_simple_search.pack_start(btn_search_simple, False)
        hbox_simple_search.pack_start(self.label_result_simple, False)

        table_search.attach(label_search_artist, 0, 1, 0, 1, False, False, 5, 0)
        table_search.attach(self.entry_search_artist, 1, 2, 0, 1, False, False, 5, 0)
        table_search.attach(label_search_track, 0, 1, 1, 2, False, False, 5, 0)
        table_search.attach(self.entry_search_track, 1, 2, 1, 2, False, False, 5, 0)
        table_search.attach(label_search_album, 0, 1, 2, 3, False, False, 5, 0)
        table_search.attach(self.entry_search_album, 1, 2, 2, 3, False, False, 5, 0)
        table_search.attach(label_search_cmpy, 0, 1, 3, 4, False, False, 5, 0)
        table_search.attach(self.entry_search_cmpy, 1, 2, 3, 4, False, False, 5, 0)
        table_search.attach(label_search_com, 0, 1, 4, 5, False, False, 5, 0)
        table_search.attach(self.entry_search_com, 1, 2, 4, 5, False, False, 5, 0)
        table_search.attach(label_search_genre, 0, 1, 5, 6, False, False, 5, 0)
        table_search.attach(self.entry_search_genre, 1, 2, 5, 6, False, False, 5, 0)
        table_search.attach(label_search_cpa, 0, 1, 6, 7, False, False, 5, 0)
        table_search.attach(self.entry_search_cpa, 1, 2, 6, 7, False, False, 5, 0)
        table_search.attach(label_search_year, 0, 1, 7, 8,  False, False, 5, 0)
        table_search.attach(self.entry_search_year, 1, 2, 7, 8,  False, False, 5, 0)        
        table_search.attach(label_search_creator, 0, 1, 8, 9,  False, False, 5, 0)
        table_search.attach(self.cb_search_creator, 1, 2, 8, 9,  False, False, 5, 0)  

        hbox_search_order.pack_start(label_search_order, False)
        hbox_search_order.pack_start(self.cb_search_order, False)
        hbox_search_max.pack_start(label_search_max, False)
        hbox_search_max.pack_start(self.spin_search_max, False)

        hbox_adv_search.pack_start(btn_search_adv, False)
        hbox_adv_search.pack_start(self.label_result_adv, False)

        vbox_cat_search.pack_start(sep_search_0, False)
        vbox_cat_search.pack_start(label_search_simple, False)
        vbox_cat_search.pack_start(self.entry_search_simple, False)
        vbox_cat_search.pack_start(hbox_simple_search, False)
        vbox_cat_search.pack_start(sep_search_1, False)
        vbox_cat_search.pack_start(label_search_adv, False)        
        vbox_cat_search.pack_start(table_search, False)        
        vbox_cat_search.pack_start(self.chk_search_comp, False)
        vbox_cat_search.pack_start(self.chk_search_demo, False)
        vbox_cat_search.pack_start(self.chk_search_local, False)
        vbox_cat_search.pack_start(self.chk_search_fem, False)
        vbox_cat_search.pack_start(self.chk_search_nr, False)
        vbox_cat_search.pack_start(hbox_search_order, False)
        vbox_cat_search.pack_start(hbox_search_max, False)          
        vbox_cat_search.pack_start(hbox_adv_search, False)     
        hbox_cat.pack_start(vbox_cat_search, False)    
        sw_cat_list.add(self.treeview_cat)
        vbox_search_lst.add(sw_cat_list)
        hbox_cat.pack_start(vbox_search_lst, True, True, 0)
    
        vbox_p3d_opt.pack_start(label_p3d_browse, False)
        sw_p3d_opt.add(self.treeview_p3d_browse)
        vbox_p3d_opt.pack_start(sw_p3d_opt, True)
        vbox_p3d_opt.pack_start(btn_p3d_select, False)
        hbox_p3d_btn.pack_start(btn_p3d_copysel, False)
        hbox_p3d_btn.pack_start(btn_p3d_copyall, False)
        hbox_p3d.pack_start(vbox_p3d_opt, False)
        sw_p3d_lst.add(self.treeview_p3d_lst)
        vbox_p3d_lst.pack_end(hbox_p3d_btn, False)
        vbox_p3d_lst.add(sw_p3d_lst)
        hbox_p3d.pack_start(vbox_p3d_lst, True)

        sw_sch.add(self.treeview_sch)
        hbox_sch.pack_start(label_sch, False)
        #hbox_sch.pack_start(btn_sch_refresh, False)
        hbox_sch.pack_start(btn_sch_now, False)
        hbox_sch.pack_start(btn_sch_add, False)
        vbox_sch.pack_start(hbox_sch, False)
        vbox_sch.pack_start(sw_sch, True, True, 0)
        
        hbox_pre_btn.pack_start(self.btn_pre_play_pause, False, False, 5)
        hbox_pre_btn.pack_start(btn_pre_stop, False, False, 5)
        hbox_pre_btn.pack_end(self.hscale_pre, True, True, 5)         
        vbox_pre.pack_start(label_pre, False, True, 5)
        vbox_pre.pack_start(hbox_pre_btn, False, False, 0)
        hbox_pre_play.pack_start(self.label_pre_play, False, False, 5)
        hbox_pre_play.pack_end(self.label_pre_time, False, False, 5)
        vbox_pre.pack_start(hbox_pre_play, False, False, 5)
        vbox_pre.pack_start(sep_pre, False, False, 0)
        
        vbox_pre.pack_start(hbox_pre_time, False, False, 5)
        hbox_pre_time.pack_start(self.label_date, False, True, 5)
        hbox_pre_time.pack_start(self.label_time, False, True, 5)
        hbox_pre_cdn.pack_start(self.label_cdn_prg, False, True, 5)
        hbox_pre_cdn.pack_start(self.label_cdn_time, False, True, 5)
        vbox_pre.pack_start(hbox_pre_cdn, False, False, 5)        
        # vbox_sch.pack_end(vbox_pre, False, False, 0)
        
        
        
        #vbox_nb.pack_start(vbox_sch, True, True, 0)       
        vbox_nb.pack_start(notebook, True, True, 5)
        notebook.append_page(hbox_msg, label_msg_btn)
        #notebook.append_page(hbox_cat, label_cat)
        notebook.append_page(hbox_p3d, label_p3d)
        vbox_bc.pack_start(label_bc, False)
        vbox_bc.pack_start(self.label_air, False)
        # uncomment next line for testing without serial signal
        ##vbox_bc.pack_start(btn_testing, False)
        vbox_bc.pack_start(self.progressbar, False)
        hbox_bc_0.pack_start(self.label_bc_time, True)
        hbox_bc_0.pack_start(self.label_bc_length, False, False, 5)
        hbox_bc_0.pack_end(btn_skip, False)
        
        
        hbox_bc_1.pack_start(btn_inf, False)
        hbox_bc_1.pack_start(btn_rem, False)
        hbox_bc_1.pack_start(btn_msg_3hr, False)
        hbox_bc_1.pack_start(btn_hist, False)
        hbox_bc_1.pack_start(self.spinbutton, False)
        hbox_bc_time.pack_end(self.label_time_1, False)
        hbox_bc_time.pack_end(label_time_0, False)
        #hbox_bc_2.pack_start(sw_bc, False, True, 0)
        vbox_bc.pack_start(hbox_bc_0, False)
        vbox_bc.pack_start(hbox_bc_1, False)
        #vbox_bc.pack_start(hbox_bc_2, True)
        vbox_bc.pack_start(sw_bc, True)
        vbox_bc.pack_start(hbox_bc_time, False)
        vbox_bc.pack_start(sep_bc_pre, False, False, 0)
        vbox_bc.pack_end(vbox_pre, False, False, 0)

        
        hbox_main.pack_start(vbox_nb, True, True, 0)
        hbox_main.pack_end(vbox_bc, False, False, 0)
        vbox_main.add(hbox_main)
        window.add(vbox_main)
        
        window.show_all()

        # Setup DBus Service
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        session_bus = dbus.SessionBus()
        name = dbus.service.BusName("com.threedradio.MessagePlayer", session_bus)
        object = MyDbus(session_bus, '/MyDbus') 
        
        gtk.gdk.threads_init()

        gtk.main()



    # columns for the lists
    def add_msg_columns(self, treeview_msg):
        '''
        columns for the list of messages
        '''
        # column ONE
        column = gtk.TreeViewColumn('CODE', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_clickable(False)
        column.set_fixed_width(66)
        self.treeview_msg.append_column(column)
        
        #Column TWO
        column = gtk.TreeViewColumn('Message', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width)
        treeview_msg.append_column(column)
        
        #Column THREE
        column = gtk.TreeViewColumn('Ending', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width)
        treeview_msg.append_column(column)
        
        #Column FOUR
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        column.set_fixed_width(70)
        treeview_msg.append_column(column)
        
    def add_bc_columns(self, treeview_bc):
        '''
        Columns for the broadcast list
        '''
        # column ONE
        column = gtk.TreeViewColumn(
            'ID', gtk.CellRendererText(), text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        self.treeview_bc.append_column(column)
        
        #Column TWO
        column = gtk.TreeViewColumn(
            'Artist Track', gtk.CellRendererText(), text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(200)
        self.treeview_bc.append_column(column)
        
        
        #Column THREE
        column = gtk.TreeViewColumn(
            'Time', gtk.CellRendererText(), text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        self.treeview_bc.append_column(column)


        #Column FOUR
        column = gtk.TreeViewColumn(
            'Joined', gtk.CellRendererToggle(), active=3)
        column.set_sort_column_id(3)
        column.set_visible(False)
        self.treeview_bc.append_column(column)        


        #Column FIVE
        cell_pix = CellRendererPixbufXt()
        cell_pix.connect("clicked", self.join_clicked)
        column = gtk.TreeViewColumn(
            'Join', cell_pix, pixbuf=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(40)
        self.treeview_bc.append_column(column)
        
    def add_sch_columns(self, treeview_sch):
        '''
        Columns for the schedule list
        '''
        # Column ONE
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                     text=0)
        column.set_sort_column_id(0)
        column.set_clickable(False)
        column.set_fixed_width(66)
        self.treeview_sch.append_column(column)
        
        # Column TWO
        column = gtk.TreeViewColumn('Programme Code', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        column.set_visible(False)
        self.treeview_sch.append_column(column) 

        # Column THREE
        column = gtk.TreeViewColumn('Programme', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width)
        self.treeview_sch.append_column(column)
        
        # Column FOUR
        column = gtk.TreeViewColumn('ID Code', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        column.set_visible(False)
        self.treeview_sch.append_column(column)
        
        # Column FIVE
        column = gtk.TreeViewColumn('Message', gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width)
        self.treeview_sch.append_column(column)       

    def add_search_columns(self, treeview):
        '''
        Columns for the catalogue search results list
        '''
        #Column ONE
        column = gtk.TreeViewColumn('ID', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)
                
        #Column TWO
        column = gtk.TreeViewColumn('Artist', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        #column.set_resizable(True)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width - 40)
        #column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        treeview.append_column(column)
       
        #Column THREE
        column = gtk.TreeViewColumn('Album/Title', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        #column.set_resizable(True)
        #column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width - 40)
        treeview.append_column(column)

        #Column FOUR
        column = gtk.TreeViewColumn('Quota', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(66)
        treeview.append_column(column)
        
        #Column FIVE
        column = gtk.TreeViewColumn('Length', gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(70)
        treeview.append_column(column)     

    def add_p3d_columns(self, treeview):
        '''
        columns for the playlist list
        '''
        #Column ONE
        column = gtk.TreeViewColumn('ID', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column) 

        #Column TWO
        column = gtk.TreeViewColumn('Artist', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width)
        treeview.append_column(column)

      #Column THREE
        column = gtk.TreeViewColumn('Title', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width)
        treeview.append_column(column)

        #Column FOUR
        column = gtk.TreeViewColumn('Quota', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(66)
        treeview.append_column(column)
        
        #Column FIVE
        column = gtk.TreeViewColumn('Length', gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(70)
        treeview.append_column(column)    
        
    # dnd    
    def msg_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        define drag n drop data retrieval for the message list.
        '''
        treeselection = treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        id_code = model.get_value(tree_iter, 0)
        dict_message = next(
            item for item in self.list_messages if item["code"] == id_code
            )
        pickle_data = pickle.dumps(dict_message)
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, pickle_data)

    def cat_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        Define drag n drop data retrieval for the catalogue list.
        '''
        treeselection = treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        trackid, tracklength = model.get(tree_iter, 0, 4)
        trackid = int(trackid)
        if tracklength:
            dict_search = next(
                (item for item in self.list_search if item['trackid'] == trackid)
                , None
                )

            if dict_search:
                pickle_data = pickle.dumps(dict_search)

            else:
                pickle_data = ""
        
        else:
            pickle_data = ""

        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, pickle_data)

    def p3d_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        Define drag n drop data retrieval for the playlist list - allows
        selecting multiple rows.
        '''
        '''
        copy the details from the hidden column of the selected row
        for drag n drop from the search results list.
        '''
        treeselection = treeview.get_selection()
        model = treeview.get_model()
        rows = treeselection.get_selected_rows()
        for row in rows:
            path = row[0]
        tree_iter = model.get_iter(path)
        trackid = model.get_value(tree_iter, 0)
        trackid = int(trackid)

        dict_playlist = next(
            item for item in self.list_playlist if item["trackid"] == trackid
            )
        pickle_data = pickle.dumps(dict_playlist)
            
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, pickle_data)

    def bc_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        Define drag n drop data retrieval for the broadcast list.
        '''
        treeselection = treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        pickle_data = model.get_value(tree_iter, 0)
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, pickle_data)
        model.remove(tree_iter)
        
    def sch_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        Define drag n drop data retrieval for the schedule list.
        '''
        treeselection = treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        id_code = model.get_value(tree_iter, 3)
        dict_schedule = next(
            item for item in self.list_schedule if item["code"] == id_code
            )
        pickle_data = pickle.dumps(dict_schedule)
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, pickle_data)
  
    def drag_data_received_data(self, treeview, context, x, y, selection,
                                info, etime):
        '''
        Adding data from drag n drop into the broadcast list.
        '''     
        list_data = []
        pickle_data = selection.get_text()
        model = treeview.get_model()

        if not pickle_data:
            str_error = "Did you just try to add a CD listing instead of a track?"
            self.error_dialog(str_error)
            return          
        
        dict_data = pickle.loads(pickle_data)
        tracktype = dict_data['tracktype']


        filepath = self.get_filepath(dict_data, tracktype)
        if not filepath:
            #display error message and return
            str_error = "Unable to add to the list, the audio file does not exist. \
                You may wish to check the details and rip that CD into the music store"
            self.error_dialog(str_error)
            return
            #for testing do nothing

        elif filepath and tracktype == "mus":
            tracktitle = dict_data['tracktitle']
            trackartist = dict_data['trackartist']
            artist = dict_data['artist']
            if not trackartist:
                trackartist = artist
            
            tracktitle = trackartist + '\n' + tracktitle
        
            int_time = dict_data['tracklength'] 

        elif filepath and tracktype == "msg":
            title = dict_data['title']
            msg_type = dict_data['type']
            tracktitle = msg_type + '\n' + title
            int_time = dict_data['duration']
            
            
        tracktime = self.convert_time(int_time)
        path_img = dir_img + img_blank        
        px = gtk.gdk.pixbuf_new_from_file(path_img)   
        
        list_data = (pickle_data, tracktitle, tracktime, False, px)    
            

        drop_info = treeview.get_dest_row_at_pos(x, y)
        if drop_info:                
            path, position = drop_info
            tree_iter = model.get_iter(path)
            if (position == gtk.TREE_VIEW_DROP_BEFORE
                or position == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                model.insert_before(tree_iter, list_data)
                self.join_drop(model, tree_iter, True)

            else:
                model.insert_after(tree_iter, list_data)
                self.join_drop(model, tree_iter, False)
                
        else:
            model.append(list_data)
        if context.action == gtk.gdk.ACTION_MOVE:
            context.finish(True, True, etime)

        self.update_time_total()                    
        iter_top = model.get_iter_first()        
        if model.iter_next(iter_top):
            self.refresh_list(model)       

    # message section
    def pg_connect_msg(self):
        '''
        connect to the message database
        '''
        #connection variables
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            pg_msg_database, pg_msg_user, pg_server, pg_msg_password)
        conn = psycopg2.connect(conn_string)
        #cur = conn.cursor()
        return conn
    
    def get_types(self):
        '''
        query the database for the different types of messages
        '''
        query = "SELECT type,description FROM typelist ORDER BY type"
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        type_rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return type_rows
    
    def make_buttons(self):
        '''
        create a button for each type of message
        '''
        ls_btn = self.vbox_sw_msg_btn.get_children()
        if ls_btn:
            for item in ls_btn:
                self.vbox_sw_msg_btn.remove(item)
                
        type_rows = self.get_types()

        for msg_type in type_rows:
            button_id = msg_type[0]
            button = gtk.Button(button_id, None, False)
            #button.set_size_request(215, 30)
            tooltip = msg_type[1]
            button.set_tooltip_text(tooltip)
            button.connect("clicked", self.msg_btn_clicked, button_id)
            self.vbox_sw_msg_btn.pack_start(button, False)

    def msg_btn_clicked(self, clicked, msg_type):
        """
        When a button is clicked get messages of that type and 
        display them in the list
        """
        db = 'msglist'
        query, search_terms = self.query_type(msg_type)
        messages = self.execute_query(db, query, search_terms)
        self.new_msg_list(messages)
        
    def query_type(self, msg_type):
        '''
        create query of the database for messages of a given type
        '''
        today = datetime.date.today()
        
        search_terms = (msg_type, today)
        query = sql.SQL("SELECT * FROM messagelist WHERE LOWER(type)=LOWER({}) AND expirydate > {} ORDER BY title").format(
            sql.Placeholder(name = 'msg_type'),
            sql.Placeholder(name = 'today')
        )

        search_terms = {'msg_type':msg_type, 'today':today}
        return (query, search_terms)
        
    def new_msg_list(self, messages):
        '''
        populate the message list with messages of the given type that 
        were retrieved from the database
        '''
        self.list_messages = []
        model = self.treeview_msg.get_model()     
        #clear existing rows
        model.clear()
         
        #add new rows
        for dict_message in messages:
            dict_message['tracktype'] = "msg"
            dict_message['tracklength'] = dict_message['duration']
            code = dict_message['code']
            title = dict_message['title']
            nq = dict_message['nq']
            duration = dict_message['duration']

            if duration:
                time = self.convert_time(duration)
            else:
                time = "NA"

            row = (code, title, nq, time)
            model.append(row)
            self.list_messages.append(dict_message)

    # music catalogue section       
    def pg_connect_cat(self):
        '''
        connect to the catalogue database
        '''
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            pg_cat_database, pg_cat_user, pg_server, pg_cat_password)
        conn = psycopg2.connect(conn_string)
        #cur = conn.cursor()
        return conn

    def simple_search(self, widget):
        '''
        run functions to query the database and add the results to the 
        catalogue list
        '''
        searchitem = self.entry_search_simple.get_text()
        str_error_none = "No search terms were entered"

        if not searchitem:
            self.error_dialog(str_error_none)
            return False

        searchitem =  self.add_percent(searchitem)

        search_terms = {}
        for item in where_items:
            search_terms[item] = searchitem

        db = "threed"
        query = self.query_simple(search_terms)
        result = self.execute_query(db, query, search_terms)

        simple = True
        if result:
            
            dict_data = self.process_result(result)
            self.add_to_search_store(dict_data)
            self.list_search = dict_data
            self.length_check(result)

            int_res = len(result)
           
        else:
            self.clear_search_list()
            int_res = 0
            
        self.update_result_label(int_res, simple)
                                
    def query_simple(self, search_terms):
        '''
        queries the database for matches to the simple search string in title 
        and artist columns for CDs and CD tracks. References global variables
        'select_items' and 'where_items'
        '''    
        select_statement = sql.SQL("SELECT")
        
        for i, item in enumerate(select_items):
            table, column = item.split(".")
            table = sql.Identifier(table)
            column = sql.Identifier(column)
            identifier = sql.SQL("{}.{}").format(table, column)
            if i == 0:
                select_statement = sql.SQL(' ').join([select_statement, identifier])
            else:
                select_statement = sql.SQL(', ').join([select_statement, identifier])
        
        from_statement = sql.SQL("FROM {} INNER JOIN {} ON {}.{}={}.{} LEFT OUTER JOIN {} ON {}.{}={}.{}").format(
        sql.Identifier("cdtrack"),
        sql.Identifier("cd"),
        sql.Identifier("cdtrack"),
        sql.Identifier("cdid"),
        sql.Identifier("cd"),
        sql.Identifier("id"),
        sql.Identifier("cdcomment"),
        sql.Identifier("cdtrack"),
        sql.Identifier("cdid"),
        sql.Identifier("cdcomment"),
        sql.Identifier("cdid"),
        )

        where_statement = sql.SQL("WHERE")
        for i, item in enumerate(search_terms):
            table, column = item.split(".")
            table = sql.Identifier(table)
            column = sql.Identifier(column)
            placeholder = sql.Placeholder(name = item)
            value = search_terms[item]

            if i > 0:
                or_statement = sql.SQL("OR")
                where_statement = sql.SQL(' ').join([where_statement, or_statement])


            ilike_search = sql.SQL("{}.{} ILIKE {} ESCAPE ''").format(table, column, placeholder)
            where_statement = sql.SQL(' ').join([where_statement, ilike_search])

        order_statement = sql.SQL("ORDER BY")
        order_sql_list = []
        ordering_items = (("artist", "ASC"), ("id", "DESC"))
        for item in ordering_items:
            table, direction = item
            if direction == "DESC":
                order_sql = sql.SQL("{}.{} DESC").format(
                sql.Identifier("cd"),
                sql.Identifier(table)
                )
            elif direction == "ASC":
                order_sql = sql.SQL("{}.{} ASC").format(
                sql.Identifier("cd"),
                sql.Identifier(table)
                )
            order_sql_list.append(order_sql)
        order_sql = sql.SQL("{}.{}").format(
            sql.Identifier("cdtrack"),
            sql.Identifier("tracknum")
            )
        order_sql_list.append(order_sql)
        order_sql = sql.SQL(", ").join(order_sql_list)
        order_statement = sql.SQL(" ").join([order_statement, order_sql])
        
        query_limit = self.spin_search_max.get_value_as_int()
        limit_statement = sql.SQL("LIMIT {}").format(
            sql.Literal(query_limit)
        )

        query = sql.SQL(' ').join([
            select_statement, 
            from_statement, 
            where_statement, 
            order_statement, 
            limit_statement])
        
        # show the query for debugging
        #conn = self.pg_connect_cat()
        #query_string = query.as_string(conn)
        #print(query_string)
        #conn.close()

        return query

    def length_check(self, result):
        '''
        Display a message if the number of results returned is the maximum
        '''
        query_limit = self.spin_search_max.get_value_as_int()

        if len(result) == query_limit:
            str_warn_0 = "Warning - your search returned the maximum of"
            str_warn_1 = "results. You can increase the maximum to see more results or"
            str_warn_2 = "modify your search to narrow it down."
            #str_warn = str_warn_0 + str(query_limit) + str_warn_1 + str(query_limit) + str_warn_2
            str_warn = "{0} {3} {1} {2}".format(
                str_warn_0,
                str_warn_1,
                str_warn_2,
                query_limit
            )
            self.warn_dialog(str_warn)

    def add_to_search_store(self, dict_data):
        '''
        populate the catalogue list with the results of a search
        '''
        self.clear_search_list()
        var_album = ""
            
        for item in dict_data:
            model = self.treeview_cat.get_model()
            
            trackid = item['trackid']
            cdid = item['cdid']
            album = item['title']
            tracktitle = item['tracktitle']
            artist = item['artist']
            if item['trackartist']:
                trackartist = item['trackartist']
            else:
                trackartist = item['artist']
            
            int_time = item['tracklength']
            int_time = int(int_time)
            dur_time = self.convert_time(int_time)
            #artist_album = artist + '\n' + album
            
            # include quota details
            quota = "  "
            local = item["local"]
            if not local:
                local = "?  "
            elif local == 0:
                local = "?  "
            elif local == 1:
                local = "-  "
            elif local == 2:
                local = "L  "
            elif local == 3:
                local = "S  "
            #local = unys[local]
            quota += local
            
            female = item["female"]
            if not female:
                female = "?  "
            if female == 0:
                female = "?  "
            elif female == 1:
                female = "-  "
            elif female == 2:
                female = "F  "
            elif female == 3:
                female = "S  "
            quota += female    
                    
            if not album:
                album = "(No Title)"

            if not album == var_album:
                # create a pickle of dictionary for the CD row.
                cd_dict = dict(item)
                for item in select_items:
                    table, column = item.split(".")
                    if table == "cdtrack" and column != "cdid":
                        del cd_dict[column]
                    cd_pickle = pickle.dumps(cd_dict)


                n = model.append(None, [cdid, artist, album, quota, ""])
                model.append(n, [trackid, trackartist, tracktitle, "", dur_time])
            else:
                model.append(n, [trackid, trackartist, tracktitle, "", dur_time])
            var_album = album
        
    def advanced_search(self, widget):
        '''
        run functions to get the advanced search input, query the database 
        and display the results
        '''
        simple = False
        result = False
        self.list_search = []
        search_terms = self.get_search_terms()

        if search_terms:
            db = 'threed'
            query = self.create_query(search_terms)
            result = self.execute_query(db, query, search_terms)

        if result:
            dict_data = self.process_result(result)
            self.add_to_search_store(dict_data)
            self.list_search = dict_data
            self.length_check(result)

            int_res = len(result)
            
        else:
            self.clear_search_list()
            int_res = 0
        
  
        self.update_result_label(int_res, simple)
        
    def get_search_terms(self):
        '''
        Make a query to the catalogue database based on the user input. 
        Return the results.
        '''
        #obtain text from entries and combos and add to parameter dictionary
        search_terms = {}
        
        artist = self.entry_search_artist.get_text()
        if artist:
            artist = self.add_percent(artist)
            search_terms["cd.artist"] = artist
            
        album = self.entry_search_album.get_text()
        if album:
            album = self.add_percent(album)
            search_terms["cd.title"] = album
            
        track = self.entry_search_track.get_text()
        if track:
            track = self.add_percent(track)
            search_terms["cdtrack.tracktitle"] = track
            
        company = self.entry_search_cmpy.get_text()
        if company:
            company = self.add_percent(company)
            search_terms["cd.company"] = company
                        
        comments = self.entry_search_com.get_text()
        if comments:
            comments = self.add_percent(comments)
            search_terms["cdcomment.comment"] = comments
                                
        genre = self.entry_search_genre.get_text()
        if genre:
            genre = self.add_percent(genre)
            search_terms["cd.genre"] = genre
            
        cpa = self.entry_search_cpa.get_text()
        if cpa:
            cpa = self.add_percent(cpa)
            search_terms["cd.cpa"] = cpa
            
        year = self.entry_search_year.get_text()
        if year:
            try:                        
                year = int(year)
                search_terms["cd.year"] = year
            except ValueError:
                str_error = '''
                Not a valid year
                '''
                self.error_dialog(str_error)
                return False
                        
        creator = self.cb_search_creator.get_active_text()
        if creator:
            # let's hope for the interim that we do not get
            # two  members who have the same name ...
            for id in self.dict_creator.keys():
                if self.dict_creator[id] == creator:
                    created_by = id 
            search_terms["cd.createwho"] = created_by
                        
        compil = self.chk_search_comp.get_active()
        if compil:
            search_terms["cd.compilation"] = 2
                        
        demo = self.chk_search_demo .get_active()
        if demo:
            search_terms["cd.demo"] = 2

        local = self.chk_search_local.get_active()
        if local:
            search_terms["cd.local"] = 2

        female = self.chk_search_fem.get_active()
        if female:
            search_terms["cd.female"] = 2
            
        new_release = self.chk_search_nr.get_active()
        if new_release:
            today = datetime.date.today()
            nr_delta = datetime.timedelta(days=60)
            nr = today - nr_delta
            search_terms["cd.arrivaldate"] = nr 
        
        str_error_none = "I can't see what you are searching for"
        str_error_len = "Please enter more than one character in your search"
        
        if not (artist or album or track or company or comments or creator or genre or new_release or year or cpa):
            self.error_dialog(str_error_none)
            return False
            

        return search_terms
        
        '''
        # comment this out for now.
            
        for item in (artist, album, track, company, comments, genre):
            if item:
                if len(item) < 2:
                    self.error_dialog(str_error_len)
                    return False
        '''            

    def create_query(self, search_terms):
        select_statement = sql.SQL("SELECT")
        
        for i, item in enumerate(select_items):
            table, column = item.split(".")
            table = sql.Identifier(table)
            column = sql.Identifier(column)
            identifier = sql.SQL("{}.{}").format(table, column)
            if i == 0:
                select_statement = sql.SQL(' ').join([select_statement, identifier])
            else:
                select_statement = sql.SQL(', ').join([select_statement, identifier])
        
        from_statement = sql.SQL("FROM {} INNER JOIN {} ON {}.{}={}.{} LEFT OUTER JOIN {} ON {}.{}={}.{}").format(
        sql.Identifier("cdtrack"),
        sql.Identifier("cd"),
        sql.Identifier("cdtrack"),
        sql.Identifier("cdid"),
        sql.Identifier("cd"),
        sql.Identifier("id"),
        sql.Identifier("cdcomment"),
        sql.Identifier("cdtrack"),
        sql.Identifier("cdid"),
        sql.Identifier("cdcomment"),
        sql.Identifier("cdid"),
        )

        where_statement = sql.SQL("WHERE")
        for i, item in enumerate(search_terms):
            table, column = item.split(".")
            table = sql.Identifier(table)
            column = sql.Identifier(column)
            placeholder = sql.Placeholder(name = item)
            value = search_terms[item]
            
            if i > 0:
                and_statement = sql.SQL("AND")
                where_statement = sql.SQL(' ').join([where_statement, and_statement])
            if item == "cd.artist":
                artist_search = sql.SQL("({}.{} ILIKE {} ESCAPE '' OR {}.{} ILIKE {} ESCAPE '')").format(
                    table,
                    column,
                    placeholder,
                    sql.Identifier("cdtrack"),
                    sql.Identifier("trackartist"),
                    placeholder
                    )
                where_statement = sql.SQL(' ').join([where_statement, artist_search])
            
            elif isinstance(value, str):
                ilike_search = sql.SQL("{}.{} ILIKE {} ESCAPE ''").format(table, column, placeholder)
                where_statement = sql.SQL(' ').join([where_statement, ilike_search])
            elif item == "cd.arrivaldate":
                ge_search = sql.SQL("{}.{} >= {}").format(table, column, placeholder)
                where_statement = sql.SQL(' ').join([where_statement, ge_search])
            else:
                eq_search = sql.SQL("{}.{} = {}").format(table, column, placeholder)
                where_statement = sql.SQL(' ').join([where_statement, eq_search])

        order_statement = sql.SQL("ORDER BY")
        order_sql_list = []
        order_by_text = self.cb_search_order.get_active_text()
        ordering_items = order_results[order_by_text]
        for item in ordering_items:
            table, direction = item
            if direction == "DESC":
                order_sql = sql.SQL("{}.{} DESC").format(
                sql.Identifier("cd"),
                sql.Identifier(table)
                )
            elif direction == "ASC":
                order_sql = sql.SQL("{}.{} ASC").format(
                sql.Identifier("cd"),
                sql.Identifier(table)
                )
            order_sql_list.append(order_sql)
        order_sql = sql.SQL("{}.{}").format(
            sql.Identifier("cdtrack"),
            sql.Identifier("tracknum")
            )
        order_sql_list.append(order_sql)
        order_sql = sql.SQL(", ").join(order_sql_list)
        order_statement = sql.SQL(" ").join([order_statement, order_sql])
        
        query_limit = self.spin_search_max.get_value_as_int()
        limit_statement = sql.SQL("LIMIT {}").format(
            sql.Literal(query_limit)
        )

        query = sql.SQL(' ').join([select_statement, from_statement, where_statement, order_statement, limit_statement])
        return query
        

        
    def execute_query(self, db, query, search_terms):
        
        if db == 'threed':
            conn = self.pg_connect_cat()
        
        elif db == 'msglist':
            conn = self.pg_connect_msg()
        
        else:
            return
        
        # show the query for debugging
        #query_string = query.as_string(conn)
        #print(query_string)

        dict_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        dict_cur.execute(query, (search_terms))
        result = dict_cur.fetchall()
        
        dict_cur.close()
        conn.close()  
        

        # convert the results to a true dictionary
        result = [{k:v for k, v in record.items()} for record in result]
        return result

    def process_result(self, result):
        dict_data = []
        first = True
        separator = '''
        -----------------------
        '''
        for item in result:
            item['tracktype'] = 'mus'
            if first:
                dict_data.append(item)
                first = False
            else:
                if item["trackid"] == dict_data[-1]["trackid"]:
                    dict_data[-1]["comment"] = dict_data[-1]["comment"] + separator + item["comment"]
                else:
                    dict_data.append(item)
            
        return dict_data

    def add_percent(self, parameter):
        '''
        wrap the string with percentage signs for 'ILIKE' query, avoiding 
        conflict with the symbol for substitution when defining parameters
        '''
        l = ('%', parameter, '%')
        percented = ''.join(l)
        return percented

    def get_dict_creator(self):
        '''
        Query the database for the list of members who have added data to the 
        catalogue
        '''
        query = "SELECT DISTINCT cd.createwho, users.first, users.last FROM "\
        "cd JOIN users ON cd.createwho = users.id ORDER BY users.last"
        conn = self.pg_connect_cat()
        cur = conn.cursor()
        cur.execute(query)
        list_creator = cur.fetchall()
        cur.close()
        conn.close()
        dict_creator = {}
        for creator in list_creator:
            num = int(creator[0])
            first = creator[1].lower()
            second = creator[2].lower()
            fullname = first + " " + second

            dict_creator[num] = fullname

        return(dict_creator)        

    def cb_search_creator_add(self, dict_creator):
        '''
        Populate the drop down list in the catalogue advanced search with the 
        names of members who have added data to the catalogue
        '''
        liststore_creator = gtk.ListStore(str)        
        list_creator =  sorted(dict_creator.values())
        for item in list_creator:
            self.cb_search_creator.append_text(item)
        self.cb_search_creator.prepend_text("")
        self.cb_search_creator.append_text("")

    def get_order(self):
        '''
        not yet implemented - for determining the order in which to display
        search results
        '''
        model = self.cb_search_order.get_model()
        active = self.cb_search_order.get_active()
        if active < 0:
          return None
        return model[active][0]

    def cb_order_add(self):
        '''
        Populate a drop down box with details of the 
        order in which to display search results
        '''
        list_order = order_results.keys()
        list_order.sort()
        for item in list_order:
            self.cb_search_order.append_text(item)
        self.cb_search_order.set_active(0)

    def clear_search_list(self):
        '''
        Clear the cataloge list of all search results 
        '''
        model = self.treeview_cat.get_model()
        model.clear()

    def update_result_label(self, int_res, simple):

        str_results = "{0} results".format(int_res)
        if simple:
            self.label_result_simple.set_text(str_results)
            self.label_result_adv.set_text("")
        else:
            self.label_result_adv.set_text(str_results)
            self.label_result_simple.set_text("")  
 
    # list import section (p3d)
    def get_p3d_browse(self, notebook, tab, index):
        if index == 2:
            self.store_p3d_browse.clear()
            parents = {}
            for top_dir, dirs, files in os.walk(dir_p3d):
                dirs.sort()
                files.sort()
                for subdir in dirs:
                    parents[os.path.join(top_dir, subdir)] = self.store_p3d_browse.append(parents.get(top_dir, None), [subdir])
                for item in files:
                    if item.endswith('.p3d'):
                        self.store_p3d_browse.append(parents.get(top_dir, None), [item])

    def get_p3d(self, widget):
        '''
        open a file chooser window to select a playlist file
        '''
        action = gtk.FILE_CHOOSER_ACTION_OPEN
        btn = gtk.STOCK_OPEN
        rsp = gtk.RESPONSE_OK
                        
        dialog = gtk.FileChooserDialog("Select the Message to Add",
                                       None,
                                       action,
                                       (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                        btn, rsp)
                                        )

        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_current_folder(dir_p3d)
        dialog.set_do_overwrite_confirmation(True)

        filter = gtk.FileFilter()
        filter.set_name("Playlist files")
        filter.add_pattern("*.p3d")

        dialog.add_filter(filter)

        response = dialog.run()
        filename = dialog.get_filename()
        if response == gtk.RESPONSE_OK:
            self.load_playlist(filename)
        dialog.destroy()

    def load_playlist(self, filepath):
        self.list_playlist = []
        ls_data = pickle.load(open(filepath, "rb"))
        model = self.treeview_p3d_lst.get_model()
        model.clear()
        for dict_data in ls_data:
            dict_data['tracktype'] = 'mus'
            int_time = dict_data['tracklength']
            tracktime = self.convert_time(int_time)
            tracktitle = dict_data['tracktitle']
            trackartist = dict_data['trackartist']
            trackid = dict_data['trackid']
            
            if not trackartist:
                artist = dict_data['artist']
                trackartist = artist
                
            # include quota details
            quota = "  "
            local = dict_data["local"]
            if not local:
                local = "?  "
            elif local == 0:
                local = "?  "
            elif local == 1:
                local = "-  "
            elif local == 2:
                local = "L  "
            elif local == 3:
                local = "S  "
            quota += local
            
            female = dict_data["female"]
            if not female:
                female = "?  "
            if female == 0:
                female = "?  "
            elif female == 1:
                female = "-  "
            elif female == 2:
                female = "F  "
            elif female == 3:
                female = "S  "
            quota += female
            
            self.list_playlist.append(dict_data)
                
            model.append((trackid, trackartist, tracktitle, quota, tracktime))
            
            self.update_time_total()

    def p3d_browse_selection_changed(self, selection):
        model, path = selection.get_selected_rows()
        if (path):
            tree_iter = model.get_iter(path[0])
            filepath = self.add_playlist(model, tree_iter)
            if filepath and os.path.isfile(filepath):
                self.load_playlist(filepath)  
        
    def add_playlist(self, model, tree_iter):

        if model.iter_has_child(tree_iter):
            return

        file_p3d = model.get_value(tree_iter, 0)
        
        while tree_iter:
            tree_iter = model.iter_parent(tree_iter)
            if tree_iter:
                parent_dir = model.get_value(tree_iter, 0)
                file_p3d = os.path.join(parent_dir, file_p3d)
                filepath = os.path.join(dir_p3d, file_p3d)
                
            else:
                filepath = os.path.join(dir_p3d, file_p3d)
        return filepath
                  
    def copy_p3d_sel(self, widget):
        '''
        Copy the selected tracks in the playlist to the broadcast list
        '''
        model_bc = self.treeview_bc.get_model()
        filepath_error = False
        treeselection = self.treeview_p3d_lst.get_selection()
        model = self.treeview_p3d_lst.get_model()
        rows = treeselection.get_selected_rows()
        row = rows[1]
        for path in row:
            tree_iter = model.get_iter(path)
            trackid = model.get_value(tree_iter, 0)
            trackid = int(trackid)
            copied = self.p3d_to_bc(trackid)
            if not copied:
                filepath_error = True

        self.update_time_total() 
        if filepath_error:
            error_message = "Not able to copy over all selected tracks"
            self.error_dialog(error_message)
            
    def copy_p3d_all(self, widget):
        model = self.treeview_p3d_lst.get_model()
        tree_iter = model.get_iter_first()
        filepath_error = False

        while tree_iter:
            trackid = model.get_value(tree_iter, 0)
            trackid = int(trackid)
            copied = self.p3d_to_bc(trackid)
            if not copied:
                filepath_error = True
            tree_iter = model.iter_next(tree_iter)
        
        self.update_time_total()
        if filepath_error:
            error_message = "Not able to copy over all tracks"
            self.error_dialog(error_message)                           
        
    def p3d_to_bc(self, trackid):        
        '''
        copy multiple tracks from the playlist to the broadcast list
        '''
        model = self.treeview_bc.get_model()
        dict_playlist = next(
            (item for item in self.list_playlist if item['trackid'] == trackid), 
            None
            )
        if dict_playlist:
            tracktype = 'mus'
            filepath = self.get_filepath(dict_playlist, tracktype)

            if not os.path.isfile(filepath):
                return False

            else:
                tracktitle = dict_playlist['tracktitle']
                trackartist = dict_playlist['trackartist']
                artist = dict_playlist['artist']
                if not trackartist:
                    trackartist = artist
                
                tracktitle = trackartist + '\n' + tracktitle
            
                int_time = dict_playlist['tracklength']
                tracktime = self.convert_time(int_time)
                path_img = dir_img + img_blank        
                px = gtk.gdk.pixbuf_new_from_file(path_img)   
                pickle_data = pickle.dumps(dict_playlist)
                list_data = (pickle_data, tracktitle, tracktime, False, px)
                model.append(list_data)
                return True
            
    # broadcast section        
    def remove_row(self, widget):    
        treeselection = self.treeview_bc.get_selection()
        model, tree_iter = treeselection.get_selected()
        if tree_iter:
            model.remove(tree_iter) 
            model = self.treeview_bc.get_model()
        else:
            print("Nothing selected")
        tree_iter = model.get_iter_first()
        if tree_iter:
            self.refresh_list(model)
        self.update_time_total()
        
    def info_row(self, widget):    
        treeselection = self.treeview_bc.get_selection()
        model, tree_iter = treeselection.get_selected()
        pickle_data = model.get_value(tree_iter, 0)
        dict_data = pickle.loads(pickle_data)

        if dict_data['tracktype'] == "msg":
            self.display_message_details(dict_data)
        
        elif  dict_data['tracktype'] == "mus":
            self.display_track_details(dict_data, False)
        
    def show_history(self, widget):
        history_log = self.query_history_log()
        if history_log:
            history_list = self.query_history(history_log)
            if history_list:
                self.display_history(history_log, history_list)

    def query_history_log(self):
        value = self.spinbutton.get_value_as_int()
        fqhn = socket.gethostname()
        hostname = fqhn.split(".")[0]
        id_type = 'mus'
        search_terms = (id_type, hostname, value)

        query = sql.SQL("SELECT {}, {} FROM {} WHERE {} = %s and {} = %s ORDER BY when_played DESC LIMIT %s").format(
            sql.Identifier('when_played'),
            sql.Identifier('id_code'),
            sql.Identifier('playlog'),
            sql.Identifier('id_type'),
            sql.Identifier('hostname')
            )

        db = 'msglist'
        history_log = self.execute_query(db, query, search_terms)

        return history_log
        
    def query_history(self, history_log):
        '''
        query the music database from the results of the history log query
        '''
        select_items = (
            "cdtrack.trackid",
            "cdtrack.cdid",
            "cdtrack.tracknum",
            "cdtrack.tracktitle",
            "cdtrack.trackartist",
            "cd.artist",
            "cd.title",
            "cd.year",
            "cd.createwhen",
            "cd.local",
            "cd.female",
            "cdtrack.tracklength"
            )        
        search_terms = []
        for result in history_log:
            search_terms.append(result['id_code'])

        select_statement = sql.SQL("SELECT")
        for i, item in enumerate(select_items):
            table, column = item.split(".")
            table = sql.Identifier(table)
            column = sql.Identifier(column)
            identifier = sql.SQL("{}.{}").format(table, column)
            if i == 0:
                select_statement = sql.SQL(' ').join([select_statement, identifier])
            else:
                select_statement = sql.SQL(', ').join([select_statement, identifier])

        from_statement = sql.SQL("FROM {} INNER JOIN {} ON {}.{}={}.{}").format(
        sql.Identifier("cdtrack"),
        sql.Identifier("cd"),
        sql.Identifier("cdtrack"),
        sql.Identifier("cdid"),
        sql.Identifier("cd"),
        sql.Identifier("id")
        )

        where_statement = sql.SQL("WHERE")
        for i, item in enumerate(search_terms):
            id_statement = sql.SQL("{} = %s").format(
                    sql.Identifier('trackid')
                )
            if i == 0:
                where_statement = sql.SQL(' ').join([
                    where_statement, 
                    id_statement
                    ])
            else:
                where_statement = sql.SQL(' OR ').join([
                    where_statement, 
                    id_statement
                    ]) 

        query = sql.SQL(' ').join([
            select_statement, 
            from_statement, 
            where_statement
            ])
        db = 'threed'
        history_list = self.execute_query(db, query, search_terms)
        return history_list

    
    def display_history(self, history_log, history_list):
        dialog = gtk.Dialog(
            "History", 
            None, 
            gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_NO_SEPARATOR, 
            buttons=None
            )    
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        sw.set_size_request(280, 360)
        dialog.vbox.pack_start(sw, True, True, 0)
        length = len(history_log) * 7
        table_played = gtk.Table(length, 2, False)
        sw.add_with_viewport(table_played)

        #history_log = history_log.sort()
        n = 0
        for item in history_log:
            when_played = item['when_played'].strftime("%I:%M %p %d/%m/%Y")
            trackid = int(item['id_code'])
            history_item = next(
                played for played in history_list if played['trackid'] == trackid
                )
            artist = history_item['artist']
            trackartist = history_item['trackartist']
        
            if not trackartist:
                trackartist = artist

            tracktitle  = history_item['tracktitle']
            title  = history_item['title']        
            tracklength = history_item['tracklength']
            str_time = self.convert_time(tracklength)

            local = history_item['local']
            female = history_item['female']

            quota = "  "

            if not local:
                local = "?  "
            elif local == 0:
                local = "?  "
            elif local == 1:
                local = "-  "
            elif local == 2:
                local = "L  "
            elif local == 3:
                local = "S  "

            quota += local
            
            if not female:
                female = "?  "
            if female == 0:
                female = "?  "
            elif female == 1:
                female = "-  "
            elif female == 2:
                female = "F  "
            elif female == 3:
                female = "S  "
            quota += female    

            label_detail_when = gtk.Label()
            label_detail_when.set_text("When Played: ")
            label_detail_when.set_alignment(0, 0.5)
            table_played.attach(label_detail_when, 0, 1, n, n + 1, False, False, 5, 0)
            
            label_when = gtk.Label()
            label_when.set_text(when_played)
            label_when.set_selectable(True)
            label_when.set_alignment(0, 0.5)
            table_played.attach(label_when, 1, 2, n, n + 1, False, False, 5, 0)

            n += 1

            label = gtk.Label()
            label.set_text("Artist: ")
            label.set_alignment(0, 0.5)
            table_played.attach(label, 0, 1, n, n + 1, False, False, 5, 0)
            
            label = gtk.Label()
            label.set_text(trackartist)
            label.set_selectable(True)
            label.set_alignment(0, 0.5)
            table_played.attach(label, 1, 2, n, n + 1, False, False, 5, 0)
            n += 1

            label = gtk.Label()
            label.set_text("Track: ")
            label.set_alignment(0, 0.5)
            table_played.attach(label, 0, 1, n, n + 1, False, False, 5, 0)
            
            label = gtk.Label()
            label.set_text(tracktitle)
            label.set_selectable(True)
            label.set_alignment(0, 0.5)
            table_played.attach(label, 1, 2, n, n + 1, False, False, 5, 0)
            n += 1

            label = gtk.Label()
            label.set_text("Album: ")
            label.set_alignment(0, 0.5)
            table_played.attach(label, 0, 1, n, n + 1, False, False, 5, 0)
            
            label = gtk.Label()
            label.set_text(title)
            label.set_selectable(True)
            label.set_alignment(0, 0.5)
            table_played.attach(label, 1, 2, n, n + 1, False, False, 5, 0)
            n += 1

            label = gtk.Label()
            label.set_text("Length: ")
            label.set_alignment(0, 0.5)
            table_played.attach(label, 0, 1, n, n + 1, False, False, 5, 0)
            
            label = gtk.Label()
            label.set_text(str_time)
            label.set_selectable(True)
            label.set_alignment(0, 0.5)
            table_played.attach(label, 1, 2, n, n + 1, False, False, 5, 0)
            n += 1

            label = gtk.Label()
            label.set_text("Quotas: ")
            label.set_alignment(0, 0.5)
            table_played.attach(label, 0, 1, n, n + 1, False, False, 5, 0)
            
            label = gtk.Label()
            label.set_text(quota)
            label.set_selectable(True)
            label.set_alignment(0, 0.5)
            table_played.attach(label, 1, 2, n, n + 1, False, False, 5, 0)
            n += 1

            separator = gtk.HSeparator()
            label.set_alignment(0, 5)
            table_played.attach(separator, 0, 2, n, n + 1, False, True, 5, 10)
            n += 1

        #sw.add_with_viewport(table_played)
        #dialog.vbox.pack_start(sw, True)
        dialog.show_all()

        width = table_played.allocation.width + 15
        height = table_played.allocation.height
        if height > 360:
            height = 360
        sw.set_size_request(width, height)

        dialog.run()
        dialog.destroy()
 

    def label_air_warning(self, status):
        attr = pango.AttrList()
        if status == "playing":
            text = "On Air"
            fg_color = pango.AttrForeground(65535, 0, 0, 0, -1)
        else:
            text = "Off Air"
            fg_color = pango.AttrForeground(0, 0, 0, 0, -1)
        self.label_air.set_text(text)
        on_air_font = pango.FontDescription("Sans Bold 22")
        self.label_air.modify_font(on_air_font)
        attr.insert(fg_color)
        self.label_air.set_attributes(attr)

    def get_msg_3hr(self):
        date_now = datetime.datetime.now()
        less3 = datetime.timedelta(0, 10800)
        now_less3 = date_now - less3
        db = 'msglist'
        search_terms = (now_less3,)
        query = "SELECT playlog.hostname, playlog.when_played, playlog.id_code, messagelist.title, messagelist.type FROM playlog JOIN messagelist ON playlog.id_code=messagelist.code WHERE playlog.when_played > %s ORDER BY playlog.when_played DESC"
        result = self.execute_query(db, query, search_terms)
        
        return result     
        
    def show_msg_3hr(self, widget):
        dialog = gtk.Dialog("Messages Played in the last 3 Hours", None, 
            gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_NO_SEPARATOR, buttons=None)
        #dialog.set_size_request(420, 60)
        result = self.get_msg_3hr()
        sw = gtk.ScrolledWindow()
        sw.set_size_request(360, 340)
        vbox = gtk.VBox(False, 0)
        for item in result:
            played_on = "Played on: " + item['hostname']
            when_played = item['when_played']
            when_played = when_played.strftime("%c")
            id_code = item['id_code']
            id_code = "Code: " + id_code
            title = item['title']
            msgtype = item['type']
            msgtype = "Message Type: " + msgtype
            str_blank = ""
            list_history = [
                when_played, 
                title, 
                msgtype, 
                id_code, 
                played_on, 
                str_blank
                ]
            
            for item in list_history:
                label = gtk.Label(item)
                vbox.pack_start(label, False)
                label.show()
        sw.add_with_viewport(vbox)
        dialog.vbox.pack_start(sw, True)
        vbox.show()
        sw.show()
        dialog.run()
        dialog.destroy()        

    def get_top_track(self):
        model = self.treeview_bc.get_model()
        tree_iter = model.get_iter_first()
        return model, tree_iter
    
    def get_bc_filepath(self):
        model, tree_iter = self.get_top_track()
        if tree_iter:
            pickle_data = model.get_value(tree_iter, 0)
            dict_data = pickle.loads(pickle_data)
            tracktype = dict_data['tracktype'] 
            filepath = self.get_filepath(dict_data, tracktype)
            tracklength = dict_data['tracklength']
            return filepath, tracklength

        else:
            print "nothing to play"
            return None

    def get_bc_title(self):
        model, tree_iter = self.get_top_track()
        pickle_data = model.get_value(tree_iter, 0)
        dict_data = pickle.loads(pickle_data)
        if dict_data['tracktype'] == 'mus':
            title = dict_data['tracktitle']

        elif dict_data['tracktype'] == 'msg':
            title = dict_data['title']
        
        return title

    def player_bc_get_state(self):
        state = self.player_bc.get_state()
        return state
        
    def player_bc_start(self, filepath):
        self.player_bc.start(filepath)
        
    def player_bc_stop(self):
        self.player_bc.stop()

    def skip_track(self, widget):
        self.player_bc_stop()
        self.check_join()
    
    def log_played_track(self):
        model, tree_iter = self.get_top_track()
        pickle_data = model.get_value(tree_iter, 0)
        dict_data = pickle.loads(pickle_data)
        tracktype = dict_data['tracktype']
        if tracktype == 'msg':
            id_code = dict_data['code']
        elif tracktype == 'mus':
            id_code = dict_data['trackid']
        dt_now = datetime.datetime.now()
        str_dt_now = str(dt_now)[0:19]
        fqhn = socket.gethostname()
        hostname = fqhn.split(".")[0]
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        query = "INSERT INTO playlog (when_played, id_code, id_type, hostname) VALUES ('{0}', '{1}', '{2}', '{3}')".format (
            str_dt_now, 
            id_code, 
            tracktype, 
            hostname)
        #print(query)
        cur.execute(query)
        conn.commit()
        cur.close()
        conn.close()
        
    def delete_top_row(self):
        # Delete the top row from the list
        model, tree_iter = self.get_top_track()
        if tree_iter:
            model.remove(tree_iter)

    def serial_signal(self):
        '''if the broadcast player is playing then stop it playing
        if it is not playing then 
        if there are queued tracks then start playing them
        remove the top track from the list and log to database.
        otherwise do nothing 
        '''
        state = self.player_bc_get_state()
        if  state == gst.STATE_NULL:
            filepath, tracklength = self.get_bc_filepath()
            
            if filepath and os.path.isfile(filepath):                
                self.label_air_warning("playing")
                self.player_bc_start(filepath)
                title = self.get_bc_title()
                self.progressbar.set_text(title)
                tracklength = self.convert_time(tracklength)
                self.label_bc_length.set_text(tracklength)
                self.log_played_track()                
                self.delete_top_row()
                self.update_time_total()

            else:
                print "no file found"
                #check for top row
                self.delete_top_row()
                self.update_time_total()
                self.check_join()
                self.label_bc_length.set_text("00:00")

        '''
        This is no longer required. It used to
        stop a playing track if the desk play button was pressed

        else:
            self.player_bc_stop()
            self.progressbar.set_text("")
            self.label_air_warning("not playing")
            
            #set the 'join' status to false and reset the image)
            model = self.treeview_bc.get_model()
            tree_iter = model.get_iter_first()
            if tree_iter:
                self.set_bool(tree_iter, False)
                iter_next = model.iter_next(tree_iter)
                if iter_next:
                    self.refresh_list(model)
                else:
                    self.set_pixbuf(tree_iter, img_blank)
        '''

    def test_bc(self, widget):
        self.serial_signal()

    def check_join(self):
        model = self.treeview_bc.get_model()
        tree_iter = model.get_iter_first()
        if tree_iter:
            bool = model.get_value(tree_iter, 3)
            if bool:
                self.serial_signal()

    def join_clicked(self, widget):
        self.joinme = True
        treeselection = self.treeview_bc.get_selection()
        treeselection.unselect_all()

    def bc_selection_changed(self, selection):
        if self.joinme:
            model, path = selection.get_selected_rows()
            if path:
                int_path = (path[0][0])
                if int_path == 0:
                    self.join_top(model, int_path)
                else:
                    self.join_tracks(model, int_path)
                    self.joinme = False

    def join_top(self, model, int_path):
        tree_iter = model.get_iter((int_path, )) 
        if model.iter_next(tree_iter):
            int_path_post = int_path + 1
            iter_post = model.get_iter((int_path_post, ))
            b = model.get_value(tree_iter, 3)
            c = model.get_value(iter_post, 3)
            
            if b and c:
                self.set_bool(tree_iter, False)
                self.set_pixbuf(tree_iter, img_top)
            
            if not b and c:
                self.set_bool(tree_iter, True)
                self.set_pixbuf(tree_iter, img_mid)
                
            if b and not c:
                self.set_bool(tree_iter, False)
                self.set_pixbuf(tree_iter, img_blank)
            
            if not b and not c:
                self.set_bool(tree_iter, True)
                self.set_pixbuf(tree_iter, img_btm)
        else:
            if model.get_value(tree_iter, 3):
                self.set_bool(tree_iter, False)
                self.set_pixbuf(tree_iter, img_blank)
            else:
                self.set_bool(tree_iter, True)
                self.set_pixbuf(tree_iter, img_btm)

    def join_tracks(self, model, int_path):                 
        int_path_pre = int_path - 1
        int_path_post = int_path + 1
        tree_iter = model.get_iter((int_path, )) 
        iter_pre = model.get_iter((int_path_pre, ))
        a = model.get_value(iter_pre, 3)
        b = model.get_value(tree_iter, 3)
        try:
            iter_post = model.get_iter((int_path_post, ))
            c = model.get_value(iter_post, 3)
        except ValueError:
            c = False
        
        if not a and not b and not c:
            self.set_bool(tree_iter, True)
            self.set_pixbuf(iter_pre, img_top)
            self.set_pixbuf(tree_iter, img_btm)
            
        if a and not b and not c:
            self.set_bool(tree_iter, True)
            self.set_pixbuf(iter_pre, img_mid)
            self.set_pixbuf(tree_iter, img_btm)
        
        if a and not b and c:
            self.set_bool(tree_iter, True)
            self.set_pixbuf(iter_pre, img_mid)
            self.set_pixbuf(tree_iter, img_mid)
        
        if not a and not b and c:
            self.set_bool(tree_iter, True)
            self.set_pixbuf(iter_pre, img_top)
            self.set_pixbuf(tree_iter, img_mid)
        
        if not a and b and not c:
            self.set_bool(tree_iter, False)
            self.set_pixbuf(iter_pre, img_blank)
            self.set_pixbuf(tree_iter, img_blank)
        
        if a and b and not c:
            self.set_bool(tree_iter, False)
            self.set_pixbuf(iter_pre, img_btm)
            self.set_pixbuf(tree_iter, img_blank)
        
        if a and b and c:
            self.set_bool(tree_iter, False)
            self.set_pixbuf(iter_pre, img_btm)
            self.set_pixbuf(tree_iter, img_top)
        
        if not a and b and c:
            self.set_bool(tree_iter, False)
            self.set_pixbuf(iter_pre, img_blank)
            self.set_pixbuf(tree_iter, img_top)

    def refresh_list(self, model):
        #first check if there is only one row
        tree_iter = model.get_iter_first()
        if not model.iter_next(tree_iter):
            if model.get_value(tree_iter, 3):
                self.set_pixbuf(tree_iter, img_btm)
            else:
                self.set_pixbuf(tree_iter, img_blank)
        else:
            int_path = 1
    
            while int_path:       
                int_path_pre = int_path - 1
                int_path_post = int_path + 1
                tree_iter = model.get_iter((int_path, )) 
                iter_pre = model.get_iter((int_path_pre, ))
                a = model.get_value(iter_pre, 3)
                b = model.get_value(tree_iter, 3)
                try:
                    iter_post = model.get_iter((int_path_post, ))
                    c = model.get_value(iter_post, 1)
                except ValueError:
                    c = False
                
                if not a and not b and not c:
                    self.set_pixbuf(iter_pre, img_blank)
                    self.set_pixbuf(tree_iter, img_blank)
                    
                if a and not b and not c:
                    self.set_pixbuf(iter_pre, img_btm)
                    self.set_pixbuf(tree_iter, img_blank)
                
                if a and not b and c:
                    self.set_pixbuf(iter_pre, img_btm)
                    self.set_pixbuf(tree_iter, img_top)
                
                if not a and not b and c:
                    self.set_pixbuf(iter_pre, img_blank)
                    self.set_pixbuf(tree_iter, img_top)
                
                if not a and b and not c:
                    self.set_pixbuf(iter_pre, img_top)
                    self.set_pixbuf(tree_iter, img_btm)
                
                if a and b and not c:
                    self.set_pixbuf(iter_pre, img_mid)
                    self.set_pixbuf(tree_iter, img_btm)
                
                if a and b and c:
                    self.set_pixbuf(iter_pre, img_mid)
                    self.set_pixbuf(tree_iter, img_mid)
                
                if not a and b and c:
                    self.set_pixbuf(iter_pre, img_top)
                    self.set_pixbuf(tree_iter, img_mid)
                if model.iter_next(tree_iter):    
                    int_path +=1
                else:
                    int_path = False
                
    def set_pixbuf(self, tree_iter, img):
        model = self.treeview_bc.get_model()
        filepath = dir_img + img
        pix = gtk.gdk.pixbuf_new_from_file(filepath)
        model.set_value(tree_iter, 4, pix)
    
    def set_bool(self, tree_iter, bool_join):
        model = self.treeview_bc.get_model()
        model.set_value(tree_iter, 3, bool_join)
    
    def join_drop(self, model, tree_iter, position):
        if position:            
            path = model.get_path(tree_iter)
            bool_join = model.get_value(tree_iter, 3)
            int_path = path[0]
            int_path = int_path - 1
            path = (int_path, )
            tree_iter = model.get_iter(path)
            self.set_bool(tree_iter, bool_join)
       
        else:
            bool_join = model.get_value(tree_iter, 3)
            path = model.get_path(tree_iter)
            int_path = path[0]
            int_path = int_path + 1
            path = (int_path, )
            tree_iter = model.get_iter(path)
            self.set_bool(tree_iter, bool_join)

    def update_time_total(self):
        model = self.treeview_bc.get_model()
        tree_iter = model.get_iter_first()
        if not tree_iter:
            self.label_time_1.set_text("00:00  ")
            
        total_time = 0
        while tree_iter:
            pickle_data = model.get_value(tree_iter, 0)
            dict_data = pickle.loads(pickle_data)
            int_time = dict_data['tracklength']
            try:
                int_time = int(int_time)
                total_time = total_time + int_time
            except TypeError:
                print('could not determine time value')
            tree_iter = model.iter_next(tree_iter)
        str_time = self.convert_time(total_time)
        self.label_time_1.set_text(str_time + "  ")

    # Scheduler section
    def set_up_sch(self):
        sch_list = self.create_sch_list()
        self.make_sch_treelist(sch_list)
        gtk.timeout_add(120000, self.set_up_sch)

    def refresh_sch(self, widget):
        self.set_up_sch()
  
    def create_sch_list(self):
        schedule_list = self.query_schedule()
        programme_list = self.query_programmes()
        sch_list = self.prepare_list(schedule_list, programme_list)
        return sch_list
        
    def query_schedule(self):
        selected_date = datetime.date.today()
        str_selected_date = str(selected_date)
        plus_one = datetime.timedelta(1, 0, 0)
        next_morning = selected_date + plus_one
        str_next_morning = str(next_morning)
        conn = self.pg_connect_msg()
        dict_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        query = "SELECT * FROM schedule JOIN messagelist ON schedule.msg_code=messagelist.code WHERE time_date >= '{0} 06:00' AND time_date < '{1} 06:00' ORDER BY time_date".format (str_selected_date, next_morning)
        dict_cur.execute(query)
        result = dict_cur.fetchall()
        dict_cur.close()
        conn.close()
        #was [datetime, code, title, nq, type, filename, duration] 
        result = [{k:v for k, v in record.items()} for record in result]

        return result
    
    def query_programmes(self):
        date_today = datetime.date.today()
        datetime_date = (date_today.year, date_today.month, date_today.day)
        day_int = date_today.weekday()
        day_of_week = tup_day[day_int]
        if day_int==6:
            next_day = 0
        else:
            next_day = tup_day[day_int+1]

        conn = self.pg_connect_msg()
        cur = conn.cursor()
        query = "SELECT code, name, start FROM programmes WHERE day='{0}' AND start >= '6:00' OR day='{1}' AND start<'06:00'".format (day_of_week, next_day) 
        cur.execute(query) 
        programme_list = cur.fetchall()
        cur.close()
        conn.close()
        return programme_list

    def prepare_list(self, schedule_list, programme_list):
        #[time, Programme ID Code, Programme title, Message ID Code, Message Title]
        timeslot = datetime.time(6, 0)
        add = datetime.timedelta(minutes=30)
        finaltime = datetime.time(5, 30)
        time_list = [["06:00", "", "", "", "", "", 0]]

        while (timeslot != finaltime):
            timeslot = ((datetime.datetime.combine(datetime.date(1,1,1),timeslot)) + add).time()
            timestring = timeslot.strftime("%H:%M")
            timerow = [timestring,  "", "", "", "", ""]
            time_list.append(timerow)
        n = 0
        for item in time_list:
            n+=1

            #check if there is a programme starting at that time
            starttime = item[0]
            for prog in programme_list:
                prog_start_datetime = prog[2]
                prog_start_str = str(prog_start_datetime)
                prog_start = prog_start_str[-8:-3]
                if prog_start==starttime:
                   item[1] =  prog[0]
                   item[2] = prog[1]

            #then check if there are messages scheduled for that time
            for msg in schedule_list:
                msg['tracktype'] = 'msg'
                msg['tracklength'] = msg['duration']
                msg_start = str(msg['time_date'])[-8:-3]
                if msg_start==starttime:
                    self.list_schedule.append(msg)
                    if item[4] == "":
                        item[3] = msg['msg_code']
                        item[4] = msg['title']

                    else:
                        time_list.insert(n, ["", "", "", msg['msg_code'], msg['title']])
                
        return time_list
        
    def make_sch_treelist(self, sch_list):
        self.store_sch.clear()
        for item in sch_list:
            tree_iter = self.store_sch.append()
            self.store_sch.set(tree_iter,
                0, item[0],
                1, item[1],
                2, item[2],
                3, item[3],
                4, item[4],
                )
        treeselection = self.treeview_sch.get_selection()
        treeselection.select_path(0)

    def go_to_now(self, widget):
        '''
        identify current time
        round off to previous half hour as time string
        search the time column one row at a time for the time string
        programatically select the row with the time string        
        '''    
        #self.refresh_sch(None)
        treeselection = self.treeview_sch.get_selection()
        str_now = self.now_half_hour()
        n = 0
        for row in self.store_sch:
            if str_now==row[0]:
                treeselection.select_path(n)
                self.treeview_sch.scroll_to_cell(n, None, True, 0, 0)
            n+=1      

    def now_half_hour(self):
        '''
        get the time rounded up to the nearest half hour
        '''
        t = datetime.datetime.now()
        hr = t.hour
        str_hr = str("%02d" % hr)
        mn = (t.minute)
        if mn < 30:
           str_mn = "00"
        else: 
            str_mn = "30"
        str_now = str_hr + ":" + str_mn 
        return str_now

    def add_sch_sel(self, widget):
        '''
        Adds the selected message in the schedule list to the 
        broadcast list.
        '''
        #get the selected row
        treeselection_sch = self.treeview_sch.get_selection()
        #get details from the row
        model, tree_iter = treeselection_sch.get_selected()
        code = model.get_value(tree_iter, 3)
        dict_schedule = next(
            (item for item in self.list_schedule if item['code'] == code), 
            None
            )
        
        if dict_schedule:
            tracktype = 'msg'            
            filepath = self.get_filepath(dict_schedule, tracktype)

            if not filepath or not os.path.isfile(filepath):
                str_error = "Unable to add - cannot locate the audio file"
                self.error_dialog(str_error)
            
            else: 
                title = dict_schedule['title']
                msg_type = dict_schedule['type']
                tracktitle = msg_type + '\n' + title
                int_time = dict_schedule['tracklength']
                tracktime = self.convert_time(int_time)
                path_img = dir_img + img_blank        
                px = gtk.gdk.pixbuf_new_from_file(path_img)   
                pickle_data = pickle.dumps(dict_schedule)
                list_data = (pickle_data, tracktitle, tracktime, False, px)

                model_bc = self.treeview_bc.get_model()
                model_bc.append(list_data)
        else:
            str_error = "You need to select a message before clicking the 'Add' button" 
            self.error_dialog(str_error)

    # preview section  

    def play_pause_clicked(self, widget):

        if self.dict_pre:
            tracktype = self.dict_pre['tracktype']
            filepath = self.get_filepath(self.dict_pre, tracktype)

            if not filepath or not os.path.isfile(filepath):
                str_error = "Unable to play - cannot locate the audio file"
                self.error_dialog(str_error)
            else:
                self.play_preview(filepath)
        
        else:
            print('nothing to play')

    def play_preview(self, filepath):
        img = self.btn_pre_play_pause.get_image()
        if img.get_name() == "play":          
            self.btn_pre_play_pause.set_image(self.image_pause)
            self.player_pre.start(filepath)
            
        else:
            self.player_pre.pause()
            self.btn_pre_play_pause.set_image(self.image_play)
                
    def on_stop_clicked(self, widget):
        self.player_pre.stop()
        self.btn_pre_play_pause.set_image(self.image_play)
        self.label_pre_time.set_text("00:00 / " + self.str_dur)
        
    def reset_playbutton(self):
        self.btn_pre_play_pause.set_image(self.image_play)

    def cat_selection_changed(self, selection):
        playstatus = self.player_pre.get_state() 
        if (not playstatus == gst.STATE_PLAYING) and (not playstatus == gst.STATE_PAUSED):
            model, path = selection.get_selected_rows()
            if path:
                tree_iter = model.get_iter(path[0])
                trackid = model.get_value(tree_iter, 0)
                
                trackid = int(trackid)
                dict_search = next(
                    (item for item in self.list_search if item['trackid'] == trackid), 
                    None
                    )
                
                if dict_search:
                    self.dict_pre = dict_search
                    tracktitle = self.dict_pre['tracktitle']
                    tracklength = self.dict_pre['tracklength']

                    self.str_dur = self.convert_time(tracklength)

                    self.label_pre_play.set_label(tracktitle)
                    if len(tracktitle) > 30:
                        self.label_pre_play.set_tooltip_text(tracktitle) 
                    else:
                        self.label_pre_play.set_tooltip_text("")
                    
                    self.label_pre_time.set_text("00:00 / " + self.str_dur)

    def p3d_selection_changed(self, selection):
        playstatus = self.player_pre.get_state() 
        if (not playstatus == gst.STATE_PLAYING) and (not playstatus == gst.STATE_PAUSED):
            model, path = selection.get_selected_rows()
            if path:
                tree_iter = model.get_iter(path[0])
                trackid = model.get_value(tree_iter, 0)
                trackid = int(trackid)
                dict_playlist = next(
                    (item for item in self.list_playlist if item['trackid'] == trackid), 
                    None
                    )
                
                if dict_playlist:
                    self.dict_pre = dict_playlist
                    tracktitle = self.dict_pre['tracktitle']
                    tracklength = self.dict_pre['tracklength']

                    self.str_dur = self.convert_time(tracklength)

                    self.label_pre_play.set_label(tracktitle)
                    if len(tracktitle) > 30:
                        self.label_pre_play.set_tooltip_text(tracktitle) 
                    else:
                        self.label_pre_play.set_tooltip_text("")
                    
                    self.label_pre_time.set_text("00:00 / " + self.str_dur)



    def msg_selection_changed(self, selection):
        playstatus = self.player_pre.get_state() 
        if (not playstatus == gst.STATE_PLAYING) and (not playstatus == gst.STATE_PAUSED):
            model, path = selection.get_selected_rows()
            if path:
                tree_iter = model.get_iter(path[0])
                code = model.get_value(tree_iter, 0)
                dict_message = next(
                    (item for item in self.list_messages if item['code'] == code), 
                    None
                    )
                
                if dict_message:
                    self.dict_pre = dict_message
                    title = self.dict_pre['title']
                    duration = self.dict_pre['duration']

                    self.str_dur = self.convert_time(duration)

                    self.label_pre_play.set_label(title)
                    if len(title) > 30:
                        self.label_pre_play.set_tooltip_text(title) 
                    else:
                        self.label_pre_play.set_tooltip_text("")
                    
                    self.label_pre_time.set_text("00:00 / " + self.str_dur)  

    def sch_selection_changed(self, selection):
        '''
        set the preview with the selected message
        '''
        playstatus = self.player_pre.get_state() 
        if (not playstatus == gst.STATE_PLAYING) and (not playstatus == gst.STATE_PAUSED):
            model, path = selection.get_selected_rows()
            if path:
                tree_iter = model.get_iter(path[0])
                code = model.get_value(tree_iter, 3)
                if code:
                    dict_schedule = next(
                        (item for item in self.list_schedule if item['code'] == code), 
                        None
                        )
                
                    if dict_schedule:
                        self.dict_pre = dict_schedule
                        title = self.dict_pre['title']
                        duration = self.dict_pre['duration']

                        self.str_dur = self.convert_time(duration)

                        self.label_pre_play.set_label(title)
                        if len(title) > 30:
                            self.label_pre_play.set_tooltip_text(title) 
                        else:
                            self.label_pre_play.set_tooltip_text("")
                        
                        self.label_pre_time.set_text("00:00 / " + self.str_dur)  
                
    def on_seek_changed(self, widget, param):
        self.player_pre.set_updateable_progress(True)
        self.player_pre.set_place_in_file(self.hscale_pre.get_value())
        
        
    def update_countdown(self, next_start_datetime):
        '''
        if the time on the label is less than 1
        query the database to get the next show
        set the labels with show name and time remaining
        else:
        subtract 1 from the time remaining
        '''
        now = datetime.datetime.now()
        difference = next_start_datetime - now
        one_second = datetime.timedelta(seconds = 1)
        one_day = datetime.timedelta(days = 1)
        
        if difference < one_second:
            try:
                #query the database
                result = self.get_next_show(now)
                if result:
                    name, start_time = result
                    next_start_datetime = datetime.datetime.combine(now, start_time)
                
                else:
                    tomorrow = now + one_day
                    midnight = datetime.time(0,0,0)
                    tomorrow_midnight = datetime.datetime.combine(tomorrow, midnight)
                    result = self.get_next_show(tomorrow_midnight)
                    name, start_time = result
                    next_start_datetime = datetime.datetime.combine(tomorrow, start_time)

                self.label_cdn_prg.set_tooltip_text(name)
                
            except Exception as e: 
                print("failed to query database for next program start time")
                print(e)
                self.label_date.set_text("Database error")
                self.label_time.set_text("")
                self.label_cdn_time.set_text("")
                
        try:            
            delta_time_remaining = next_start_datetime - now
            print("time remaining is:")          
            print(str((delta_time_remaining + datetime.timedelta(0,1))))
            time_left = str((delta_time_remaining + datetime.timedelta(0,1))).split(".")[0]
            self.label_cdn_time.set_text(time_left)
            
            self.label_date.set_text(now.strftime(("%A %d %B")))
            # uncomment below to show hours minutes and seconds
            self.label_time.set_text(now.strftime("%H:%M:%S"))
            # Uncoment below to also display seconds and AM/PM
            #self.label_time.set_text(now.strftime('%-I:%M:%S %p'))
        except Exception as e:
                print("failed to set the time or countdown")
                print(e)
                self.label_date.set_text("Time/date error")
                self.label_time.set_text("")
                self.label_cdn_time.set_text("")
        
        finally:
            gtk.timeout_add(1000, self.update_countdown, next_start_datetime)
        
    def get_next_show(self,now):
        
        day = now.strftime('%A')
        now_time = now.strftime("%H:%M:%S")

        result = self.query_next_show(day, now_time)

        print("Query database for the next show")
        print(result)

        return result

    def query_next_show(self, day, now_time):
        # select name, start from programmes where day='Saturday' and start > '14:04' order by start limit 1;

        conn = self.pg_connect_msg()
        cur = conn.cursor()
        query = "SELECT name, start FROM programmes WHERE day=%s AND start >= %s ORDER BY start ASC LIMIT 1"
        cur.execute(query, (day, now_time)) 
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result

    #common functions

    def get_filepath(self, dict_data, tracktype):
        '''
        get details from the dict data, 
        check if the file exists
        and if so, return the filepath.
        '''
        if tracktype == 'msg':
            filepath = "{0}/{1}/{2}".format (
                dir_msg, 
                dict_data['type'].lower()[0:12], 
                dict_data['filename'])   

        
        elif tracktype == 'mus':                   
            cd_code = str(format(dict_data['cdid'], '07d')) # 7 digit
            track_no = str(format(dict_data['tracknum'], '02d')) # 2 digit
            filepath = "{0}{1}/{1}-{2}.mp3".format(
                dir_mus, 
                cd_code,
                track_no
            )

        if os.path.isfile(filepath):
            return filepath

        else:
            return None
        
    def right_click_msg_list_menu(self, treeview, event):
        '''
        create items in a menu on right-click
        '''
        if event.button == 3: # right click
            selection = treeview.get_selection()
            model, tree_iter = selection.get_selected()
            if tree_iter:
                context_menu = gtk.Menu()
                details_item = gtk.MenuItem( "Details")
                details_item.connect("activate", self.show_msg_details, treeview)
                details_item.show()
                play_item = gtk.MenuItem("Play Preview")
                play_item.connect( "activate", self.play_msg_from_menu, treeview)
                play_item.show()
                add_item = gtk.MenuItem("Add")
                add_item.connect("activate", self.add_msg_to_bc, treeview)
                add_item.show()
                context_menu.append(details_item)
                context_menu.append(play_item)
                context_menu.append(add_item)
                context_menu.popup(
                    None, 
                    None, 
                    None, 
                    event.button, 
                    event.get_time()
                	)
        

    


    def right_click_cat_list_menu(self, treeview, event):
        '''
        create items in a menu on right-click
        '''
        if event.button == 3: # right click
            context_menu = gtk.Menu()
            details_item = gtk.MenuItem( "Details")
            details_item.connect("activate", self.show_cat_details, treeview)
            details_item.show()

            selection = treeview.get_selection()
            model, iter = selection.get_selected()
            tracklength = model.get_value(iter, 4)
            play_item = gtk.MenuItem("Play Preview")
            play_item.connect( "activate", self.play_cat_from_menu, treeview)
            play_item.show()

            add_item = gtk.MenuItem("Add")
            add_item.connect("activate", self.add_cat_to_bc, treeview)
            add_item.show()

            context_menu.append(details_item)
            context_menu.append(play_item)
            context_menu.append(add_item)
            
            if not tracklength:
                play_item.set_sensitive(False)
                add_item.set_sensitive(False)
                
            context_menu.popup( None, None, None, event.button, event.get_time())

    def right_click_p3d_list_menu(self, treeview, event):
        '''
        create items in a menu on right-click
        '''
        if event.button == 3: # right click
            selection = treeview.get_selection()
            model, path = selection.get_selected_rows()
            if path:            
                context_menu = gtk.Menu()
                details_item = gtk.MenuItem( "Details")
                details_item.connect("activate", self.show_p3d_details, treeview)
                details_item.show()
                play_item = gtk.MenuItem("Play Preview")
                play_item.connect( "activate", self.play_p3d_from_menu, treeview)
                play_item.show()
                add_item = gtk.MenuItem("Add")
                add_item.connect("activate", self.add_p3d_to_bc, treeview)
                add_item.show()
                context_menu.append(details_item)
                context_menu.append(play_item)
                context_menu.append(add_item)
                context_menu.popup(
                    None, 
                    None, 
                    None, 
                    event.button, 
                    event.get_time()
                    )

    def right_click_sch_list_menu(self, treeview, event):
        '''
        create items in a menu on right-click
        '''
        if event.button == 3: # right click
            selection = treeview.get_selection()
            model, tree_iter = selection.get_selected()
            if tree_iter:            
                context_menu = gtk.Menu()
                details_item = gtk.MenuItem( "Details")
                details_item.connect("activate", self.show_sch_details, treeview)
                details_item.show()
                play_item = gtk.MenuItem("Play Preview")
                play_item.connect( "activate", self.play_sch_from_menu, treeview)
                play_item.show()
                add_item = gtk.MenuItem("Add")
                add_item.connect("activate", self.add_sch_to_bc, treeview)
                add_item.show()
                context_menu.append(details_item)
                context_menu.append(play_item)
                context_menu.append(add_item)
                context_menu.popup(
                    None, 
                    None, 
                    None, 
                    event.button, 
                    event.get_time()
                    )
                selection = treeview.get_selection()
                model, tree_iter = selection.get_selected()
                code = model.get_value(tree_iter, 3)
                if not code:
                    details_item.set_sensitive(False)
                    play_item.set_sensitive(False)
                    add_item.set_sensitive(False)



    def right_click_bc_list_menu(self, treeview, event):
        '''
        create items in a menu on right-click
        '''
        if event.button == 3: # right click
            selection = treeview.get_selection()
            model, tree_iter = selection.get_selected()
            if tree_iter:            
                context_menu = gtk.Menu()
                details_item = gtk.MenuItem( "Details")
                details_item.connect("activate", self.show_bc_details, treeview)
                details_item.show()
                context_menu.append(details_item)
                context_menu.popup(
                    None, 
                    None, 
                    None, 
                    event.button, 
                    event.get_time()
                    )

    def play_msg_from_menu(self, widget, treeview):
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        code = model.get_value(tree_iter, 0)

        dict_data = next(
            (item for item in self.list_messages if item['code'] == code), 
            None
            )
        
        if dict_data:
            tracktype = 'msg'
            filepath = self.get_filepath(dict_data, tracktype)

            if os.path.isfile(filepath):  
                self.play_preview(filepath)     

    def play_cat_from_menu(self, widget, treeview):
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()

        trackid = model.get_value(tree_iter, 0)
        trackid = int(trackid)

        dict_data = next(
            (item for item in self.list_search if item['trackid'] == trackid), 
            None
            )
        if dict_data:
            tracktype = 'mus'
            filepath = self.get_filepath(dict_data, tracktype)

            if filepath:  
                self.play_preview(filepath)     
    
    def play_p3d_from_menu(self, widget, treeview):
        treeselection = treeview.get_selection()
        model = treeview.get_model()
        rows = treeselection.get_selected_rows()
        for row in rows:
            path = row[0]
        tree_iter = model.get_iter(path)
        trackid = model.get_value(tree_iter, 0)
        trackid = int(trackid)

        dict_data = next(
            (item for item in self.list_playlist if item['trackid'] == trackid), 
            None
            )
        if dict_data:
            tracktype = 'mus'
            filepath = self.get_filepath(dict_data, tracktype)

            if os.path.isfile(filepath):  
                self.play_preview(filepath)     

    def play_sch_from_menu(self, widget, treeview):
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        code = model.get_value(tree_iter, 3)

        dict_data = next(
            (item for item in self.list_schedule if item['code'] == code), 
            None
            )
        
        if dict_data:
            tracktype = 'msg'
            filepath = self.get_filepath(dict_data, tracktype)

            if os.path.isfile(filepath):  
                self.play_preview(filepath)     

    def show_msg_details(self, w, treeview):
        '''
        get the dictionary of details from the treeview and run the function 
        to display a dialog window with the details.

        '''
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        code = model.get_value(tree_iter, 0)

        dict_data = next(
            (item for item in self.list_messages if item['code'] == code), 
            None
            )
        
        self.display_message_details(dict_data)


    def show_cat_details(self, w, treeview):
        '''
        get the dictionary of details from the treeview and run the function 
        to display a dialog window with the details.

        '''
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        id, tracklength = model.get(tree_iter, 0, 4)
        id = int(id)
        tracklength = tracklength

        if tracklength:
            dict_data = next(
                (item for item in self.list_search if item['trackid'] == id), 
                None
                )
            is_cd = False
        else:
            dict_data = next(
                (item for item in self.list_search if item['cdid'] == id), 
                None
                ) 
            is_cd = True          
        
        self.display_track_details(dict_data, is_cd)

    def show_p3d_details(self, w, treeview):
        '''
        get the dictionary of details from the treeview and run the function 
        to display a dialog window with the details.

        '''
        treeselection = treeview.get_selection()
        model = treeview.get_model()
        rows = treeselection.get_selected_rows()
        for row in rows:
            path = row[0]
        tree_iter = model.get_iter(path)
        trackid = model.get_value(tree_iter, 0)
        trackid = int(trackid)

        dict_data = next(
            (item for item in self.list_playlist if item['trackid'] == trackid), 
            None
            )
        
        self.display_track_details(dict_data, False)


    def show_sch_details(self, w, treeview):
        '''
        get the dictionary of details from the treeview and run the function 
        to display a dialog window with the details.

        '''
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        code = model.get_value(tree_iter, 3)

        dict_data = next(
            (item for item in self.list_schedule if item['code'] == code), 
            None
            )

        self.display_message_details(dict_data)

    def show_bc_details(self, w, treeview):
        '''
        get the dictionary of details from the treeview and run the function 
        to display a dialog window with the details.

        '''
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        pickle_data = model.get_value(tree_iter, 0)
        dict_data = pickle.loads(pickle_data)
        if 'code' in dict_data:        
            self.display_message_details(dict_data)

        elif 'trackid' in dict_data:
            self.display_track_details(dict_data, False)

    def add_msg_to_bc(self, widget, treeview):
        '''
        from right-click menu add the selected message to the playlist
        '''
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        code = model.get_value(tree_iter, 0)

        dict_data = next(
            (item for item in self.list_messages if item['code'] == code), 
            None
            )
        tracktype = 'msg'
        filepath = self.get_filepath(dict_data, tracktype)
        if not filepath:
            #display error message and return
            str_error = "Unable to add to the list, the audio file does not exist. \
Please inform the message production team of this error."            

            self.error_dialog(str_error)
            return

        model = self.treeview_bc.get_model()
        int_time = dict_data['tracklength']
        tracktime = self.convert_time(int_time)
        title = dict_data['title']
        msg_type = dict_data['type']
        tracktitle = msg_type + '\n' + title
        pickle_data = pickle.dumps(dict_data)
        path_img = dir_img + img_blank        
        px = gtk.gdk.pixbuf_new_from_file(path_img)   
        list_data = (pickle_data, tracktitle, tracktime, False, px)
        model.append(list_data)

    def add_cat_to_bc(self, widget, treeview):
        '''
        from right-click menu add the selected catalogue track to the playlist
        '''
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        trackid = model.get_value(tree_iter, 0)
        trackid = int(trackid)

        dict_data = next(
            (item for item in self.list_search if item['trackid'] == trackid), 
            None
            )
        tracktype = 'mus'
        filepath = self.get_filepath(dict_data, tracktype)
        
        if not filepath:
            str_error = "Unable to add to the list, the audio file does not exist. \
                You may wish to get the details and rip that CD into the music store"            
            self.error_dialog(str_error)
            return

        model = self.treeview_bc.get_model()
        int_time = dict_data['tracklength']
        tracktime = self.convert_time(int_time)
        tracktitle = dict_data['tracktitle']
        trackartist = dict_data['trackartist']
        artist = dict_data['artist']
        
        if not trackartist:
            trackartist = artist
        
        tracktitle = trackartist + '\n' + tracktitle
        path_img = dir_img + img_blank        
        px = gtk.gdk.pixbuf_new_from_file(path_img)   
        pickle_data = pickle.dumps(dict_data)
        list_data = (pickle_data, tracktitle, tracktime, False, px)
        model.append(list_data)

    def add_p3d_to_bc(self, widget, treeview):
        '''
        from right-click menu add the selected catalogue track to the playlist
        '''
        selection = treeview.get_selection()
        model = treeview.get_model()
        rows = selection.get_selected_rows()
        for row in rows:
            path = row[0]
        tree_iter = model.get_iter(path)
        trackid = model.get_value(tree_iter, 0)
        trackid = int(trackid)

        dict_data = next(
            (item for item in self.list_playlist if item['trackid'] == trackid), 
            None
            )

        if dict_data:
            tracktype = 'mus'
            filepath = self.get_filepath(dict_data, tracktype)
            if not filepath:
                str_error = "Unable to add to the list, the audio file could not be located."
                self.error_dialog(str_error)
                return

            model = self.treeview_bc.get_model()
            int_time = dict_data['tracklength']
            tracktime = self.convert_time(int_time)
            #cd_code = str(format(dict_data['cdid'], '07d')) # 7 digit
            #track_no = str(format(dict_data['tracknum'], '02d')) # 2 digit
            tracktitle = dict_data['tracktitle']
            trackartist = dict_data['trackartist']
            artist = dict_data['artist']
            
            if not trackartist:
                trackartist = artist
            
            tracktitle = trackartist + '\n' + tracktitle
            path_img = dir_img + img_blank        
            px = gtk.gdk.pixbuf_new_from_file(path_img)   
            pickle_data = pickle.dumps(dict_data)
            list_data = (pickle_data, tracktitle, tracktime, False, px)
            model.append(list_data)

    def add_sch_to_bc(self, widget, treeview):
        '''
        from right-click menu add the selected message to the playlist
        '''
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        code = model.get_value(tree_iter, 3)
        dict_data = next(
            (item for item in self.list_schedule if item['code'] == code), 
            None
            )
        tracktype = 'msg'
        filepath = self.get_filepath(dict_data, tracktype)
        if not filepath:
            #display error message and return
            str_error = "Unable to add to the list, the audio file does not exist. \
Please inform the message production team of this error."
            self.error_dialog(str_error)
            return

        model = self.treeview_bc.get_model()
        int_time = dict_data['tracklength']
        tracktime = self.convert_time(int_time)
        title = dict_data['title']
        msg_type = dict_data['type']
        tracktitle = msg_type + '\n' + title
        pickle_data = pickle.dumps(dict_data)
        path_img = dir_img + img_blank        
        px = gtk.gdk.pixbuf_new_from_file(path_img)   
        list_data = (pickle_data, tracktitle, tracktime, False, px)
        model.append(list_data)


    def display_track_details(self, dict_data, is_cd):
        '''
        open a dialog window with details of the selected track
        '''
        dialog = gtk.Dialog("Details", None, 0, (
            gtk.STOCK_OK, gtk.RESPONSE_OK))
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        #sw.set_size_request(280, 340)
        table_details = gtk.Table(20, 2, False)
        sw.add_with_viewport(table_details) 

        dialog.vbox.pack_start(sw, True, True, 0)
       
        n = 0
        
        if is_cd:
            artist = dict_data["artist"]

        elif "trackartist" in dict_data:
            artist = dict_data["trackartist"]
            if not artist:
                artist = dict_data["artist"]
        else: 
            artist = dict_data["artist"]
            
        label_detail_artist = gtk.Label()
        label_detail_artist.set_alignment(0, 0.5)
        label_detail_artist.set_text("Artist: ")        
        table_details.attach(label_detail_artist, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_artist = gtk.Label()
        label_artist.set_alignment(0, 0.5)
        label_artist.set_text(artist)
        label_artist.set_selectable(True)
        table_details.attach(label_artist, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1 

        if not is_cd:
            if "tracktitle" in dict_data:
                label_detail_track = gtk.Label()
                label_detail_track.set_text("Track: ")
                label_detail_track.set_alignment(0, 0.5)
                table_details.attach(label_detail_track, 0, 1, n, n + 1, False, False, 5, 0)
                
                label_track = gtk.Label()
                track = dict_data['tracktitle']
                label_track.set_text(track)
                label_track.set_selectable(True)
                label_track.set_alignment(0, 0.5)
                table_details.attach(label_track, 1, 2, n, n + 1, False, False, 5, 0)
                
                n += 1    
                
        label_detail_album = gtk.Label()
        label_detail_album.set_text("Album: ")
        label_detail_album.set_alignment(0, 0.5)
        table_details.attach(label_detail_album, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_album = gtk.Label()
        album = dict_data['title']
        label_album.set_text(album)
        label_album.set_selectable(True)
        label_album.set_alignment(0, 0.5)
        table_details.attach(label_album, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1
        
        if not is_cd:
            if "tracklength" in dict_data:
                label_detail_tracklength = gtk.Label()
                label_detail_tracklength.set_text("Track Length: ")
                label_detail_tracklength.set_alignment(0, 0.5)
                table_details.attach(label_detail_tracklength, 0, 1, n, n + 1, False, False, 5, 0)
                
                label_tracklength = gtk.Label()
                tracklength = dict_data['tracklength']
                str_tracklength = self.convert_time(tracklength)
                label_tracklength.set_text(str_tracklength)
                label_tracklength.set_selectable(True)
                label_tracklength.set_alignment(0, 0.5)
                table_details.attach(label_tracklength, 1, 2, n, n + 1, False, False, 5, 0)
            
                n += 1

        label_detail_local = gtk.Label()
        label_detail_local.set_alignment(0, 0.5)
        label_detail_local.set_text("Local: ")
        table_details.attach(label_detail_local, 0, 1, n, n + 1, False, False, 5, 0)
                
        label_local = gtk.Label()
        label_local.set_alignment(0, 0.5)
        label_local.set_selectable(True)
        local = dict_data['local']
        local = unys[local]
        label_local.set_text(local)
        table_details.attach(label_local, 1, 2, n, n + 1, False, False, 5, 0)
        
        n += 1

        label_detail_female = gtk.Label()
        label_detail_female.set_alignment(0, 0.5)
        label_detail_female.set_text("Female: ")
        table_details.attach(label_detail_female, 0, 1, n, n + 1, False, False, 5, 0)      

        label_female = gtk.Label()
        label_female.set_alignment(0, 0.5)
        label_female.set_selectable(True)
        female = dict_data['female']
        female = unys[female]
        label_female.set_text(female)
        table_details.attach(label_female, 1, 2, n, n + 1, False, False, 5, 0)
        
        n += 1

        label_detail_demo = gtk.Label()
        label_detail_demo.set_alignment(0, 0.5)
        label_detail_demo.set_text("Demo: ")
        table_details.attach(label_detail_demo, 0, 1, n, n + 1, False, False, 5, 0) 

        label_demo = gtk.Label()
        label_demo.set_alignment(0, 0.5)
        label_demo.set_selectable(True)
        demo = dict_data['demo']
        if not demo:
            demo = 0
        demo = unys[demo]
        label_demo.set_text(demo)
        table_details.attach(label_demo, 1, 2, n, n + 1, False, False, 5, 0)
        
        n += 1

        if 'compliation' in dict_data:
            label_detail_compilation = gtk.Label()
            label_detail_compilation.set_alignment(0, 0.5)
            label_detail_compilation.set_text("Compilation: ")
            table_details.attach(label_detail_compilation, 0, 1, n, n + 1, False, False, 5, 0)      

            label_compilation = gtk.Label()
            label_compilation.set_alignment(0, 0.5)
            label_compilation.set_selectable(True)
            compilation = dict_data['compilation']
            compilation = unys[compilation]
            label_compilation.set_text(compilation)
            table_details.attach(label_compilation, 1, 2, n, n + 1, False, False, 5, 0)
            
            n += 1

        if 'company' in dict_data:
            label_detail_company = gtk.Label()
            label_detail_company.set_alignment(0, 0.5)
            label_detail_company.set_text("Company: ")
            table_details.attach(label_detail_company, 0, 1, n, n + 1, False, False, 5, 0)      
            
            label_company = gtk.Label()
            label_company.set_alignment(0, 0.5)
            label_company.set_selectable(True)
            company = dict_data['company']

            if company:
                label_company.set_text(company)
                table_details.attach(label_company, 1, 2, n, n + 1, False, False, 5, 0)
            
            n += 1
        
        if 'year' in dict_data:
            label_detail_year = gtk.Label()
            label_detail_year.set_alignment(0, 0.5)
            label_detail_year.set_text("Release Year: ") 
            table_details.attach(label_detail_year, 0, 1, n, n + 1, False, False, 5, 0)      

            label_year = gtk.Label()
            label_year.set_alignment(0, 0.5)
            label_year.set_selectable(True)
            year = dict_data['year']
            if year:
                year = str(year)
                label_year.set_text(year) 
                table_details.attach(label_year, 1, 2, n, n + 1, False, False, 5, 0)

            n += 1

        if 'cpa' in dict_data:
            label_detail_cpa = gtk.Label()
            label_detail_cpa.set_alignment(0, 0.5)
            label_detail_cpa.set_text("Country: ")
            table_details.attach(label_detail_cpa, 0, 1, n, n + 1, False, False, 5, 0)      
        
            label_cpa = gtk.Label()
            label_cpa.set_alignment(0, 0.5)
            label_cpa.set_selectable(True)

            cpa = dict_data['cpa']
            if cpa:
                label_cpa.set_text(cpa)
                table_details.attach(label_cpa, 1, 2, n, n + 1, False, False, 5, 0)

            n += 1

        if 'genre' in dict_data:
            label_detail_genre = gtk.Label()
            label_detail_genre.set_alignment(0, 0.5)
            label_detail_genre.set_text("Genre: ")
            table_details.attach(label_detail_genre, 0, 1, n, n + 1, False, False, 5, 0)      
        
            
            label_genre = gtk.Label()
            label_genre.set_alignment(0, 0.5)
            label_genre.set_selectable(True)
            genre = dict_data['genre']
            if genre:
                label_genre.set_text(genre)
                table_details.attach(label_genre, 1, 2, n, n + 1, False, False, 5, 0)

            n += 1

        if 'createwho' in dict_data:
            label_detail_createwho = gtk.Label()
            label_detail_createwho.set_alignment(0, 0.5)
            label_detail_createwho.set_text("Added By: ")
            table_details.attach(label_detail_createwho, 0, 1, n, n + 1, False, False, 5, 0)      
        
            
            label_createwho = gtk.Label()
            label_createwho.set_alignment(0, 0.5)
            label_createwho.set_selectable(True)
        
            createwho = dict_data['createwho']
            if createwho:
                createwho = self.dict_creator[createwho]
                label_createwho.set_text(createwho)
                table_details.attach(label_createwho, 1, 2, n, n + 1, False, False, 5, 0)

            n += 1
       
        if 'createwhen' in dict_data:
            label_detail_createwhen = gtk.Label()
            label_detail_createwhen.set_alignment(0, 0.5)
            label_detail_createwhen.set_text("Date Added: ")
            table_details.attach(label_detail_createwhen, 0, 1, n, n + 1, False, False, 5, 0)      
            
            label_createwhen = gtk.Label()
            label_createwhen.set_alignment(0, 0.5)
            label_createwhen.set_selectable(True)
            createwhen = dict_data['createwhen']
            if createwhen:
                createwhen = datetime.datetime.fromtimestamp(createwhen)
                createwhen = createwhen.strftime("%d/%m/%Y")
                label_createwhen.set_text(createwhen)
                table_details.attach(label_createwhen, 1, 2, n, n + 1, False, False, 5, 0)

            n += 1
                
        label_detail_id = gtk.Label()
        label_detail_id.set_text("CD ID: ")
        label_detail_id.set_alignment(0, 0.5)
        table_details.attach(label_detail_id, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_id = gtk.Label()
        cdid = dict_data["cdid"]
        cdid = str(format(cdid, '07d')) # 7 digit
        label_id.set_text(cdid)
        label_id.set_selectable(True)
        label_id.set_alignment(0, 0.5)
        table_details.attach(label_id, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        if 'comment' in dict_data:
            label_detail_comment = gtk.Label()
            label_detail_comment.set_text("Comments: ")
            label_detail_comment.set_alignment(0, 0.5)
            table_details.attach(label_detail_comment, 0, 1, n, n + 1, False, False, 5, 0)

            label_comment = gtk.Label()
            label_comment.set_alignment(0, 0.5)
            label_comment.set_selectable(True)
            label_comment.set_line_wrap(True)        
            
            cdcomment = dict_data['comment']
            if cdcomment:
                label_comment.set_text(cdcomment)
                table_details.attach(label_comment, 1, 2, n, n + 1, False, False, 5, 0)

        dialog.show_all()
        width = table_details.allocation.width + 15
        height = table_details.allocation.height
        if height > 360:
            height = 360
        sw.set_size_request(width, height)
        dialog.run()    
        dialog.destroy()        

    def display_message_details(self, dict_data):
        '''
        open a dialog window with details of the selected message
        '''
        dialog = gtk.Dialog("Details", None, 0, (
            gtk.STOCK_OK, gtk.RESPONSE_OK))
        table_details = gtk.Table(20, 2, False)
        dialog.vbox.pack_start(table_details, True, True, 0)

        n = 0

        label_detail_type = gtk.Label()
        label_detail_type.set_text("Message Type: ")
        label_detail_type.set_alignment(0, 0.5)
        table_details.attach(label_detail_type, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_type = gtk.Label()
        msgtype = dict_data['type']
        label_type.set_text(msgtype)
        label_type.set_selectable(True)
        label_type.set_alignment(0, 0.5)
        table_details.attach(label_type, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1
               
        label_detail_title = gtk.Label()
        label_detail_title.set_text("Title: ")
        label_detail_title.set_alignment(0, 0.5)
        table_details.attach(label_detail_title, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_title = gtk.Label()
        title = dict_data['title']
        label_title.set_text(title)
        label_title.set_selectable(True)
        label_title.set_alignment(0, 0.5)
        table_details.attach(label_title, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_nq = gtk.Label()
        label_detail_nq.set_text("End Cue: ")
        label_detail_nq.set_alignment(0, 0.5)
        table_details.attach(label_detail_nq, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_nq = gtk.Label()
        nq = dict_data['nq']
        label_nq.set_text(nq)
        label_nq.set_selectable(True)
        label_nq.set_alignment(0, 0.5)
        table_details.attach(label_nq, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_code = gtk.Label()
        label_detail_code.set_text("ID Code: ")
        label_detail_code.set_alignment(0, 0.5)
        table_details.attach(label_detail_code, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_code = gtk.Label()
        code = dict_data['code']
        label_code.set_text(code)
        label_code.set_selectable(True)
        label_code.set_alignment(0, 0.5)
        table_details.attach(label_code, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_fldproducer = gtk.Label()
        label_detail_fldproducer.set_text("Produced By: ")
        label_detail_fldproducer.set_alignment(0, 0.5)
        table_details.attach(label_detail_fldproducer, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_fldproducer = gtk.Label()
        fldproducer = dict_data['fldproducer']
        label_fldproducer.set_text(fldproducer)
        label_fldproducer.set_selectable(True)
        label_fldproducer.set_alignment(0, 0.5)
        table_details.attach(label_fldproducer, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_created = gtk.Label()
        label_detail_created.set_text("Created On: ")
        label_detail_created.set_alignment(0, 0.5)
        table_details.attach(label_detail_created, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_created = gtk.Label()
        created = dict_data['created']
        created = created.strftime('%d/%m/%Y')
        label_created.set_text(created)
        label_created.set_selectable(True)
        label_created.set_alignment(0, 0.5)
        table_details.attach(label_created, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_expirydate = gtk.Label()
        label_detail_expirydate.set_text("Expiry Date: ")
        label_detail_expirydate.set_alignment(0, 0.5)
        table_details.attach(label_detail_expirydate, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_expirydate = gtk.Label()
        expirydate = dict_data['expirydate']
        expirydate = expirydate.strftime('%d/%m/%Y')
        label_expirydate.set_text(expirydate)
        label_expirydate.set_selectable(True)
        label_expirydate.set_alignment(0, 0.5)
        table_details.attach(label_expirydate, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_filename = gtk.Label()
        label_detail_filename.set_text("Audio File: ")
        label_detail_filename.set_alignment(0, 0.5)
        table_details.attach(label_detail_filename, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_filename = gtk.Label()
        filename = dict_data['filename']
        label_filename.set_text(filename)
        label_filename.set_selectable(True)
        label_filename.set_alignment(0, 0.5)
        table_details.attach(label_filename, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        if "duration" in dict_data:
            label_detail_duration = gtk.Label()
            label_detail_duration.set_text("Track Length: ")
            label_detail_duration.set_alignment(0, 0.5)
            table_details.attach(label_detail_duration, 0, 1, n, n + 1, False, False, 5, 0)
            
            label_duration = gtk.Label()
            duration = dict_data['duration']
            str_duration = self.convert_time(duration)
            label_duration.set_text(str_duration)
            label_duration.set_selectable(True)
            label_duration.set_alignment(0, 0.5)
            table_details.attach(label_duration, 1, 2, n, n + 1, False, False, 5, 0)
        
            n += 1


        dialog.show_all()
        dialog.run()    
        dialog.destroy()            


    def convert_time(self, dur):
        s = int(dur)
        m,s = divmod(s, 60)

        if m < 60:
            str_dur = "%02i:%02i" %(m,s)
            return str_dur
        else:
            h,m = divmod(m, 60)
            str_dur = "%i:%02i:%02i" %(h,m,s)
            return str_dur   

    def resize_check(self, widget, allocation):
        width = allocation.width
        required_width = (width - 340) / 2
        if required_width != self.column_width:
            for columnid in (1, 2):
                self.column_width = required_width
                column = self.treeview_cat.get_column(columnid)
                column.set_fixed_width(self.column_width - 40)
                column = self.treeview_p3d_lst.get_column(columnid)
                column.set_fixed_width(self.column_width)
                column = self.treeview_msg.get_column(columnid)
                column.set_fixed_width(self.column_width)
            column2 = self.treeview_sch.get_column(2)
            column2.set_fixed_width(self.column_width + 135)
            column4 = self.treeview_sch.get_column(4)
            column4.set_fixed_width(self.column_width + 135)

    # message dialogs
    def info_dialog(self, str_info):
        messagedialog = gtk.MessageDialog(None, 0, 
                    gtk.MESSAGE_INFO, gtk.BUTTONS_OK, 
                    str_info)
        messagedialog.run()
        messagedialog.destroy() 

    def warn_dialog(self, str_warn):
        m = gtk.MessageDialog(None, 0, 
                    gtk.MESSAGE_WARNING, gtk.BUTTONS_OK, 
                    str_warn)
        m.run()
        m.destroy()
    
    def error_dialog(self, str_error):
        messagedialog = gtk.MessageDialog(None, 0, 
                    gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, 
                    str_error)
        messagedialog.run()
        messagedialog.destroy()  

tdp = ThreeD_Player()
tdp.main()


'''
TO FIX
search
		fix to allow apostrophes
schedule
    lists in wrong orfer - mixes nq and sponsorship 
        when not listed beside show name
    'next message' button
    keyboard schortcuts for all schedule buttons.
'''
