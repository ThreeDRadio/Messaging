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

import pygtk
import gtk
import gobject
import pango
import sys
import psycopg2
import subprocess
import datetime
import pickle
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

tup_day = ("Monday", 
            "Tuesday", 
            "Wednesday", 
            "Thursday", 
            "Friday", 
            "Saturday", 
            "Sunday")

#lists 
select_items = (
    "cdtrack.trackid",
    "cdtrack.cdid",
    "cdtrack.tracknum",
    "cdtrack.tracktitle",
    "cdtrack.trackartist",
    "cd.artist",
    "cd.title",
    "cd.company",
    "cdtrack.tracklength"
    )

where_items = (
    "trackartist",
    "tracktitle",
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

# Look for config file in a few places, can now have a local version for testing.
configFile = config.read(['/usr/local/etc/threedradio.conf', '/etc/threedradio.conf', 'threedradio.conf'])


# Display an error message if we can't find a config file, and exit
if configFile == []:
    print "Could not find a config file. Giving up!"
    dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, "Could not find a config file.\nPlease report this on the bulletin board.\n\nGiving up!")
    dialog.set_title("Three D Message Player")
    dialog.run()
    exit()

#the serialwatch script to be run as a subprocess
dir_serialwatch = config.get('Paths', 'dir_serialwatch')
file_serialwatch = config.get('ThreeDPlayer', 'file_serialwatch')

dir_pl3d = config.get('Paths', 'dir_pl3d')

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
    This enable a dbus signal to activate the broadcast player. 
    The serialwatch script is used to send the signal.
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
        #for item in play_state:
        #    print(item)
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
    def __init__(self, time_label, progressbar, label_air_warning, check_join):
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
        window = gtk.Window(gtk.WINDOW_TOPLEVEL) 
        window.set_position(gtk.WIN_POS_CENTER)
        filepath_logo = dir_img + logo
        window.set_icon_from_file(filepath_logo)
        window.set_resizable(False)
        window.set_size_request(1240, 840)
        
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
        vbox_msg_btn.set_size_request(240, 460)
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
        #table for music catalogue search
        table_cat = gtk.Table(20, 2, False)
        #hbox for catalogue creator selection
        hbox_cat_creator = gtk.HBox(False, 5)
        #vbox for catalogue list
        vbox_cat_lst = gtk.VBox(False, 0)
        #scrolled window for catalogue list treeview
        sw_cat_lst = gtk.ScrolledWindow()
        sw_cat_lst.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_cat_lst.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        #hbox for list import
        hbox_pl3d = gtk.HBox(False, 5)
        # vbox for buttons and option for list import
        vbox_pl3d_opt = gtk.VBox(False, 5)
        #vbox for the imported list
        vbox_pl3d_lst = gtk.VBox(False, 5)
        #scrolled window for browsing pl3d files
        sw_pl3d_opt = gtk.ScrolledWindow()
        sw_pl3d_opt.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_pl3d_opt.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        #scrolled window for imported list
        sw_pl3d_lst = gtk.ScrolledWindow()
        sw_pl3d_lst.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_pl3d_lst.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        #hbox for the copy buttons below the imported list
        hbox_pl3d_btn = gtk.HBox(False, 5)      
        #hbox  for scheduler and preview
        hbox_sch_pre = gtk.HBox(False, 0)
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
        hbox_sch_pre = gtk.HBox(False, 5)
        # vbox for buttons and drop-down list
        vbox_sch_move = gtk.VBox(False, 0)
        #scrolled window for the schedule list
        sw_sch = gtk.ScrolledWindow()
        sw_sch.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_sch.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        # vbox for preview section
        vbox_pre = gtk.VBox(False, 0)  
        # hbox for preview player buttons
        hbox_pre_btn = gtk.HBox(False, 0)        

        
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
        store_msg = gtk.ListStore(str, str, str, str, str)
        self.treeview_msg = gtk.TreeView(store_msg)
        self.treeview_msg.set_rules_hint(True)
        treeselection_msg = self.treeview_msg.get_selection()
        self.add_msg_columns(self.treeview_msg)
        
        ### ----------------Music Catalogue Section---------------- ###
        
        label_cat = gtk.Label(" Music Catalogue ")
        label_cat.modify_font(header_font)        
        sep_cat_0 = gtk.HSeparator()
        label_cat_simple = gtk.Label("Simple Search")
        label_cat_simple.modify_font(subheader_font_1)
        self.entry_cat_simple = gtk.Entry(50)
        btn_cat_simple = gtk.Button("Search")
        btn_cat_simple.set_tooltip_text("Simple search")
        btn_cat_simple.set_size_request(80, 30)
        self.label_result_simple = gtk.Label()
        self.label_result_simple.set_size_request(80, 40)
        sep_cat_1 = gtk.HSeparator()
        label_cat_adv = gtk.Label("Advanced Search")
        label_cat_adv.modify_font(subheader_font_1)
        label_cat_artist = gtk.Label("Artist")
        self.entry_cat_artist = gtk.Entry(50)
        label_cat_album = gtk.Label("Album")
        self.entry_cat_album = gtk.Entry(50)
        label_cat_title = gtk.Label("Title")
        self.entry_cat_title = gtk.Entry(50)
        label_cat_cmpy = gtk.Label("Company")
        self.entry_cat_cmpy = gtk.Entry(50)
        label_cat_genre = gtk.Label("Genre")
        self.entry_cat_genre = gtk.Entry(50)        
        label_cat_com = gtk.Label("Comments")
        self.entry_cat_com = gtk.Entry(50)
        label_cat_creator = gtk.Label("Created by")
        self.cb_cat_creator = gtk.combo_box_new_text()
        self.cb_creator_add()       
        self.chk_cat_comp = gtk.CheckButton("Compilation", True)
        self.chk_cat_demo = gtk.CheckButton("Demo", True)
        self.chk_cat_local = gtk.CheckButton("Local", True)       
        self.chk_cat_fem = gtk.CheckButton("Female", True)
        label_cat_order = gtk.Label("Order by")
        self.cb_cat_order = gtk.combo_box_new_text()
        self.cb_order_add()
        btn_cat_adv = gtk.Button("Search")
        btn_cat_adv.set_tooltip_text("Advanced Search")
        self.label_result_adv = gtk.Label()
        self.label_result_adv.set_size_request(80, 40)
        
        ### ----------- Search Results Section -----------###

        label_results = gtk.Label("Search Results")
        label_results.modify_font(subheader_font_1)
        label_results.set_size_request(80, 30)

        #make the list
        self.store_cat = gtk.TreeStore(str ,str ,str ,str)
        self.treeview_cat = gtk.TreeView(self.store_cat)
        self.treeview_cat.set_rules_hint(True)
        treeselection_cat = self.treeview_cat.get_selection()
        self.add_cat_columns(self.treeview_cat)
        
        ### ----------- Playlist Import Section -----------###
        
        label_pl3d =  gtk.Label(" Import List ")
        label_pl3d.modify_font(header_font)
        label_pl3d_browse =  gtk.Label("Select a Playlist")
        label_pl3d_browse.set_size_request(220, 28)
        label_pl3d_browse.modify_font(subheader_font_1)
        
        # treeview for browsing playlists
        self.store_pl3d_browse = gtk.TreeStore(str)
        self.treeview_pl3d_browse = gtk.TreeView(self.store_pl3d_browse)
        self.treeview_pl3d_browse.set_rules_hint(True)
        treeselection_pl3d_browse = self.treeview_pl3d_browse.get_selection()
        column = gtk.TreeViewColumn('Select a Playlist', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_clickable(False)
        self.treeview_pl3d_browse.append_column(column)
        self.get_pl3d_browse(None)
        
        btn_pl3d_refresh = gtk.Button("Refresh")
        btn_pl3d_select = gtk.Button("Browse for a pl3d playlist")
        
        #treeview to display playlist
        store_pl3d_lst = gtk.ListStore(str ,str ,str ,str ,str)
        self.treeview_pl3d_lst = gtk.TreeView(store_pl3d_lst)        
        self.treeview_pl3d_lst.set_rules_hint(True)        
        self.treeview_pl3d_lst.set_rubber_banding(True)
        treeselection_pl3d_lst = self.treeview_pl3d_lst.get_selection()
        treeselection_pl3d_lst.set_mode(gtk.SELECTION_MULTIPLE)
        self.add_pl3d_columns(self.treeview_pl3d_lst)    
        btn_pl3d_copysel = gtk.Button("Copy selected tracks to the broadcast list")
        btn_pl3d_copyall = gtk.Button("Copy all tracks to the broadcast list")   


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
        bc_store = gtk.ListStore(str, str, str, str,
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

        
        self.player_bc = Broadcast_Player(self.label_bc_time, 
            self.progressbar, self.label_air_warning, self.check_join)

        btn_inf = gtk.Button("Info")
        btn_rem = gtk.Button("Remove")
        btn_hist = gtk.Button("History")
        btn_hist.set_tooltip_text("Show details of the music tracks played for back-announcing")
        btn_skip = gtk.Button("Skip to End")
        
        adj_spin = gtk.Adjustment(3, 1, 120, 1, 5, 0)
        self.spinbutton = gtk.SpinButton(adj_spin, 0, 0)
        self.spinbutton.set_numeric(True)
        self.spinbutton.set_tooltip_text("How many tracks to be shown in the history")
        
        btn_msg_3hr = gtk.Button("Msg 3hr")
        
        label_time_0 = gtk.Label("Playlist Total Time - ")
        self.label_time_1 = gtk.Label("00:00  ")

        ### ----------------Scheduler Section ---------------- ###

        # drop down list (combobox)
        self.cb_sch_prg = gtk.combo_box_new_text()

        # Label
        label_sch = gtk.Label("Schedule")
        label_sch.modify_font(header_font)
        label_sch.set_size_request(200, 30)   
             
        # Buttons
        btn_sch_refresh = gtk.Button(stock=gtk.STOCK_REFRESH)

        btn_sch_now = gtk.Button("now")
        btn_sch_add = gtk.Button("Add to Broadcast List")

        # make the scheduler list display
        self.store_sch = gtk.ListStore(str ,str, str, str)         
        self.treeview_sch = gtk.TreeView(self.store_sch)
        self.treeview_sch.set_rules_hint(True)
        treeselection_sch = self.treeview_sch.get_selection()
        self.add_sch_columns(self.treeview_sch)
        
        self.set_up_sch()

        ### ----------------Preview Section---------------- ###

        #preview Label
        label_pre = gtk.Label("Preview")
        label_pre.modify_font(header_font)
        label_pre.set_size_request(200, 30)
        # preview player buttons
        self.btn_pre_play_pause = gtk.Button()
        self.btn_pre_play_pause.set_image(self.image_play)
        btn_pre_stop = gtk.Button()
        btn_pre_stop.set_image(image_stop)
         
        #Label of track to preview
        self.str_dur="00:00"
        self.label_pre_play = gtk.Label()
        self.label_pre_play.set_width_chars(30)
        self.label_pre_play.set_tooltip_text("")
        self.label_pre_time = gtk.Label("00:00 / 00:00")        
        #create a list for holding details of message to play
        #[Message Title, Message Type, filename, msg/mus]
        self.list_pre = ["", "", "", ""]
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
        

        ### Date and Time ###
        # date label
        self.label_date = gtk.Label()
        self.label_date.modify_font(subheader_font)
        #time label
        self.label_time = gtk.Label()
        self.label_time.modify_font(header_font)   
        self.date_and_time()     


        ### dnd and connections ###
        self.treeview_cat.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                              [("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_pl3d_lst.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
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
        self.treeview_pl3d_lst.connect("drag_data_get", self.pl3d_drag_data_get_data)
        self.treeview_bc.connect("drag_data_get", self.bc_drag_data_get_data)
        self.treeview_sch.connect("drag_data_get", self.sch_drag_data_get_data)
        self.treeview_bc.connect("drag_data_received",
                              self.drag_data_received_data)
        self.treeview_sch.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                      [("copy-row", 0, 0)], 
                                      gtk.gdk.ACTION_COPY)

        window.connect("delete_event", self.delete_event)
        window.connect("destroy", self.destroy)
        treeselection_msg.connect('changed', self.msg_selection_changed)
        treeselection_cat.connect('changed', self.cat_selection_changed)
        treeselection_pl3d_browse.connect('changed', self.pl3d_browse_selection_changed)
        treeselection_pl3d_lst.connect('changed', self.cat_selection_changed)
        btn_cat_simple.connect("clicked", self.simple_search)
        self.entry_cat_simple.connect("activate", self.simple_search)        
        btn_cat_adv.connect("clicked", self.advanced_search)
        self.entry_cat_simple.connect("activate", self.simple_search)
        self.entry_cat_artist.connect("activate", self.advanced_search)
        self.entry_cat_album.connect("activate", self.advanced_search)
        self.entry_cat_title.connect("activate", self.advanced_search)
        self.entry_cat_cmpy.connect("activate", self.advanced_search)
        self.entry_cat_genre.connect("activate", self.advanced_search)
        self.entry_cat_com.connect("activate", self.advanced_search)
        btn_pl3d_refresh.connect("clicked", self.get_pl3d_browse)
        btn_pl3d_select.connect("clicked", self.get_pl3d)
        btn_pl3d_copysel.connect("clicked", self.copy_pl3d_sel)
        btn_pl3d_copyall.connect("clicked", self.copy_pl3d_all)
        treeselection_bc.connect('changed', self.bc_selection_changed)
        btn_testing.connect("clicked", self.test_bc)
        btn_inf.connect("clicked", self.info_row)
        btn_rem.connect("clicked", self.remove_row)
        btn_hist.connect("clicked", self.show_history)
        btn_skip.connect("clicked", self.skip_track)
        btn_msg_3hr.connect("clicked", self.show_msg_3hr)
        self.cb_sch_prg.connect("changed", self.go_to_programme)
        btn_sch_refresh.connect("clicked", self.refresh_sch)
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

        table_cat.attach(label_cat_artist, 0, 1, 0, 1, False, False, 5, 0)
        table_cat.attach(self.entry_cat_artist, 1, 2, 0, 1, False, False, 5, 0)
        table_cat.attach(label_cat_album, 0, 1, 1, 2, False, False, 5, 0)
        table_cat.attach(self.entry_cat_album, 1, 2, 1, 2, False, False, 5, 0)
        table_cat.attach(label_cat_title, 0, 1, 2, 3, False, False, 5, 0)
        table_cat.attach(self.entry_cat_title, 1, 2, 2, 3, False, False, 5, 0)
        table_cat.attach(label_cat_cmpy, 0, 1, 3, 4, False, False, 5, 0)
        table_cat.attach(self.entry_cat_cmpy, 1, 2, 3, 4, False, False, 5, 0)
        table_cat.attach(label_cat_com, 0, 1, 4, 5, False, False, 5, 0)
        table_cat.attach(self.entry_cat_com, 1, 2, 4, 5, False, False, 5, 0)
        table_cat.attach(label_cat_genre, 0, 1, 5, 6, False, False, 5, 0)
        table_cat.attach(self.entry_cat_genre, 1, 2, 5, 6, False, False, 5, 0)
        
        hbox_cat_creator.pack_start(label_cat_creator, False)
        hbox_cat_creator.pack_start(self.cb_cat_creator, False)
        vbox_cat_search.pack_start(sep_cat_0, False)
        vbox_cat_search.pack_start(label_cat_simple, False)
        vbox_cat_search.pack_start(self.entry_cat_simple, False)
        vbox_cat_search.pack_start(btn_cat_simple, False)
        vbox_cat_search.pack_start(self.label_result_simple, False)
        vbox_cat_search.pack_start(sep_cat_1, False)
        vbox_cat_search.pack_start(label_cat_adv, False)        
        vbox_cat_search.pack_start(table_cat, False)        
        vbox_cat_search.pack_start(hbox_cat_creator, False)
        vbox_cat_search.pack_start(self.chk_cat_comp, False)
        vbox_cat_search.pack_start(self.chk_cat_demo, False)
        vbox_cat_search.pack_start(self.chk_cat_local, False)
        vbox_cat_search.pack_start(self.chk_cat_fem, False)
        vbox_cat_search.pack_start(btn_cat_adv, False)     
        vbox_cat_search.pack_start(self.label_result_adv, False) 
        hbox_cat.pack_start(vbox_cat_search, False)    
        sw_cat_lst.add(self.treeview_cat)
        vbox_cat_lst.add(sw_cat_lst)
        hbox_cat.pack_start(vbox_cat_lst, True, True, 0)
    
        vbox_pl3d_opt.pack_start(label_pl3d_browse, False)
        sw_pl3d_opt.add(self.treeview_pl3d_browse)
        vbox_pl3d_opt.pack_start(sw_pl3d_opt, True)
        vbox_pl3d_opt.pack_start(btn_pl3d_refresh, False)
        vbox_pl3d_opt.pack_start(btn_pl3d_select, False)
        hbox_pl3d_btn.pack_start(btn_pl3d_copysel, False)
        hbox_pl3d_btn.pack_start(btn_pl3d_copyall, False)
        hbox_pl3d.pack_start(vbox_pl3d_opt, False)
        sw_pl3d_lst.add(self.treeview_pl3d_lst)
        vbox_pl3d_lst.pack_end(hbox_pl3d_btn, False)
        vbox_pl3d_lst.add(sw_pl3d_lst)
        hbox_pl3d.pack_start(vbox_pl3d_lst, True)

        sw_sch.add(self.treeview_sch)
        vbox_sch_move.pack_start(label_sch, False)
        vbox_sch_move.pack_start(btn_sch_refresh, False)
        #vbox_sch_move.pack_start(self.cb_sch_prg, False)
        vbox_sch_move.pack_start(btn_sch_now, False)
        vbox_sch_move.pack_end(btn_sch_add, False)
        hbox_sch_pre.pack_start(vbox_sch_move, False)
        hbox_sch_pre.pack_start(sw_sch, True, True, 0)
        
        hbox_pre_btn.pack_start(self.btn_pre_play_pause, False)
        hbox_pre_btn.pack_start(btn_pre_stop, False)
        vbox_pre.pack_start(label_pre, False)
        vbox_pre.pack_start(hbox_pre_btn, False)
        vbox_pre.pack_start(self.label_pre_play, False, False, 5)         
        vbox_pre.pack_start(self.hscale_pre)
        vbox_pre.pack_start(self.label_pre_time, False)
        vbox_pre.pack_start(self.label_date)
        vbox_pre.pack_start(self.label_time)
        hbox_sch_pre.pack_end(vbox_pre, False, False, 0)
        vbox_nb.pack_start(notebook, False, False, 5)
        notebook.append_page(hbox_msg, label_msg_btn)
        notebook.append_page(hbox_cat, label_cat)
        notebook.append_page(hbox_pl3d, label_pl3d)
        vbox_nb.pack_start(hbox_sch_pre, True, True, 0)       
        vbox_bc.pack_start(label_bc, False)
        vbox_bc.pack_start(self.label_air, False)
        #vbox_bc.pack_start(btn_testing, False)
        vbox_bc.pack_start(self.progressbar, False)
        hbox_bc_0.pack_start(self.label_bc_time, True)
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
        # run the loop to watch for serial signals
        sw_arg = dir_serialwatch + file_serialwatch
        pid = Popen(["/usr/bin/python2", sw_arg]).pid
        gtk.gdk.threads_init()

        gtk.main()

    # columns for the lists
    def add_msg_columns(self, treeview_msg):
        '''
        columns for the list of messages
        '''
        #Column ONE
        column = gtk.TreeViewColumn('Dict', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)

        # column TWO
        column = gtk.TreeViewColumn('CODE', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        self.treeview_msg.append_column(column)

        # column THREE
        column = gtk.TreeViewColumn('Message', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        treeview_msg.append_column(column)
        
        #Column FOUR
        column = gtk.TreeViewColumn('Ending', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        treeview_msg.append_column(column)
        
        #Column FIVE
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        treeview_msg.append_column(column)
 
    def add_bc_columns(self, treeview_bc):
        '''
        Columns for the broadcast list
        '''
        #Column ONE
        column = gtk.TreeViewColumn('Dict', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)

        #Column TWO
        column = gtk.TreeViewColumn(
            'Track Title', gtk.CellRendererText(), text=1)
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
            '', cell_pix, pixbuf=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        #column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        #column.set_fixed_width(26)
        self.treeview_bc.append_column(column)
        
    def add_sch_columns(self, treeview_sch):
        '''
        Columns for the schedule list
        '''
        #Column ONE
        column = gtk.TreeViewColumn('Dict', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)        
        
        #Column TWO
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                     text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        self.treeview_sch.append_column(column)

        #Column THREE
        column = gtk.TreeViewColumn('Programme', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        column.set_resizable(True)
        self.treeview_sch.append_column(column)
        
        #Column FOUR
        column = gtk.TreeViewColumn('Message', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        column.set_resizable(True)
        self.treeview_sch.append_column(column)     

    def add_cat_columns(self, treeview):
        '''
        Columns for the catalogue search results list
        '''
        
        #Column ONE
        column = gtk.TreeViewColumn('Dict', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)
        
        #Column TWO
        column = gtk.TreeViewColumn('Album / Title', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        #column.set_visible(False)
        column.set_max_width(360)
        column.set_resizable(True)
        column.set_clickable(False)
        treeview.append_column(column)

        #Column THREE
        column = gtk.TreeViewColumn('Artist', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        column.set_resizable(True)
        treeview.append_column(column)
                     
        #Column FOUR
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        treeview.append_column(column)

    def add_pl3d_columns(self, treeview):
        '''
        columns for the playlist list
        '''
        #Column ONE
        column = gtk.TreeViewColumn('Dict', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)
        
        
        #Column TWO
        column = gtk.TreeViewColumn('Title', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_max_width(360)
        column.set_resizable(True)
        column.set_clickable(False)
        treeview.append_column(column)

        #Column THREE
        column = gtk.TreeViewColumn('Artist', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        column.set_resizable(True)
        treeview.append_column(column)

        # column FOUR
        column = gtk.TreeViewColumn('Album', gtk.CellRendererText(),
                                    text=5)
        column.set_sort_column_id(5)
        column.set_clickable(False)
        column.set_resizable(True)
        treeview.append_column(column)

        #Column FIVE
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                    text=7)
        column.set_sort_column_id(7)
        treeview.append_column(column)
        column.set_clickable(False)
        
    # dnd    
    def msg_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        define drag n drop data retrieval for the message list.
        '''
        treeselection = treeview.get_selection()
        model, iter = treeselection.get_selected()
        tuple_data = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7, 8)
        list_data = list(tuple_data)
        list_data.append(False)
        tuple_data = tuple(list_data)
        str_data = str(tuple_data).strip('[]')
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, str_data)

    def cat_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        Define drag n drop data retrieval for the catalogue list.
        '''
        treeselection = treeview.get_selection()
        model, iter = treeselection.get_selected()
        tuple_data = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7, 8)
        list_data = list(tuple_data)
        list_data.append(False)
        tuple_data = tuple(list_data)
        str_data = str(tuple_data).strip('[]')
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, str_data)

    def pl3d_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        Define drag n drop data retrieval for the playlist list - allows
        selecting multiple rows.
        '''
        treeselection = treeview.get_selection()
        model = treeview.get_model()
        rows = treeselection.get_selected_rows()
        for row in rows:
            path = row[0]
        iter = model.get_iter(path)
        tuple_data = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7, 8)
        list_data = list(tuple_data)
        list_data.append(False)
        tuple_data = tuple(list_data)
        str_data = str(tuple_data).strip('[]')
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, str_data)

    def bc_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        Define drag n drop data retrieval for the broadcast list.
        '''
        treeselection = treeview.get_selection()
        model, iter = treeselection.get_selected()
        datatuple = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
        datastring = str(datatuple).strip('[]')
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, datastring)
        model.remove(iter)
        
    def sch_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        Define drag n drop data retrieval for the schedule list.
        '''
        treeselection = treeview.get_selection()
        model, iter = treeselection.get_selected()
        datatuple = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7, 8)
        print (datatuple)
        code = datatuple[3]
        filename = datatuple[7]
        message = datatuple[4]
        nq = datatuple[6]
        msg_type = datatuple[5]
        dur = datatuple[8]
        if dur:
            time = self.convert_time(dur)
        else:
            time = 'N/A'    
        datalist = ["msg", code, filename, message, nq, msg_type, "None", time, dur, False]
        
        datatuple = tuple(datalist)
        datastring = str(datatuple)
        #print('Printing datastring')
        #print(datastring)
        
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, datastring)
  
    def drag_data_received_data(self, treeview, context, x, y, selection,
                                info, etime):
        '''
        Adding data from drag n drop into the broadcast list.
        '''

        str_data = selection.get_text()
        tuple_data = eval(str_data)    
        path_img = dir_img + img_blank        
        px = gtk.gdk.pixbuf_new_from_file(path_img)          
        list_data = list(tuple_data)
        list_data.append(px)
        model = treeview.get_model()
        
        filepath = self.get_filepath(tuple_data)
        if not os.path.isfile(filepath):
            if tuple_data[0] == "mus":
                str_error = "Unable to add to the list, file does not exist."\
                "That track has probably not yet been ripped into the "\
                "music store"
                self.error_dialog(str_error) 
            else:
                str_error = "Unable to add to the list, file does not exist"
                self.error_dialog(str_error) 
            return     
        if str_data[0]:
            drop_info = treeview.get_dest_row_at_pos(x, y)
            if drop_info:                
                path, position = drop_info
                iter = model.get_iter(path)
                if (position == gtk.TREE_VIEW_DROP_BEFORE
                    or position == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                    model.insert_before(iter, list_data)
                    self.join_drop(model, iter, True)

                else:
                    model.insert_after(iter, list_data)
                    self.join_drop(model, iter, False)
                    
            else:
                model.append(list_data)
            if context.action == gtk.gdk.ACTION_MOVE:
                context.finish(True, True, etime)

            self.update_time_total()                    
            iter_top = model.get_iter_first()        
            if model.iter_next(iter_top):
                self.refresh_list(model)               
              
        else:
            print("empty field, nothing added")

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
            button.set_size_request(215, 24)
            tooltip = msg_type[1]
            button.set_tooltip_text(tooltip)
            button.connect("clicked", self.msg_btn_clicked, button_id)
            self.vbox_sw_msg_btn.pack_start(button, False)

    def msg_btn_clicked(self, clicked, msg_type):
        """
        When a button is clicked get messages of that type and 
        display them in the list
        """
        messages = self.query_type(msg_type)
        self.new_msg_list(messages, msg_type)
        
    def query_type(self, msg_type):
        '''
        query the database for messages of a given type
        '''
        
        today = datetime.date.today()
        columns = "code, filename, title, nq, fldproducer, duration"
        query = "SELECT {0} FROM messagelist WHERE LOWER(type)=LOWER('{1}') AND expirydate > '{2}' ORDER BY title".format (columns, msg_type, today)
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        messages = cur.fetchall()  
        cur.close()
        conn.close()
        return messages
        
    def new_msg_list(self, messages, msg_type):
        '''
        populate the message list with messages of the given type that 
        were retrieved from the database
        '''
        model = self.treeview_msg.get_model()     
        #clear existing rows
        model.clear()
        #add new rows
        for item in messages:
            msg = "msg"
            code = item[0]
            filename = item[1]
            title = item[2]
            nq = item[3]
            producer = item[4]
            duration = item[5]

            if duration:
                time = self.convert_time(duration)
            else:
                time = "NA"

            row = (msg, code, filename, title, nq, msg_type, producer, time, duration)
            model.append(row)

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
        result = self.query_simple()
        simple = True
        if result:
            self.length_check(result)
            self.add_to_cat_store(result)
            int_res = len(result)
           
        else:
            self.clear_cat_list()
            int_res = 0
            
        print("number of hits")
        print(int_res)  
        
        self.update_result_label(int_res, simple)
                                
    def query_simple(self):
        '''
        queries the database for matches to the simple search string in title 
        and artist columns for CDs and CD tracks. References global variables
        'select_items' and 'where_items'
        '''    
        str_error_none = "No search terms were entered"
        str_error_len = "Please enter more than three characters in your search"
            
        searchitem = self.entry_cat_simple.get_text()
        if not searchitem:
            self.error_dialog(str_error_none)
            return False
            
        if len(searchitem) < 3:
            self.error_dialog(str_error_len)
            return False
        
        conn = self.pg_connect_cat()

        str_select = "SELECT "
        for s in select_items:    
            str_select = str_select + s + ", "

        str_select = str_select.rstrip(", ")

        str_from = " from cdtrack inner JOIN cd on cdtrack.cdid=cd.id "
        str_where = "where "
        for s in where_items:
            str_where = str_where + s + " ilike '%" + searchitem + "%' or "

        str_where = str_where.rstrip(" or ")
        str_order = "order by cd.title, cdtrack.tracknum "
        str_limit = "LIMIT " + str(query_limit)

        query = str_select + str_from + str_where + str_order + str_limit

        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        
        return result

    def length_check(self, result):
        '''
        Display a message if the number of results returned is the maximum
        '''
        if len(result) == query_limit:
            str_warn_0 = "Warning - your query returned "
            str_warn_1 = " or more results. Only displaying the first "
            str_warn_2 = ". Please modify your search and be more specific."
            str_warn = str_warn_0 + str(query_limit) + str_warn_1 + str(query_limit) + str_warn_2
            self.warn_dialog(str_warn)

    def add_to_cat_store(self, result):
        '''
        populate the catalogue list with the results of a search
        '''
        self.clear_cat_list()
        var_album = ""
        mus = "mus"
        model = self.treeview_cat.get_model()
        for item in result:
            album = item[6]
            track_id = str(item[0])
            cd_code = str(format(item[1], '07d'))
            track_no = str(format(item[2], '02d'))
            cd_track_code = cd_code + "-" + track_no
            title = item[3]
            tr_artist = item[4]
            artist = item[5]
            if not tr_artist:
                tr_artist = artist
                
            company = item[7]
            int_time = item[8]
            dur_time = self.convert_time(int_time)
            
            if not album:
                album = "(No Title)"

            if not album == var_album:                
                n = model.append(None, [None, None, None, album, artist, None, None, None, 0])
                model.append(n, [mus, track_id, cd_track_code, title, tr_artist, album, company, dur_time, int_time])
            else:
                model.append(n, [mus, track_id, cd_track_code, title, tr_artist, album, company, dur_time, int_time])
            var_album = album

    def advanced_search(self, widget):
        '''
        run functions to get the advanced search input, query the database 
        and display the results
        '''
        result = self.query_adv()
        simple = False
        if result:
            self.length_check(result)
            self.add_to_cat_store(result)
            int_res = len(result)
            
        else:
            self.clear_cat_list()
            int_res = 0
        
  
        self.update_result_label(int_res, simple)
    
    def query_adv(self):
        '''
        Get the entries for an advanced search and query the database
        '''
        #obtain text from entries and combos
        artist = self.entry_cat_artist.get_text()
        album = self.entry_cat_album.get_text()
        title = self.entry_cat_title.get_text()
        company = self.entry_cat_cmpy.get_text()
        comments = self.entry_cat_com.get_text()
        genre = self.entry_cat_genre.get_text()
        created_by = self.cb_cat_creator.get_active_text()
        if created_by:
            ls_creator = created_by.split(',')
            created_by = ls_creator[0]
        compil = self.chk_cat_comp.get_active()
        demo = self.chk_cat_demo .get_active()
        local = self.chk_cat_local.get_active()
        female = self.chk_cat_fem.get_active()
        #query according to the text
        
        str_error_none = "No search terms were entered"
        str_error_len = "Please enter more than three characters in your search"
        
        if not artist and not album and not title and not company and not comments and not genre:
            self.error_dialog(str_error_none)
            return False
            
        for item in (artist, album, title, company, comments, genre):
            if item:
                if len(item) < 3:
                    self.error_dialog(str_error_len)
                    return False
        
        if artist:
            q_artist = "(cd.artist ILIKE '%" + artist + "%' OR cdtrack.trackartist ILIKE '%" + artist + "%') AND "
        else:
            q_artist = None
        if album:
            q_album = "cd.title ILIKE '%" + album + "%' AND "
        else:
            q_album = None
        if title:
            q_title = "cdtrack.tracktitle ILIKE '%" + title + "%' AND "
        else:
            q_title = None
        if company:
            q_company = "cd.company ILIKE '%" + company + "%' AND "
        else:
            q_company = None
        if comments:
            q_comments = "cdcomment.comment ILIKE '%" + comments + "%' AND "
        else:
            q_comments = None
        if genre:
            q_genre = "cd.genre ILIKE '%" + genre + "%' AND "
        else:
            q_genre = None
        if created_by:
            q_created_by = "cd.createwho = " + created_by + " AND "
        else:
            q_created_by = None        
        if compil:
            q_compil = "cd.compilation = 2 AND "
        else:
            q_compil = None
        if demo:
            q_demo = "cd.demo = 2 AND "
        else:
            q_demo = None
        if local:
            q_local = "cd.local = 2 AND "
        else:
            q_local = None
        if female:
            q_female = "cd.female = 2 AND "
        else:
            q_female = None
        
        str_select = "SELECT "
        for s in select_items:    
            str_select = str_select + s + ", "        
        str_select = str_select.rstrip(", ")
        str_from = " FROM cdtrack INNER JOIN cd ON cdtrack.cdid=cd.id "
        str_where = "WHERE "
        
        adv_var = (
            q_artist,
            q_album,
            q_title,
            q_company,
            q_comments,
            q_genre,
            q_created_by,
            q_compil,
            q_demo,
            q_local,
            q_female,
            )
            
        for item in adv_var:
            if item:
                str_where = str_where + item
      
        str_where = str_where.rstrip("AND ")
        
        str_order = " ORDER BY cd.title, cdtrack.tracknum "
        str_limit = "LIMIT " + str(query_limit)

        query = str_select + str_from + str_where + str_order + str_limit        

        conn = self.pg_connect_cat()
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()        
        
        return result

    def get_creator(self):
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
        return list_creator

    def cb_creator_add(self):
        '''
        Populate the drop down list in the catalogue advanced search with the 
        names of members who have added data to the catalogue
        '''
        liststore_creator = gtk.ListStore(str)        
        list_creator = self.get_creator()
        for item in list_creator:
            str_creator = str(item[0]) + ", " + item[1] + " " + item[2]
            self.cb_cat_creator.append_text(str_creator)
        self.cb_cat_creator.prepend_text("")

    def get_order(self):
        '''
        not yet implemented - for determining the order in which to display
        search results
        '''
        model = self.cb_cat_order.get_model()
        active = self.cb_cat_order.get_active()
        if active < 0:
          return None
        return model[active][0]

    def cb_order_add(self):
        '''
        not yet implemented - Populate a drop down box with details of the 
        order in which to display search results
        '''
        list_order = ["Artist Alphabetical",
            "Album Alphabetical",
            "Most recent first",
            "Oldest First"]
        for item in list_order:
            self.cb_cat_order.append_text(item)
        self.cb_cat_order.set_active(0)

    def clear_cat_list(self):
        '''
        Clear the cataloge list of all search results 
        '''
        model = self.treeview_cat.get_model()
        model.clear()

    def update_result_label(self, int_res, simple):
        if int_res < 200 :
            str_results = "Your search returned {0} results".format(int_res)
            if simple:
                self.label_result_simple.set_text(str_results)
                self.label_result_adv.set_text("")
            else:
                self.label_result_adv.set_text(str_results)
                self.label_result_simple.set_text("")  
        else:
            self.label_result_adv.set_text("")
            self.label_result_simple.set_text("")

    def cat_selection_changed(self, selection):
        playstatus = self.player_pre.get_state() 
        if (not playstatus == gst.STATE_PLAYING) and (not playstatus == gst.STATE_PAUSED):
            model, path = selection.get_selected_rows()
            if path:
                iter = model.get_iter(path[0])
                mus = model.get_value(iter, 0)
                if mus:
                    #title
                    self.list_pre[0] = model.get_value(iter, 3)
                    #CD Code/Track No
                    self.list_pre[1] = model.get_value(iter, 2)
                    #filename
                    self.list_pre[2] = model.get_value(iter, 2)
                    #identify as msg
                    self.list_pre[3] = mus
                    self.label_pre_play.set_label(self.list_pre[0])
                    if len(self.list_pre[0]) > 30:
                        self.label_pre_play.set_tooltip_text(self.list_pre[0]) 
                    else:
                        self.label_pre_play.set_tooltip_text("")

    def get_cat_filepath(self, ID):
        filename = ID + ".mp3"
        dir_cd = ID[0:-3] + "/"
        filepath = dir_mus + dir_cd + filename
        return filepath

    # list import section (pl3d)
    def get_pl3d_browse(self, widget):
        self.store_pl3d_browse.clear()
        parents = {}
        for top_dir, dirs, files in os.walk(dir_pl3d):
            for subdir in dirs:
                parents[os.path.join(top_dir, subdir)] = self.store_pl3d_browse.append(parents.get(top_dir, None), [subdir])
            for item in files:
                self.store_pl3d_browse.append(parents.get(top_dir, None), [item])

    def get_pl3d(self, widget):
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
        dialog.set_current_folder(dir_pl3d)
        dialog.set_do_overwrite_confirmation(True)

        filter = gtk.FileFilter()
        filter.set_name("Playlist files")
        filter.add_pattern("*.pl3d")

        dialog.add_filter(filter)

        response = dialog.run()
        filename = dialog.get_filename()
        if response == gtk.RESPONSE_OK:
            self.load_playlist(filename)
        dialog.destroy()

    def load_playlist(self, filepath):
        playlist = self.pl3d2pylist(filepath)
        model = self.treeview_pl3d_lst.get_model()
        model.clear()
        for item in playlist:
            model.append(item)
            
    def pl3d2pylist(self, filename):
        '''
        convert the information in an pl3d file to a python list
        '''
        doc = etree.parse(filename)
        pl3d_ns = "http://xspf.org/ns/0/"
        ns = "{%s}" % pl3d_ns

        el_tracklist = doc.findall("//%strack" % ns)

        ls_tracklist = []

        for track in el_tracklist:

            if track.find("%stitle" % ns) is not None:
                str_title = track.find("%stitle" % ns).text
            else:
                str_title = None
            
            #identifier is trackid    
            if track.find("%sidentifier" % ns) is not None:
                str_identifier = track.find("%sidentifier" % ns).text
            else:
                str_identifier = None
                
            #location is cdid-trackno
            if track.find("%slocation" % ns) is not None:
                str_location = track.find("%slocation" % ns).text
            else:
                str_location = None

            if track.find("%salbum" % ns) is not None:
                str_album = track.find("%salbum" % ns).text
            else:
                str_album = None     
            
            #creator is artist               
            if track.find("%screator" % ns) is not None:
                str_creator = track.find("%screator" % ns).text
            else:
                str_creator = None
            
            #annotation is company    
            if track.find("%sannotation" % ns) is not None:
                str_annotation = track.find("%sannotation" % ns).text
            else:
                str_annotation = None

            if track.find("%sduration" % ns) is not None:
                str_duration = track.find("%sduration" % ns).text
            else:
                str_duration = None
            
            if not str_duration:
                str_duration = 0
            str_duration = int(str_duration)/1000
            str_time = self.convert_time(str_duration)
            
            mus = "mus"
            tp_track = (
                mus,
                str_identifier,
                str_location, 
                str_title,  
                str_creator,
                str_album,                  
                str_annotation,
                str_time, 
                str_duration
                )
                
            ls_tracklist.append(tp_track)
            
        return ls_tracklist

    def pl3d_browse_selection_changed(self, selection):
        model, path = selection.get_selected_rows()
        iter = model.get_iter(path[0])
        self.add_playlist(model, iter)
        
    def add_playlist(self, model, iter):

        if model.iter_has_child(iter):
            return
        file_pl3d = model.get(iter, 0)[0]
        
        while iter:
            iter = model.iter_parent(iter)
            if iter:
                parent_dir = model.get(iter, 0)[0]
                file_pl3d = os.path.join(parent_dir, file_pl3d)
                filepath = os.path.join(dir_pl3d, file_pl3d)
                
            else:
                filepath = os.path.join(dir_pl3d, file_pl3d)
        self.load_playlist(filepath)        

    def copy_pl3d_sel(self, widget):
        model_bc = self.treeview_bc.get_model()
        treeselection = self.treeview_pl3d_lst.get_selection()
        model = self.treeview_pl3d_lst.get_model()
        rows = treeselection.get_selected_rows()
        row = rows[1]
        for path in row:
            iter = model.get_iter(path)
            tuple_data = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7, 8)
            list_data = list(tuple_data)
            list_data.append(False)
            tuple_data = tuple(list_data)
            self.copy_track(tuple_data, model_bc)
        self.update_time_total() 
            
    def copy_pl3d_all(self, widget):
        model_bc = self.treeview_bc.get_model()
        model = self.treeview_pl3d_lst.get_model()
        iter = model.get_iter_first()
        while iter:
            tuple_data = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7, 8)
            list_data = list(tuple_data)
            list_data.append(False)
            tuple_data = tuple(list_data)
            self.copy_track(tuple_data, model_bc)
            iter = model.iter_next(iter)
        self.update_time_total()                    
        #iter_top = model_bc.get_iter_first()        
        #if model_bc.iter_next(iter_top):
        #    self.refresh_list(model_bc)
        
    def copy_track(self, tuple_data, model):        
        track = str(tuple_data[3])
        filepath = dir_img + img_blank
        px = gtk.gdk.pixbuf_new_from_file(filepath)        
        list_data = list(tuple_data)
        list_data.append(px)
        str_error_0 = "Unable to add to the list, '"
        str_error_1 = "' can't be found "
        str_error_2 = "That track has probably not yet been ripped into the music store"
        
        filepath = self.get_filepath(tuple_data)
        if not os.path.isfile(filepath):
            if list_data[0] == "mus":
                str_error = str_error_0 + track + str_error_1 + str_error_2
                self.error_dialog(str_error) 
            else:
                str_error = str_error_0 + track + str_error_1
                self.error_dialog(str_error) 
            return  
        model.append(list_data)


    # broadcast section        
    def remove_row(self, widget):    
        treeselection = self.treeview_bc.get_selection()
        model, iter = treeselection.get_selected()
        if iter:
            model.remove(iter) 
            model = self.treeview_bc.get_model()
        else:
            print("Nothing selected")
        iter = model.get_iter_first()
        if iter:
            self.refresh_list(model)
            self.update_time_total()
        
    def info_row(self, widget):    
        treeselection = self.treeview_bc.get_selection()
        model, iter = treeselection.get_selected()
        try:
            datatuple = model.get(iter, 0, 1, 3, 4, 5, 6)
            print(datatuple)
            if datatuple[0] == "msg":
                self.info_message(datatuple)
            elif datatuple[0] == "mus":
                 self.info_music(datatuple)
        except TypeError:
            pass
        return    
        
    def show_history(self, widget):
        dialog = gtk.Dialog("History", None, 
            gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_NO_SEPARATOR, buttons=None)
        #dialog.set_size_request(420, 60)
        history_list = self.get_history()
        sw = gtk.ScrolledWindow()
        sw.set_size_request(560, 440)
        vbox = gtk.VBox(False, 0)
        if history_list:
            for item in history_list:
                str_blank = ""
                if item[1]:
                    str_artist = item[1]
                else:
                    str_artist = item[2]
                str_artist = "Artist: " + str_artist
                str_track = item[0]
                str_track = "Track: " + str_track
                str_cd = item[3]
                str_cd = "Album: " + str_cd
                str_cmpy = item[4]
                str_cmpy = "Company: " + str_cmpy 
                dt = item[5]  

                now = datetime.datetime.now()
                nowdate = now.date()
                dtdate = dt.date()
                if dtdate < nowdate:
                    str_time = dt.strftime("%A %d %B  %I:%M%p")
                else:
                    str_time = dt.strftime("%I:%M%p")
                str_time = "Played: " + str_time
                
                label = gtk.Label(str_time)
                vbox.pack_start(label, False)
                label.show()
                label = gtk.Label(str_artist)                
                label.modify_font(subheader_font_1)
                label.set_alignment(0, 0)
                vbox.pack_start(label, False)
                label.show()
                label = gtk.Label(str_track)                
                label.modify_font(subheader_font_1)
                label.set_alignment(0, 0)
                vbox.pack_start(label, False)
                label.show()
                list_history = [str_cd, str_cmpy, str_blank]
                for item in list_history:
                    label = gtk.Label(item)
                    label.set_alignment(0, 0)
                    vbox.pack_start(label, False)
                    label.show()
        sw.add_with_viewport(vbox)
        dialog.vbox.pack_start(sw, True)
        vbox.show()
        sw.show()
        dialog.run()
        dialog.destroy()

    def get_history(self):
        value = self.spinbutton.get_value_as_int()
        fqhn = socket.gethostname()
        hostname = fqhn.split(".")[0]
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        query = "SELECT when_played, id_code FROM playlog WHERE id_type = 'mus' and hostname = '{0}' ORDER BY when_played DESC LIMIT {1}".format(hostname, value)
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        if result:
            history_list = self.query_history(result)
            #history_list.reverse()  
        else:
            history_list = None
        return history_list
        
    def query_history(self, result):
        conn = self.pg_connect_cat()
        cur = conn.cursor()
     
        select_items = (
            "cdtrack.trackid",
            "cdtrack.cdid",
            "cdtrack.tracknum",
            "cdtrack.tracktitle",
            "cdtrack.trackartist",
            "cd.artist",
            "cd.title",
            "cd.company",
            "cdtrack.tracklength"
            )        
      
        history_list = []
        dim_select_items = select_items[3:8]
        str_select = "SELECT "
        for s in dim_select_items:    
            str_select = str_select + s + ", "

        str_select = str_select.rstrip(", ")        
        str_from = " from cdtrack inner JOIN cd on cdtrack.cdid=cd.id "        
        for item in result:
            str_where = "WHERE"        
            str_where = str_where + " cdtrack.trackid = " + "'" + item[1] + "'"

            query = str_select + str_from + str_where
            cur.execute(query)
            history_item = cur.fetchall()
	    history_item = list(history_item[0])
	    history_item.append(item[0])
	    history_item = tuple(history_item)
	    history_list.append(history_item)
	    print(history_list)

        cur.close()
        conn.close()
        
        '''
        # This adds the time to the end of each tuple in the query result
        v, n, stop = True, 0, len(result) 

        while n < stop:
            try: 
                tp = (result[n][0], )
                history_list[n] = history_list[n] + tp
                n+=1
            except IndexError:    
                print("error with processing history")   
                stop = 0    
        
        history_list = sorted(history_list,  key=itemgetter(-1), reverse = True)
        '''    
        return history_list
        
    def info_message(self, datatuple):
        code = datatuple[1]
        title = datatuple[2]
        ending = datatuple[3]
        msg_type = datatuple[4]
        
  
        head_txt = "Message Information"
        title_txt = "Title: {0}".format (title)
        ending_txt = "Ending: {0}".format (ending)
        type_txt = "Type: {0}".format (msg_type)
        code_txt = "Code {0}".format (code)

        label_head = gtk.Label(head_txt)
        label_head.modify_font(subheader_font_1)
        label_title = gtk.Label(title_txt)
        label_ending = gtk.Label(ending_txt)
        label_type = gtk.Label(type_txt)
        label_code = gtk.Label(code_txt)
        dialog = gtk.Dialog("Information", None, 0, (gtk.STOCK_OK, gtk.RESPONSE_OK))
        dialog.set_default_size(350, 150)
        dialog.vbox.pack_start(label_head, True, True, 0)
        dialog.vbox.pack_start(label_title, True, True, 0)
        dialog.vbox.pack_start(label_ending, True, True, 0)
        dialog.vbox.pack_start(label_type, True, True, 0)
        dialog.vbox.pack_start(label_code, True, True, 0)
        
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def info_music(self, datatuple):
        title = datatuple[2]
        artist = datatuple[3]
        album = datatuple[4]
        company = datatuple[5]    
        
        head_txt = "Track Information"
        title_txt = "Title: {0}".format (title)
        artist_txt = "Artist: {0}".format (artist)
        album_txt = "Album: {0}".format (album)
        cmpy_txt = "Company: {0}".format (company)

        label_head = gtk.Label(head_txt)
        label_head.modify_font(subheader_font_1)
        label_title = gtk.Label(title_txt)
        label_artist = gtk.Label(artist_txt)
        label_album = gtk.Label(album_txt)
        label_cmpy = gtk.Label(cmpy_txt)
        dialog = gtk.Dialog("Information", None, 0, (gtk.STOCK_OK, gtk.RESPONSE_OK))
        dialog.set_default_size(350, 150)
        dialog.vbox.pack_start(label_head, True, True, 0)
        dialog.vbox.pack_start(label_artist, True, True, 0)
        dialog.vbox.pack_start(label_title, True, True, 0)
        dialog.vbox.pack_start(label_album, True, True, 0)
        dialog.vbox.pack_start(label_cmpy, True, True, 0)
        
        dialog.show_all()
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
        fqhn = socket.gethostname()
        hostname = fqhn.split(".")[0]
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        query = "SELECT playlog.when_played, playlog.id_code, messagelist.title FROM playlog JOIN messagelist ON playlog.id_code=messagelist.code WHERE playlog.when_played > '{0}' AND hostname = '{1}' ORDER BY playlog.when_played DESC".format (now_less3, hostname)
        cur.execute(query)
        list_msg_3hr = cur.fetchall()
        cur.close()
        conn.close()
        
        return list_msg_3hr     
        
    def show_msg_3hr(self, widget):
        dialog = gtk.Dialog("Messages Played in the last 3 Hours", None, 
            gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_NO_SEPARATOR, buttons=None)
        #dialog.set_size_request(420, 60)
        list_msg_3hr = self.get_msg_3hr()
        sw = gtk.ScrolledWindow()
        sw.set_size_request(360, 340)
        vbox = gtk.VBox(False, 0)
        for item in list_msg_3hr:
            str_dt = item[0].strftime("%c")
            str_code = item[1]
            str_title = item[2]
            str_blank = ""
            list_history = [str_dt, str_code, str_title, str_blank]
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

    def date_and_time(self):
        self.label_date.set_text(time.strftime(("%A %d %B")))
        self.label_time.set_text(time.strftime('%H:%M %p'))
        gtk.timeout_add(1000, self.date_and_time)

    def get_top_track(self):
        model = self.treeview_bc.get_model()
        iter = model.get_iter_first()
        return model, iter
    
    def get_bc_filepath(self):
        model, iter = self.get_top_track()
        try:
            top_track = model.get(iter, 0, 1, 2, 3, 4, 5, 6)
        except TypeError:
            filepath = ""
            return filepath 
        
        filepath = self.get_filepath(top_track)
        return filepath

    def get_bc_title(self):
        model = self.treeview_bc.get_model()
        iter = model.get_iter_first()
        title = model.get(iter, 3)[0]
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
        model, iter = self.get_top_track()
        top_track = model.get(iter, 0, 1)
        id_code = top_track[1]
        id_type = top_track[0]
        dt_now = datetime.datetime.now()
        str_dt_now = str(dt_now)[0:19]
        fqhn = socket.gethostname()
        hostname = fqhn.split(".")[0]
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        query = "INSERT INTO playlog (when_played, id_code, id_type, hostname) VALUES ('{0}', '{1}', '{2}', '{3}')".format (str_dt_now, id_code, id_type, hostname)
        cur.execute(query)
        conn.commit()
        cur.close()
        conn.close()
        
    def delete_top_row(self):
        # Delete the top row from the list
        model, iter = self.get_top_track()
        if iter:
            model.remove(iter)

    def serial_signal(self):
        '''if the broadcast player is playing then stop it playing
        if it is not playing then 
        if there are queued tracks then start playing them
        remove the top track from the list and log to database.
        otherwise do nothing 
        '''
        state = self.player_bc_get_state()
        if  state == gst.STATE_NULL:
            filepath = self.get_bc_filepath()
            
            if os.path.isfile(filepath):                
                self.label_air_warning("playing")
                self.player_bc_start(filepath)
                title = self.get_bc_title()
                self.progressbar.set_text(title)
                self.log_played_track()                
                self.delete_top_row()
                self.update_time_total()

            else:
                print "no file found"
                #check for top row
                self.delete_top_row()
                self.update_time_total()
                self.check_join()

        '''
        This is no longer required. It used to
        stop a playing track if the desk play button was pressed

        else:
            self.player_bc_stop()
            self.progressbar.set_text("")
            self.label_air_warning("not playing")
            
            #set the 'join' status to false and reset the image)
            model = self.treeview_bc.get_model()
            iter = model.get_iter_first()
            if iter:
                self.set_bool(iter, False)
                iter_next = model.iter_next(iter)
                if iter_next:
                    self.refresh_list(model)
                else:
                    self.set_pixbuf(iter, img_blank)
        '''

    def test_bc(self, widget):
        self.serial_signal()

    def check_join(self):
        model = self.treeview_bc.get_model()
        iter = model.get_iter_first()
        if iter:
            bool = model.get_value(iter, 9)
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
        iter = model.get_iter((int_path, )) 
        if model.iter_next(iter):
            int_path_post = int_path + 1
            iter_post = model.get_iter((int_path_post, ))
            b = model.get_value(iter, 9)
            c = model.get_value(iter_post, 9)
            
            if b and c:
                self.set_bool(iter, False)
                self.set_pixbuf(iter, img_top)
            
            if not b and c:
                self.set_bool(iter, True)
                self.set_pixbuf(iter, img_mid)
                
            if b and not c:
                self.set_bool(iter, False)
                self.set_pixbuf(iter, img_blank)
            
            if not b and not c:
                self.set_bool(iter, True)
                self.set_pixbuf(iter, img_btm)
        else:
            if model.get_value(iter, 9):
                self.set_bool(iter, False)
                self.set_pixbuf(iter, img_blank)
            else:
                self.set_bool(iter, True)
                self.set_pixbuf(iter, img_btm)

    def join_tracks(self, model, int_path):                 
        int_path_pre = int_path - 1
        int_path_post = int_path + 1
        iter = model.get_iter((int_path, )) 
        iter_pre = model.get_iter((int_path_pre, ))
        a = model.get_value(iter_pre, 9)
        b = model.get_value(iter, 9)
        try:
            iter_post = model.get_iter((int_path_post, ))
            c = model.get_value(iter_post, 9)
        except ValueError:
            c = False
        
        if not a and not b and not c:
            self.set_bool(iter, True)
            self.set_pixbuf(iter_pre, img_top)
            self.set_pixbuf(iter, img_btm)
            
        if a and not b and not c:
            self.set_bool(iter, True)
            self.set_pixbuf(iter_pre, img_mid)
            self.set_pixbuf(iter, img_btm)
        
        if a and not b and c:
            self.set_bool(iter, True)
            self.set_pixbuf(iter_pre, img_mid)
            self.set_pixbuf(iter, img_mid)
        
        if not a and not b and c:
            self.set_bool(iter, True)
            self.set_pixbuf(iter_pre, img_top)
            self.set_pixbuf(iter, img_mid)
        
        if not a and b and not c:
            self.set_bool(iter, False)
            self.set_pixbuf(iter_pre, img_blank)
            self.set_pixbuf(iter, img_blank)
        
        if a and b and not c:
            self.set_bool(iter, False)
            self.set_pixbuf(iter_pre, img_btm)
            self.set_pixbuf(iter, img_blank)
        
        if a and b and c:
            self.set_bool(iter, False)
            self.set_pixbuf(iter_pre, img_btm)
            self.set_pixbuf(iter, img_top)
        
        if not a and b and c:
            self.set_bool(iter, False)
            self.set_pixbuf(iter_pre, img_blank)
            self.set_pixbuf(iter, img_top)

    def refresh_list(self, model):
        #first check if there is only one row
        iter = model.get_iter_first()
        if not model.iter_next(iter):
            if model.get_value(iter, 9):
                self.set_pixbuf(iter, img_btm)
            else:
                self.set_pixbuf(iter, img_blank)
        else:
            int_path = 1
    
            while int_path:       
                int_path_pre = int_path - 1
                int_path_post = int_path + 1
                iter = model.get_iter((int_path, )) 
                iter_pre = model.get_iter((int_path_pre, ))
                a = model.get_value(iter_pre, 9)
                b = model.get_value(iter, 9)
                try:
                    iter_post = model.get_iter((int_path_post, ))
                    c = model.get_value(iter_post, 1)
                except ValueError:
                    c = False
                
                if not a and not b and not c:
                    self.set_pixbuf(iter_pre, img_blank)
                    self.set_pixbuf(iter, img_blank)
                    
                if a and not b and not c:
                    self.set_pixbuf(iter_pre, img_btm)
                    self.set_pixbuf(iter, img_blank)
                
                if a and not b and c:
                    self.set_pixbuf(iter_pre, img_btm)
                    self.set_pixbuf(iter, img_top)
                
                if not a and not b and c:
                    self.set_pixbuf(iter_pre, img_blank)
                    self.set_pixbuf(iter, img_top)
                
                if not a and b and not c:
                    self.set_pixbuf(iter_pre, img_top)
                    self.set_pixbuf(iter, img_btm)
                
                if a and b and not c:
                    self.set_pixbuf(iter_pre, img_mid)
                    self.set_pixbuf(iter, img_btm)
                
                if a and b and c:
                    self.set_pixbuf(iter_pre, img_mid)
                    self.set_pixbuf(iter, img_mid)
                
                if not a and b and c:
                    self.set_pixbuf(iter_pre, img_top)
                    self.set_pixbuf(iter, img_mid)
                if model.iter_next(iter):    
                    int_path +=1
                else:
                    int_path = False
                
    def set_pixbuf(self, iter, img):
        model = self.treeview_bc.get_model()
        filepath = dir_img + img
        pix = gtk.gdk.pixbuf_new_from_file(filepath)
        model.set_value(iter, 10, pix)
    
    def set_bool(self, iter, bool):
        model = self.treeview_bc.get_model()
        model.set_value(iter, 9, bool)
    
    def join_drop(self, model, iter, position):
        if position:            
            path = model.get_path(iter)
            bool_join = model.get_value(iter, 9)
            int_path = path[0]
            int_path = int_path - 1
            path = (int_path, )
            iter = model.get_iter(path)
            self.set_bool(iter, bool_join)
       
        else:
            bool_join = model.get_value(iter, 9)
            path = model.get_path(iter)
            int_path = path[0]
            int_path = int_path + 1
            path = (int_path, )
            iter = model.get_iter(path)
            self.set_bool(iter, bool_join)

    def update_time_total(self):
        model = self.treeview_bc.get_model()
        iter = model.get_iter_first()
        if not iter:
            self.label_time_1.set_text("00:00  ")
            
        total_time = 0
        while iter:
            int_time = model.get_value(iter, 8)
            try:
                int_time = int(int_time)
                total_time = total_time + int_time
            except TypeError:
                print('could not determine time value')
            iter = model.iter_next(iter)
        str_time = self.convert_time(total_time)
        self.label_time_1.set_text(str_time + "  ")

    # Scheduler section
    def set_up_sch(self):
        sch_list = self.create_sch_list()
        self.make_sch_treelist(sch_list)
        self.list_programmes()

    def refresh_sch(self, widget):
        self.list_programmes()
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
        cur = conn.cursor()
        query = "SELECT schedule.time_date,  schedule.msg_code, messagelist.title, messagelist.nq, messagelist.type, messagelist.filename, messagelist.duration FROM schedule JOIN messagelist ON schedule.msg_code=messagelist.code WHERE time_date >= '{0} 06:00' AND time_date < '{1} 06:00' ORDER BY time_date".format (str_selected_date, next_morning)
        cur.execute(query)
        schedule_list = cur.fetchall()
        cur.close()
        conn.close()
        #[datetime, code, title, nq, type, filename, duration] 
        return schedule_list
    
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
    
    def list_programmes(self):
        #populate the drop down 'combo' list
        liststore = gtk.ListStore(str)        
        programme_list = self.query_programmes()
        for item in programme_list:        
            liststore.append([item[1]])
        self.cb_sch_prg.set_model(liststore)
        self.cb_sch_prg.set_active(0)

    def prepare_list(self, schedule_list, programme_list):
        #[time, Programme ID Code, Programme title, Message ID Code, Message Title, type, nq, filename, duration]
        time_list = [["06:00", "", "", "", "", "", "", "", ""],
             ["06:30", "", "", "", "", "", "", "", "", ""],
             ["07:00", "", "", "", "", "", "", "", ""],
             ["07:30", "", "", "", "", "", "", "", ""],
             ["08:00", "", "", "", "", "", "", "", ""],
             ["08:30", "", "", "", "", "", "", "", ""],
             ["09:00", "", "", "", "", "", "", "", ""],
             ["09:30", "", "", "", "", "", "", "", ""],
             ["10:00", "", "", "", "", "", "", "", ""],
             ["10:30", "", "", "", "", "", "", "", ""],
             ["11:00", "", "", "", "", "", "", "", ""],
             ["11:30", "", "", "", "", "", "", "", ""],
             ["12:00", "", "", "", "", "", "", "", ""],
             ["12:30", "", "", "", "", "", "", "", ""],
             ["13:00", "", "", "", "", "", "", "", ""],
             ["13:30", "", "", "", "", "", "", "", ""],
             ["14:00", "", "", "", "", "", "", "", ""],
             ["14:30", "", "", "", "", "", "", "", ""],
             ["15:00", "", "", "", "", "", "", "", ""],
             ["15:30", "", "", "", "", "", "", "", ""],
             ["16:00", "", "", "", "", "", "", "", ""],
             ["16:30", "", "", "", "", "", "", "", ""],
             ["17:00", "", "", "", "", "", "", "", ""],
             ["17:30", "", "", "", "", "", "", "", ""],
             ["18:00", "", "", "", "", "", "", "", ""],
             ["18:30", "", "", "", "", "", "", "", ""],
             ["19:00", "", "", "", "", "", "", "", ""],
             ["19:30", "", "", "", "", "", "", "", ""],
             ["20:00", "", "", "", "", "", "", "", ""],
             ["20:30", "", "", "", "", "", "", "", ""],
             ["21:00", "", "", "", "", "", "", "", ""],
             ["21:30", "", "", "", "", "", "", "", ""],
             ["22:00", "", "", "", "", "", "", "", ""],
             ["22:30", "", "", "", "", "", "", "", ""],
             ["23:00", "", "", "", "", "", "", "", ""],
             ["23:30", "", "", "", "", "", "", "", ""],
             ["00:00", "", "", "", "", "", "", "", ""],
             ["00:30", "", "", "", "", "", "", "", ""],
             ["01:00", "", "", "", "", "", "", "", ""],
             ["01:30", "", "", "", "", "", "", "", ""],
             ["02:00", "", "", "", "", "", "", "", ""],
             ["02:30", "", "", "", "", "", "", "", ""],
             ["03:00", "", "", "", "", "", "", "", ""],
             ["03:30", "", "", "", "", "", "", "", ""],
             ["04:00", "", "", "", "", "", "", "", ""],
             ["04:30", "", "", "", "", "", "", "", ""],
             ["05:00", "", "", "", "", "", "", "", ""],
             ["05:30", "", "", "", "", "", "", "", ""]]
        n = 0
        for item in time_list:
            n+=1
            #(check if there is an entry in item[0] - necessary?)
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
                msg_start = str(msg[0])[-8:-3]
                if msg_start==starttime:
                    if item[4] == "":
                        item[3] = msg[1]
                        item[4] = msg[2]
                        item[5] = msg[4]
                        item[6] = msg[3]
                        item[7] = msg[5]
                        item[8] = msg[6]
                        
                    else:
                        time_list.insert(n, ["", "", "", msg[1], msg[2], msg[4], msg[3], msg[5], msg[6]])
        return time_list
        
    def make_sch_treelist(self, sch_list):
        self.store_sch.clear()
        for item in sch_list:
            iter = self.store_sch.append()
            self.store_sch.set(iter,
                0, item[0],
                1, item[1],
                2, item[2],
                3, item[3],
                4, item[4],
                5, item[5],
                6, item[6],
                7, item[7],
                8, item[8],
                )
        treeselection = self.treeview_sch.get_selection()
        treeselection.select_path(0)

    def go_to_programme(self, widget):
        '''
        get the name of a programme from the drop down list
        search the programme column, one row at a time, for the programme
        programatically select the row with the programme in it
        '''
        treeselection = self.treeview_sch.get_selection()
        str_prg = widget.get_active_text()
        n = 0
        for row in self.store_sch:
            if str_prg==row[2]:
                treeselection.select_path(n)
                self.treeview_sch.scroll_to_cell(n, None, True, 0, 0)
            n+=1    

    def go_to_now(self, widget):
        '''
        identify current time
        round off to previous half hour as time string
        search the time column one row at a time for the time string
        programatically select the row with the time string        
        '''    
        self.refresh_sch(None)
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
        model, iter = treeselection_sch.get_selected()
        datatuple = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7, 8)
        
        if datatuple[4]:
            code = datatuple[3]
            filename = datatuple[7]
            message = datatuple[4]
            nq = datatuple[6]
            msg_type = datatuple[5]
            dur = datatuple[8]
            if dur:
                time = self.convert_time(dur)
            else:
                time = 'N/A'    
                
            path_img = dir_img + img_blank        
            px = gtk.gdk.pixbuf_new_from_file(path_img)          

            datalist = ["msg", code, filename, message, nq, msg_type, "None", time, dur, False, px]        
            #add details to the bottom of the broadcast list
            model = self.treeview_bc.get_model()
            model.append(datalist)
        else:
            str_error = "No scheduled message was selected" 
            self.error_dialog(str_error)

    # preview section  
    def get_pre_filepath(self):
        if self.list_pre[3] == "msg":
            dir_type = self.list_pre[1][0:12]
            filepath = "{0}/{1}/{2}".format (dir_msg, dir_type.lower(), self.list_pre[2])
            print(filepath)
        elif self.list_pre[3] == "mus":
            filepath = self.get_cat_filepath(self.list_pre[2])
        else: filepath = ""
        return filepath

    def play_pause_clicked(self, widget):
        filepath = self.get_pre_filepath()
        if not os.path.isfile(filepath):
            str_error = "Unable to play - the file does not exist"
            self.error_dialog(str_error)
        else:
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
        
    def msg_selection_changed(self, selection):
        playstatus = self.player_pre.get_state() 
        if (not playstatus == gst.STATE_PLAYING) and (not playstatus == gst.STATE_PAUSED):
            model, path = selection.get_selected_rows()
            if path:
                iter = model.get_iter(path[0])
                #title
                self.list_pre[0] = model.get_value(iter, 3)
                #type
                self.list_pre[1] = model.get_value(iter, 5)
                #filename
                self.list_pre[2] = model.get_value(iter, 2)
                #identify as msg
                self.list_pre[3] = "msg"
                self.label_pre_play.set_label(self.list_pre[0])
                if len(self.list_pre[0]) > 30:
                    self.label_pre_play.set_tooltip_text(self.list_pre[0]) 
                else:
                    self.label_pre_play.set_tooltip_text("")      

    def sch_selection_changed(self, selection):
        playstatus = self.player_pre.get_state() 
        if (not playstatus == gst.STATE_PLAYING) and (not playstatus == gst.STATE_PAUSED): 
            model, path = selection.get_selected_rows()
            if path:
                iter = model.get_iter(path[0])
                #title
                self.list_pre[0] = model.get_value(iter, 4)
                #type
                self.list_pre[1] = model.get_value(iter, 5)
                #filename
                self.list_pre[2] = model.get_value(iter, 7)
                #identify as msg
                self.list_pre[3] = "msg"
                self.label_pre_play.set_label(self.list_pre[0])
                if len(self.list_pre[0]) > 30:
                    self.label_pre_play.set_tooltip_text(self.list_pre[0]) 
                else:
                    self.label_pre_play.set_tooltip_text("")
            
    def on_seek_changed(self, widget, param):
        self.player_pre.set_updateable_progress(True)
        self.player_pre.set_place_in_file(self.hscale_pre.get_value())

    #common functions
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

    def get_filepath(self, track):   
        if track[0] == "msg":            
            dir_file = track[5][0:12]
            filepath = "{0}/{1}/{2}".format (dir_msg, dir_file.lower(), track[2])
        elif track[0] == "mus":
            filepath = self.get_cat_filepath(track[2])
        else: filepath = ""
        return filepath

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
