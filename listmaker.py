#!/usr/bin/python2
'''
listmaker
search for tracks and add them to a list which can be saved
as an xspf file
'''
import datetime
import pickle
import threading
import thread
import os
import time
import ConfigParser

import pygtk
import gtk
import gobject
import pango
import psycopg2
import psycopg2.extras
import gst
import pygst
from lxml import etree
from psycopg2 import sql

#get variables from config file
config = ConfigParser.SafeConfigParser()
config.read('/usr/local/etc/threedradio.conf')

dir_pl3d = config.get('Paths', 'dir_pl3d')
dir_mus = config.get('Paths', 'dir_mus')
dir_img = config.get('Paths', 'dir_img')
logo = config.get('Images', 'logo')

query_limit = config.getint('Listmaker', 'query_limit')

pg_user = config.get('Listmaker', 'pg_user')
pg_password = config.get('Listmaker', 'pg_password')
pg_server = config.get('Common', 'pg_server')
pg_cat_database = config.get('Common', 'pg_cat_database')

#other variables
sfx = ".p3d"
sfx_old = ".pl3d"

        
#lists and dictionaries 
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
            "Album Alphabetical": (("title", "ASC"), ("id", "DESC"))
}

class Preview_Player:
    '''
    adapted from Benny Malev's DamnSimplePlayer
    '''
    def __init__(self, time_label, hscale, reset_playbutton):
        self.player = gst.element_factory_make("playbin", "player")
        fakesink = gst.element_factory_make("fakesink", "fakesink")
        sink_pre = gst.element_factory_make("alsasink", "preview_sink")
        #sink_pre.set_property("device", "preview")
        self.player.set_property("video-sink", fakesink)
        self.player.set_property("audio-sink", sink_pre)
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

class List_Maker():
    
    def delete_event(self, widget, event, data=None):
        return False

    def destroy(self, widget, data=None):
        gtk.main_quit()

    def main(self):
        '''defines the layout of the graphical interface
           and the events connected to the widgets
        '''
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL) 
        self.window.set_position(gtk.WIN_POS_CENTER)
        filepath_logo = dir_img + logo
        self.window.set_icon_from_file(filepath_logo)
        #self.window.set_resizable(False)
        self.window.set_size_request(1100, 800)
        self.window.set_title("Listmaker")
        
        
        ###   create containers - boxes and scrolled windows  ###        
        #hpane to hold playlist and search panes
        #hpane = gtk.HPaned()
        # hbox for music catalogue
        hbox_cat = gtk.HBox(False, 5)
        # vbox for catalogue search
        vbox_cat_search = gtk.VBox(False, 5)
        # table for music catalogue search
        table_cat = gtk.Table(20, 2, False)

        # hbox for catalogue order selection
        hbox_cat_order = gtk.HBox(False, 5)
        
        # hbox for catalogue maximum result limit selection
        hbox_cat_max = gtk.HBox(False, 5)
        
        # vbox for catalogue list
        vbox_cat_lst = gtk.VBox(False, 0)
        # scrolled window for catalogue list treeview
        self.sw_cat_lst = gtk.ScrolledWindow()
        self.sw_cat_lst.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        self.sw_cat_lst.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC) 
        
        # hbox for preview player buttons
        hbox_pre_btn = gtk.HBox(False, 0)  
        hbox_pre_btn.set_size_request(280, 30)
        # vbox for playlist
        vbox_pl = gtk.VBox(False, 5)
        # hbox for list option buttons in the playlist
        hbox_pl = gtk.HBox(False, 0)        
        
        # scrolled holder for the playlist treelist
        sw_pl = gtk.ScrolledWindow()
        sw_pl.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_pl.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
 
        # hbox for Total Time 
        hbox_pl_time = gtk.HBox(False, 0)    
        hbox_pl_time.set_size_request(280, 30)


        ### Styles ###

        header_font = pango.FontDescription("Sans Bold 18")
        subheader_font = pango.FontDescription("Sans Bold 14")
        subheader_font_1 = pango.FontDescription("Sans Bold 12")
        subheader_font_2 = pango.FontDescription("Sans Bold 11")  


        ### ----------------Music Catalogue Search ---------------- ###
        
        label_search = gtk.Label(" Music Catalogue ")
        label_search.modify_font(header_font)        
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
        label_search = gtk.Label("Advanced Search")
        label_search.modify_font(subheader_font_1)
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
        label_search_cpa = gtk.Label("Source")
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
        self.cb_creator_add(self.dict_creator)        
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
          
        
        btn_search = gtk.Button("Search")
        self.label_search_result = gtk.Label()
        self.label_search_result.set_size_request(80, 40)

        ### ----------- Search Results Section -----------###

        label_results = gtk.Label("Search Results")
        label_results.modify_font(subheader_font_1)
        #label_results.set_size_request(80, 30)

        #make the list
        self.store_cat = gtk.TreeStore(str ,str ,str, str)
        self.treeview_cat = gtk.TreeView(self.store_cat)
        self.treeview_cat.set_rules_hint(True)
        treeselection_cat = self.treeview_cat.get_selection()
        self.add_cat_columns(self.treeview_cat)
        
        
        ### ------------ Preview Section ------------  ###
        
        ### images for buttons
        self.image_play = gtk.Image()
        self.image_play.set_from_stock(gtk.STOCK_MEDIA_PLAY, gtk.ICON_SIZE_BUTTON)
        self.image_play.set_name("play")
        self.image_pause = gtk.Image()
        self.image_pause.set_from_stock(gtk.STOCK_MEDIA_PAUSE, gtk.ICON_SIZE_BUTTON)
        self.image_pause.set_name("pause")
        image_stop = gtk.Image()
        image_stop.set_from_stock(gtk.STOCK_MEDIA_STOP, gtk.ICON_SIZE_BUTTON)
        # preview player buttons
        self.btn_pre_play_pause = gtk.Button()
        self.btn_pre_play_pause.set_image(self.image_play)
        btn_pre_stop = gtk.Button()
        btn_pre_stop.set_image(image_stop)
        btn_pre_stop.connect("clicked", self.on_stop_clicked)
        #Label of track to preview
        self.str_dur="00:00"
        self.label_pre_time = gtk.Label("00:00 / 00:00")        
        #both lambdas toggle progressbar to be not updatable by player_pre while valve is dragged
        self.progress_pressed = lambda widget, param: self.player_pre.set_updateable_progress(False)

        self.hscale_pre = gtk.HScale()
        self.hscale_pre.set_size_request(180, 20)
        self.hscale_pre.set_range(0, 100)
        self.hscale_pre.set_increments(1, 10)
        self.hscale_pre.set_digits(0)
        self.hscale_pre.set_draw_value(False)
        self.hscale_pre.set_update_policy(gtk.UPDATE_DISCONTINUOUS) 


        # the preview player
        self.player_pre = Preview_Player(
            self.label_pre_time, self.hscale_pre, self.reset_playbutton)

        ### ---------- Playlist Section ---------- ###
        
        self.changed = False
        label_pl = gtk.Label("Playlist")
        label_pl.modify_font(subheader_font_1)
        label_pl.set_size_request(80, 30)     
        
        btn_inf = gtk.Button("Info")
        btn_inf.set_tooltip_text("Information about the selected track")
        btn_rem = gtk.Button("Remove")
        btn_rem.set_tooltip_text("Remove the selected track from the playlist")
        btn_open = gtk.Button("_Open")
        btn_open.set_tooltip_text("Open a new playlist")
        btn_save = gtk.Button("_Save")
        btn_save.set_tooltip_text("Save this playlist")
        btn_saveas = gtk.Button("Save As")
        btn_saveas.set_tooltip_text("Save this playlist as a new file with a different name")
        
        
        self.store_pl = gtk.ListStore(str ,str ,str ,str)
        self.treeview_pl = gtk.TreeView(self.store_pl)
        self.treeview_pl.set_rules_hint(True)
        treeselection_pl = self.treeview_pl.get_selection()
        self.add_pl_columns(self.treeview_pl)        
        
        label_time_0 = gtk.Label("Playlist Total Time - ")
        self.label_time_1 = gtk.Label("00:00  ")

        ### dnd and connections ###
        self.treeview_cat.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                              [("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_pl.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                              [("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_pl.enable_model_drag_dest([("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_cat.connect("drag_data_get", self.cat_drag_data_get_data)
        self.treeview_pl.connect("drag_data_get", self.pl_drag_data_get_data)
        self.treeview_pl.connect("drag_data_received",
                              self.drag_data_received_data)
        self.sw_cat_lst.connect("size-allocate", self.resize_check)
        self.window.connect("delete_event", self.delete_event)
        self.window.connect("destroy", self.destroy)
        
        treeselection_cat.connect('changed', self.cat_selection_changed)
        #btn_cat_simple.connect("clicked", self.simple_search)
        #self.entry_search_simple.connect("activate", self.simple_search)
        self.entry_search_artist.connect("activate", self.search_catalogue)
        self.entry_search_album.connect("activate", self.search_catalogue)
        self.entry_search_track.connect("activate", self.search_catalogue)
        self.entry_search_cmpy.connect("activate", self.search_catalogue)
        self.entry_search_genre.connect("activate", self.search_catalogue)
        self.entry_search_com.connect("activate", self.search_catalogue)
        self.entry_search_cpa.connect("activate", self.search_catalogue)
        self.entry_search_year.connect("activate", self.search_catalogue)           
        btn_search.connect("clicked", self.search_catalogue)
        self.btn_pre_play_pause.connect("clicked", self.play_pause_clicked)
        btn_pre_stop.connect("clicked", self.on_stop_clicked)
        self.hscale_pre.connect("button-release-event", self.on_seek_changed)
        self.hscale_pre.connect("button-press-event", self.progress_pressed)
        btn_inf.connect("clicked", self.info_row)
        btn_rem.connect("clicked", self.remove_row)
        btn_open.connect("clicked", self.open_dialog)
        btn_save.connect("clicked", self.save)
        btn_saveas.connect("clicked", self.saveas)
        
        self.treeview_cat.connect('button-release-event' , self.right_click_list_menu)
        ### do the packing ###

        hbox_pre_btn.pack_start(self.btn_pre_play_pause, False)
        hbox_pre_btn.pack_start(btn_pre_stop, False)
        hbox_pre_btn.pack_start(self.hscale_pre, True)
        hbox_pre_btn.pack_start(self.label_pre_time, True)   

        table_cat.attach(label_search_artist, 0, 1, 0, 1, False, False, 5, 0)
        table_cat.attach(self.entry_search_artist, 1, 2, 0, 1, False, False, 5, 0)
        table_cat.attach(label_search_album, 0, 1, 1, 2, False, False, 5, 0)
        table_cat.attach(self.entry_search_album, 1, 2, 1, 2, False, False, 5, 0)
        table_cat.attach(label_search_track, 0, 1, 2, 3, False, False, 5, 0)
        table_cat.attach(self.entry_search_track, 1, 2, 2, 3, False, False, 5, 0)
        table_cat.attach(label_search_cmpy, 0, 1, 3, 4, False, False, 5, 0)
        table_cat.attach(self.entry_search_cmpy, 1, 2, 3, 4, False, False, 5, 0)
        table_cat.attach(label_search_com, 0, 1, 4, 5, False, False, 5, 0)
        table_cat.attach(self.entry_search_com, 1, 2, 4, 5, False, False, 5, 0)
        table_cat.attach(label_search_genre, 0, 1, 5, 6, False, False, 5, 0)
        table_cat.attach(self.entry_search_genre, 1, 2, 5, 6, False, False, 5, 0)
        table_cat.attach(label_search_cpa, 0, 1, 6, 7, False, False, 5, 0)
        table_cat.attach(self.entry_search_cpa, 1, 2, 6, 7, False, False, 5, 0)
        table_cat.attach(label_search_year, 0, 1, 7, 8,  False, False, 5, 0)
        table_cat.attach(self.entry_search_year, 1, 2, 7, 8,  False, False, 5, 0)        
        table_cat.attach(label_search_creator, 0, 1, 8, 9,  False, False, 5, 0)
        table_cat.attach(self.cb_search_creator, 1, 2, 8, 9,  False, False, 5, 0)        
        

        hbox_cat_order.pack_start(label_search_order, False)
        hbox_cat_order.pack_start(self.cb_search_order, False)
        hbox_cat_max.pack_start(label_search_max, False)
        hbox_cat_max.pack_start(self.spin_search_max, False)

        vbox_cat_search.pack_start(sep_cat_0, False)
        #vbox_cat_search.pack_start(label_search_simple, False)
        #vbox_cat_search.pack_start(self.entry_search_simple, False)
        #vbox_cat_search.pack_start(btn_cat_simple, False)
        #vbox_cat_search.pack_start(self.label_result_simple, False)
        #vbox_cat_search.pack_start(sep_cat_1, False)
        vbox_cat_search.pack_start(label_search, False)
        
        vbox_cat_search.pack_start(table_cat, False)
        vbox_cat_search.pack_start(self.chk_search_comp, False)
        vbox_cat_search.pack_start(self.chk_search_demo, False)
        vbox_cat_search.pack_start(self.chk_search_local, False)
        vbox_cat_search.pack_start(self.chk_search_fem, False)
        vbox_cat_search.pack_start(self.chk_search_nr, False)
        vbox_cat_search.pack_start(hbox_cat_order, False)
        vbox_cat_search.pack_start(hbox_cat_max, False)   
        vbox_cat_search.pack_start(btn_search, False)
        #vbox_cat_search.pack_start(self.entry_search_adv, False)  
        vbox_cat_search.pack_start(self.label_search_result, False)
        self.sw_cat_lst.add(self.treeview_cat)
        sw_pl.add(self.treeview_pl)   
        vbox_cat_lst.pack_start(label_results, False)
        vbox_cat_lst.pack_start(self.sw_cat_lst, True)
        vbox_cat_lst.pack_start(hbox_pre_btn, False)



        hbox_pl_time.pack_end(self.label_time_1, False)
        hbox_pl_time.pack_end(label_time_0, False)
                
        hbox_pl.pack_start(btn_inf, False)
        hbox_pl.pack_start(btn_rem, False)
        hbox_pl.pack_start(btn_open, False)
        hbox_pl.pack_start(btn_save, False)
        hbox_pl.pack_start(btn_saveas, False)
        
        vbox_pl.pack_start(label_pl, False)
        vbox_pl.pack_start(hbox_pl, False)
        vbox_pl.pack_start(sw_pl, True)
        vbox_pl.pack_start(hbox_pl_time, False)
        hbox_cat.pack_start(vbox_cat_search, False)  
        hbox_cat.pack_start(vbox_cat_lst, True) 
        hbox_cat.pack_start(vbox_pl, False)  
        #hpane.pack1(hbox_cat, False, False)
        #hpane.pack2(vbox_pl, False, False)
        #window.add(hpane)
        self.window.add(hbox_cat)
        self.window.show_all()
        
        gtk.gdk.threads_init()
        
        self.Saved = False
        self.name_of_open_file = None

        gtk.main()

    # columns for the lists
    def add_cat_columns(self, treeview):
        '''
        Columns for the list of search results. The first column is hidden 
        and contains all the information about the track/CD in that row
        '''        
        # variable to use with window/sw resize
        self.column_width = 240
        
        #Column ONE
        column = gtk.TreeViewColumn('Dict', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)
                
        #Column TWO
        column = gtk.TreeViewColumn('', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        #column.set_resizable(True)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width)
        #column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        treeview.append_column(column)
       
        #Column THREE
        column = gtk.TreeViewColumn('', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        #column.set_resizable(True)
        #column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(self.column_width)
        treeview.append_column(column)

        #Column FOUR
        column = gtk.TreeViewColumn('', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_fixed_width(60)
        treeview.append_column(column)
        
    def resize_check(self, widget, allocation):
        #allocation = self.sw_cat_lst.get_allocation()
        width = allocation.width
        required_width = (width - 66) / 2
        if required_width != self.column_width:
            for columnid in (1, 2):
                self.column_width = required_width
                column = self.treeview_cat.get_column(columnid)
                column.set_fixed_width(self.column_width)
                print self.column_width
        
    def add_pl_columns(self, treeview):
        '''
        Columns for the playlist of tracks. The first column is hidden 
        and contains all the information about the track in that row
        '''
        # Column ONE
        column = gtk.TreeViewColumn('Dict', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)

        # Column TWO
        column = gtk.TreeViewColumn('Title', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        column.set_max_width(360)
        treeview.append_column(column)
        
        # Column THREE
        column = gtk.TreeViewColumn('Artist', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_visible(False)
        column.set_clickable(False)
        treeview.append_column(column)
        
        # Column FOUR
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        treeview.append_column(column)
        
    # dnd    
    def cat_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        copy the details from the hidden column of the selected row
        for drag n drop from the search results list.
        '''
        treeselection = treeview.get_selection()
        model, iter = treeselection.get_selected()
        
        #if the tracktime column is ("", ) then the CD has been selected, 
        tracktime = model.get(iter, 3)
        if not tracktime[0]:
            pickle_data = ""
        else:
            pickle_data = model.get(iter, 0)
            pickle_data = pickle_data[0]
            
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, pickle_data)

    def pl_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        copy the details from the hidden column of the selected row
        for drag n drop within the playlist.
        '''                                                           
        treeselection = treeview.get_selection()
        model, iter = treeselection.get_selected()
        

        pickle_data = model.get(iter, 0)
        pickle_data = pickle_data[0]
            
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, pickle_data)
        model.remove(iter)
        
    def drag_data_received_data(self, treeview, context, x, y, selection,
                                info, etime):
        '''
        add or move a row in the playlist using details copied with drag n drop.
        '''
        model = treeview.get_model()
        pickle_data = selection.get_text()

        dict_data = pickle.loads(pickle_data)
        track_id = dict_data['trackid']
        if not track_id:
            str_error = "Looks like you just tried to add a CD rather than a track"
            self.error_dialog(str_error)
            return
            
        int_time = dict_data['tracklength']
        tracktime = self.convert_time(int_time)
        cd_code = str(format(dict_data['cdid'], '07d')) # 7 digit
        track_no = str(format(dict_data['tracknum'], '02d')) # 2 digit
        tracktitle = dict_data['tracktitle']
        trackartist = dict_data['trackartist']
        artist = dict_data['artist']
        if not trackartist:
            trackartist = artist
        
        tracktitle = trackartist + '\n' + tracktitle
        list_data = (pickle_data, tracktitle, trackartist, tracktime)

        ID = cd_code + "-" + track_no
        if ID and  int_time:
            filepath = self.get_filepath(ID)
            #remove the check for testing where there are no files
            print(filepath)
            if not filepath:
                str_error = "Unable to add to the list, file does not exist. That track has probably not yet been ripped into the music store"
                self.error_dialog(str_error) 
            
            else:
                drop_info = treeview.get_dest_row_at_pos(x, y)
                if drop_info:
                    path, position = drop_info
                    iter = model.get_iter(path)
                    if (position == gtk.TREE_VIEW_DROP_BEFORE
                        or position == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                        model.insert_before(iter, list_data)
                        #self.join_drop(model, iter, True)

                    else:
                        model.insert_after(iter, list_data)
                        #self.join_drop(model, iter, False)
                        
                else:
                    model.append(list_data)
                if context.action == gtk.gdk.ACTION_MOVE:
                    context.finish(True, True, etime)
                
                self.update_time_total()
                self.changed = True
                    
        else:
            str_error = "Error - Not enough data in the list. Please contact a station tech for assistance"
            self.error_dialog(str_error)

    
        return

    # music catalogue section       
    def pg_connect_cat(self):
        '''
        initiate a connection to the catalogue database
        '''
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
                pg_cat_database, pg_user, pg_server, pg_password)
        conn = psycopg2.connect(conn_string)
        return conn


           
    def search_catalogue(self, widget):
        '''
        run functions which query the database and display the results as a list
        '''
        result = self.query_catalogue()
        if result:
            int_res = len(result)
            self.update_result_label(int_res)
            self.length_check(result)
            self.add_to_cat_store(result)
            
        else:
            self.clear_cat_list()
            int_res = 0
            self.update_result_label(int_res)
    
    def query_catalogue(self):
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

            

        #query according to the text
        
        str_error_none = "I can't see what you are searching for"
        str_error_len = "Please enter more than one character in your search"
        
        if not (artist or album or track or company or comments or creator or genre or new_release or year or cpa):
            self.error_dialog(str_error_none)
            return False
        
        '''
        # comment this out for now.
            
        for item in (artist, album, track, company, comments, genre):
            if item:
                if len(item) < 2:
                    self.error_dialog(str_error_len)
                    return False
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
   
        conn = self.pg_connect_cat()
        
        # show the query for debugging
        #query_string = query.as_string(conn)
        #print(query_string)

        dict_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        dict_cur.execute(query, (search_terms))
        result = dict_cur.fetchall()
        
        dict_cur.close()
        conn.close()  
        

        # convert the results to a true dictionary - for testing purposes
        #row_dict = [{k:v for k, v in record.items()} for record in result]
        #print(row_dict)
        result = [{k:v for k, v in record.items()} for record in result]
        return result

    def add_percent(self, parameter):
        '''
        wrap the string with percentage signs for 'ILIKE' query, avoiding 
        conflict with the symbol for substitution when defining parameters
        '''
        l = ('%', parameter, '%')
        percented = ''.join(l)
        return percented

    def update_result_label(self, int_res):
        '''
        Show how many tracks were found in the search
        '''
        query_limit = self.spin_search_max.get_value_as_int()
        if int_res >= query_limit :
            int_res = str(query_limit) + "+"
        str_results = "Your search returned {0} results".format(int_res)
        self.label_search_result.set_text(str_results)

    def length_check(self, result):
        '''
        check if the number of results returned is equal to 
        the value set as the limit for returned results.
        Display a message if the number is equal
        '''
        query_limit = self.spin_search_max.get_value_as_int()

        if len(result) == query_limit:
            str_warn_0 = "Warning - your query returned "
            str_warn_1 = " or more results. Only displaying the first "
            str_warn_2 = ". Please modify your search and be more specific "
            str_warn_3 = "or increase the number for the Maximum Results."
            str_warn = str_warn_0 + str(query_limit) + str_warn_1 + str(query_limit) + str_warn_2
            self.warn_dialog(str_warn)
    
    def add_to_cat_store(self, result):
        '''
        take the results of the search and display as rows in a treeview list
        full search details for each item go into the hidden column 
        '''

        # remove extra results caused by multiple comments and concatenate comments
        
        dict_result = []
        first = True
        separator = '''
        -----------------------
        '''
        for item in result:
            if first:
                dict_result.append(item)
                first = False
            else:
                if item["trackid"] == dict_result[-1]["trackid"]:
                    dict_result[-1]["comment"] = dict_result[-1]["comment"] + separator + item["comment"]
                else:
                    dict_result.append(item)

        self.clear_cat_list()
        var_album = ""
            
        for item in dict_result:
            model = self.treeview_cat.get_model()

            pickle_list = pickle.dumps(item)
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
            artist_album = artist + '\n' + album
            
            # include quota details
            quota = "Local:    "
            local = item["local"]
            if not local:
                local = 0
            local = unys[local]
            quota += local
            quota += "\nFemale:  "
            female = item["female"]
            if not female:
                female = 0
            female = unys[female]
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


                n = model.append(None, [cd_pickle, artist_album, quota, ""])
                model.append(n, [pickle_list, trackartist, tracktitle, dur_time])
            else:
                model.append(n, [pickle_list, trackartist, tracktitle, dur_time])
            var_album = album
        
    def get_dict_creator(self):
        '''
        create a dictionary of music catalogue user IDs and names
        '''
        list_creator = self.get_creator()
        dict_creator = {}
        for creator in list_creator:
            num = int(creator[0])
            first = creator[1].lower()
            second = creator[2].lower()
            fullname = first + " " + second

            dict_creator[num] = fullname

        return(dict_creator)

    def get_creator(self):
        '''
        query the catalogue for all users        
        '''
        query = "SELECT DISTINCT cd.createwho, users.first, users.last FROM cd JOIN users ON cd.createwho = users.id ORDER BY users.first"
        conn = self.pg_connect_cat()
        cur = conn.cursor()
        #dict_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(query)
        list_creator = cur.fetchall()
        cur.close()
        conn.close()
        return list_creator

    def cb_creator_add(self, dict_creator):
        '''
        populate the drop down list of contributors
        '''
        liststore_creator = gtk.ListStore(str)        
        list_creator = sorted(dict_creator.values())
        

        for creator in list_creator:
            self.cb_search_creator.append_text(creator)
        self.cb_search_creator.prepend_text("")
        self.cb_search_creator.append_text("")


        '''
        an orphaned function?
        ...will delete after checking
                
    def get_order(self):
        
        model = self.cb_search_order.get_model()
        active = self.cb_search_order.get_active()
        if active < 0:
            return None
        return model[active][0]
        '''

    def cb_order_add(self):
        '''
        populate the drop down list for selecting the order to list 
        search results 
        '''
        list_order = order_results.keys()
        list_order.sort()
        for item in list_order:
            self.cb_search_order.append_text(item)
        self.cb_search_order.set_active(0)

    def clear_cat_list(self):
        '''
        clear the search results
        '''
        model = self.treeview_cat.get_model()
        model.clear()



    # preview section  
    def get_sel_filepath(self):
        '''
        get the filepath of the track selected in the search results. 
        Combine the cdid with the track number to get the name of the file
        then call the function to get the full path 
        '''
        treeselection = self.treeview_cat.get_selection()
        model, iter = treeselection.get_selected()
        pickle_list = model.get(iter, 0)
        pickle_list = pickle_list[0]
        data_list = pickle.loads(pickle_list)
        ID = data_list['cdid']
        tracknum = data_list['tracknum']
        ID = str(ID).zfill(7) + "-" + str(tracknum).zfill(2)
        filepath = self.get_filepath(ID)
        if not filepath:
            str_error = "Unable to play, file does not exist. That track has probably not yet been ripped into the music store"
            self.error_dialog(str_error)
            return
        else: 
            return filepath

    def play_pause_clicked(self, widget):
        '''
        play the track selected in the results
        '''
        filepath = self.get_sel_filepath()
        if filepath:
            img = self.btn_pre_play_pause.get_image()
            if img.get_name() == "play":          
                self.btn_pre_play_pause.set_image(self.image_pause)
                self.player_pre.start(filepath)
                
            else:
                self.player_pre.pause()
                self.btn_pre_play_pause.set_image(self.image_play)
                
    def on_stop_clicked(self, widget):
        '''
        stop playing the track
        '''
        self.player_pre.stop()
        self.btn_pre_play_pause.set_image(self.image_play)
        self.label_pre_time.set_text("00:00 / " + self.str_dur)
    
    def reset_playbutton(self):
        '''
        set the pause/play image
        '''
        self.btn_pre_play_pause.set_image(self.image_play)
        
    def cat_selection_changed(self, selection):
        '''
        stop playing the preview when another track is selected
        '''
        playstatus = self.player_pre.get_state() 
        if (playstatus == gst.STATE_PLAYING) or (playstatus == gst.STATE_PAUSED):
            self.on_stop_clicked(True)
            
    def on_seek_changed(self, widget, param):
        self.player_pre.set_updateable_progress(True)
        self.player_pre.set_place_in_file(self.hscale_pre.get_value())
    

    # playlist section
    def update_time_total(self):
        model = self.treeview_pl.get_model()
        iter = model.get_iter_first()
        total_time = 0
        while iter:
            pickle_data = model.get_value(iter, 0)
            dict_data = pickle.loads(pickle_data)
            int_time = dict_data['tracklength']
            int_time = int(int_time)
            total_time = total_time + int_time
            iter = model.iter_next(iter)
        str_time = self.convert_time(total_time)
        self.label_time_1.set_text(str_time + "  ")

    def get_filename(self, act, name):
        '''
        open a file chooser window to open or save a playlist file
    
        '''
        if act == "open_file":
            action = gtk.FILE_CHOOSER_ACTION_OPEN
            btn = gtk.STOCK_OPEN

        elif act == "save_file":
            action = gtk.FILE_CHOOSER_ACTION_SAVE
            btn = gtk.STOCK_SAVE

        dialog = gtk.FileChooserDialog(
            "Select a Playlist",
            None,
            action,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
            btn, gtk.RESPONSE_ACCEPT)
            )


        dialog.set_default_response(gtk.RESPONSE_ACCEPT)

        dialog.set_current_folder(dir_pl3d)
        dialog.set_do_overwrite_confirmation(True)
        if name:
            dialog.set_current_name(name)

        filter = gtk.FileFilter()
        filter.set_name("Playlist files")
        filter.add_pattern("*.pl3d")
        filter.add_pattern("*.p3d")
        dialog.add_filter(filter)
        
        response = dialog.run()
        
        if response == gtk.RESPONSE_ACCEPT:
            filename = dialog.get_filename()
            dialog.destroy()
            return filename
                
        elif response == gtk.RESPONSE_CANCEL:
            dialog.destroy()
            return None

    def info_row(self, widget):    
        self.show_details(widget, self.treeview_pl)


    def info_message(self, datatuple):
        title = datatuple[0]
        artist = datatuple[1]
        album = datatuple[2]
        company = datatuple[3] 
        
        title_txt = "Title: {0}".format (title)
        artist_txt = "Artist: {0}".format (artist)
        album_txt = "Album: {0}".format (album)
        company_txt = "Company: {0}".format (company)
        
        label_title = gtk.Label(title_txt)
        label_artist = gtk.Label(artist_txt)   
        label_album = gtk.Label(album_txt)
        label_company = gtk.Label(company_txt)
           
        dialog = gtk.Dialog("Information", None, 0, (gtk.STOCK_OK, gtk.RESPONSE_OK))
        dialog.set_default_size(350, 150)

        dialog.vbox.pack_start(label_artist, True, True, 0)
        dialog.vbox.pack_start(label_title, True, True, 0)
        dialog.vbox.pack_start(label_album, True, True, 0)
        dialog.vbox.pack_start(label_company, True, True, 0)
        
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def remove_row(self, widget):    
        treeselection = self.treeview_pl.get_selection()
        model, iter = treeselection.get_selected()
        if iter:
            model.remove(iter) 
            model = self.treeview_pl.get_model()
            self.changed = True
        else:
            print("Nothing selected")
        iter = model.get_iter_first()
        if iter:
            self.update_time_total()
        else:
            self.label_time_1.set_text("00:00  ")

    def get_tracklist(self):
        model = self.treeview_pl.get_model()
        iter = model.get_iter_first()
        ls_tracklist = []
        while iter:
            pickle_row = model.get(iter, 0)[0]
            dict_row = pickle.loads(pickle_row)
            ls_tracklist.append(dict_row)
            iter = model.iter_next(iter)

        return ls_tracklist
            
    def open_dialog(self, widget):
        '''
        simply open a playlist - or
        check if there is a changed playlist open and ask if you want to save 
        it before opening another
        '''
        action = "open_file"
        if self.changed:
            self.save_change()
        filename = self.get_filename(action, None)
        filesp, filesfx = os.path.splitext(filename)
        

        if not (filesfx == sfx or filesfx == sfx_old):
            filename = filename + sfx

        
        if filename:
            title = os.path.basename(filesp)
            self.window.set_title(title)
            self.changed = False
            
        if filesfx == ".p3d":
            self.open_pl(filename)
            
        elif filesfx == ".pl3d":

            self.open_pl_xml(filename)

    def save_change(self):
        dialog = gtk.Dialog("Save List?", None, 0, 
        (gtk.STOCK_OK, gtk.RESPONSE_OK, 
         gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        
        ask_save = '''
        Do you want to save the changes that you made to this list 
        before you open another one?
        
        Click 'OK' to save 
        Or click 'Cancel' to open a new list without saving this one
        '''
        
        label_save = gtk.Label(ask_save)
        dialog.vbox.pack_start(label_save, True, True, 0)
        dialog.show_all()
        
        
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self.save(None)
        dialog.destroy()

    def open_pl(self, filename):

        ls_data = pickle.load(open(filename, "rb"))


        model = self.treeview_pl.get_model()
        for dict_data in ls_data:

            int_time = dict_data['tracklength']
            tracktime = self.convert_time(int_time)
            tracktitle = dict_data['tracktitle']
            trackartist = dict_data['trackartist']
            if not trackartist:
                artist = dict_data['artist']
                trackartist = artist
                
            pickle_data = pickle.dumps(dict_data)
                
            model.append((pickle_data, tracktitle, trackartist, tracktime))
            
            self.update_time_total()
            self.name_of_open_file = filename
        
    def open_pl_xml(self, filename):
        '''
        open the deprecated playlist
        '''    
        if filename:
            ls_tracklist = self.pl3d2pylist(filename)
            model = self.treeview_pl.get_model()
            model.clear()
            for item in ls_tracklist:
                title = item[0]
                
                #identifier is the track ID within a URL
                #eg http://threedradio.com/1234
                identifier = item[1]
                if identifier:
                    track_id = os.path.split(identifier)[1]
                
                #location is the filepath. It contains the track number and CD ID 
                location = item[2]
                cdid, tracknum = location.split("-")

                cdid = int(cdid)
                tracknum = int(tracknum)
                album = item[3]
                creator = item[4]
                
                #the annotation element is used to hold the company name
                annotation = item[5]
                company = annotation
                
                #duration is in milliseconds
                duration = item[6]
                if duration:
                    int_dur = int(duration)/1000
                    str_dur = self.convert_time(int_dur)
                
                dict_row = {"tracktitle": title, 
                            "track_id": track_id, 
                            "cdid": cdid, 
                            "tracknum": tracknum, 
                            "album": album, 
                            "artist": "", 
                            "trackartist": creator, 
                            "company": company, 
                            "str_dur": str_dur, 
                            "tracklength": int_dur}
                            
                pickle_row = pickle.dumps(dict_row)
                
                row = (pickle_row, title, creator, str_dur)
                model.append(row)
            
            self.update_time_total()
            self.name_of_open_file = filename
                        
    def save(self, widget):
        '''
        save the file. First check that it is not a new file.
        '''
        if self.name_of_open_file:
            filename = self.name_of_open_file      
            ls_tracklist = self.get_tracklist()
            pickle.dump(ls_tracklist, open(filename, "wb"))

        else:
            action = "save_file"
            filename = self.get_filename(action, 'Untitled.p3d')
            filesp, filesfx = os.path.splitext(filename)

            if not filesfx == sfx:
                filename = filesp + sfx
                
            if filename: 
                ls_tracklist = self.get_tracklist()
                try: 
                    pickle.dump(ls_tracklist, open(filename, "wb"))
                    self.changed = False
                    self.name_of_open_file = filename
                    self.Saved = True
                    
                except IOError:
                    str_error = '''
                    It looks like you are trying to overwrite 
                    somebody else's playlist.

                    Not Allowed!'''
                    self.error_dialog(str_error)
                                   
    def saveas(self, widget):
        action = "save_file"
        name = "Untitled.p3d"
        filename = self.get_filename(action, name)
        filesp, filesfx = os.path.splitext(filename)
        
        if filename:
            if not (filesfx == sfx):
                filename = filesp + sfx
            
            title = os.path.basename(filesp)
            self.window.set_title(title)
            self.changed = False
            
            ls_tracklist = self.get_tracklist()
            pickle.dump(ls_tracklist, open(filename, "wb"))
            self.name_of_open_file = filename
                
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
                
            if track.find("%sidentifier" % ns) is not None:
                str_identifier = track.find("%sidentifier" % ns).text
            else:
                str_identifier = None
                
            if track.find("%slocation" % ns) is not None:
                str_location = track.find("%slocation" % ns).text
            else:
                str_location = None

            if track.find("%salbum" % ns) is not None:
                str_album = track.find("%salbum" % ns).text
            else:
                str_album = None     
                           
            if track.find("%screator" % ns) is not None:
                str_creator = track.find("%screator" % ns).text
            else:
                str_creator = None
                
            if track.find("%sannotation" % ns) is not None:
                str_annotation = track.find("%sannotation" % ns).text
            else:
                str_annotation = None

            if track.find("%sduration" % ns) is not None:
                str_duration = track.find("%sduration" % ns).text
            else:
                str_duration = None

            tp_track = (
                str_title, 
                str_identifier, 
                str_location, 
                str_album, 
                str_creator, 
                str_annotation, 
                str_duration
                )
                
            ls_tracklist.append(tp_track)
            
        return ls_tracklist


    #common functions
    def right_click_list_menu(self, treeview, event):
        if event.button == 3: # right click
            context_menu = gtk.Menu()
            details_item = gtk.MenuItem( "Details")
            details_item.connect( "activate", self.show_details, treeview)
            details_item.show()
            play_item = gtk.MenuItem("Play")
            play_item.connect( "activate", self.play_from_menu, treeview)
            play_item.show()
            context_menu.append(details_item)
            context_menu.append(play_item)
            context_menu.popup( None, None, None, event.button, event.get_time())
            
    def get_details(self, treeview):
        selection = treeview.get_selection()
        model, iter = selection.get_selected()
        pickle_data = model.get(iter, 0)[0]
        dict_data = pickle.loads(pickle_data)
        return dict_data
        
    def show_details(self, w, treeview):
        
        dialog = gtk.Dialog("Details", None, 0, (
            gtk.STOCK_OK, gtk.RESPONSE_OK))
        table_details = gtk.Table(20, 2, False)
        dialog.vbox.pack_start(table_details, True, True, 0)
        dict_details = self.get_details(treeview)
        
        n = 0
        
        if "trackartist" in dict_details:
            artist = dict_details["trackartist"]
            if not artist:
                artist = dict_details["artist"]
        else: 
            artist = dict_details["artist"]
            
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

        if "tracktitle" in dict_details:
            label_detail_track = gtk.Label()
            label_detail_track.set_text("Track: ")
            label_detail_track.set_alignment(0, 0.5)
            table_details.attach(label_detail_track, 0, 1, n, n + 1, False, False, 5, 0)
            
            label_track = gtk.Label()
            track = dict_details['tracktitle']
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
        album = dict_details['title']
        label_album.set_text(album)
        label_album.set_selectable(True)
        label_album.set_alignment(0, 0.5)
        table_details.attach(label_album, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_local = gtk.Label()
        label_detail_local.set_alignment(0, 0.5)
        label_detail_local.set_text("Local: ")
        table_details.attach(label_detail_local, 0, 1, n, n + 1, False, False, 5, 0)
                
        label_local = gtk.Label()
        label_local.set_alignment(0, 0.5)
        label_local.set_selectable(True)
        local = dict_details['local']
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
        female = dict_details['female']
        female = unys[female]
        label_female.set_text(female)
        table_details.attach(label_female, 1, 2, n, n + 1, False, False, 5, 0)
        
        n += 1
        
        if "tracklength" in dict_details:
            label_detail_tracklength = gtk.Label()
            label_detail_tracklength.set_text("Track Length: ")
            label_detail_tracklength.set_alignment(0, 0.5)
            table_details.attach(label_detail_tracklength, 0, 1, n, n + 1, False, False, 5, 0)
            
            label_tracklength = gtk.Label()
            tracklength = dict_details['tracklength']
            str_tracklength = self.convert_time(tracklength)
            label_tracklength.set_text(str_tracklength)
            label_tracklength.set_selectable(True)
            label_tracklength.set_alignment(0, 0.5)
            table_details.attach(label_tracklength, 1, 2, n, n + 1, False, False, 5, 0)
        
        n += 1

        label_detail_demo = gtk.Label()
        label_detail_demo.set_alignment(0, 0.5)
        label_detail_demo.set_text("Demo: ")
        table_details.attach(label_detail_demo, 0, 1, n, n + 1, False, False, 5, 0) 

        label_demo = gtk.Label()
        label_demo.set_alignment(0, 0.5)
        label_demo.set_selectable(True)
        demo = dict_details['demo']
        if not demo:
            demo = 0
        demo = unys[demo]
        label_demo.set_text(demo)
        table_details.attach(label_demo, 1, 2, n, n + 1, False, False, 5, 0)
        
        n += 1
        
        label_detail_compilation = gtk.Label()
        label_detail_compilation.set_alignment(0, 0.5)
        label_detail_compilation.set_text("Compilation: ")
        table_details.attach(label_detail_compilation, 0, 1, n, n + 1, False, False, 5, 0)      

        label_compilation = gtk.Label()
        label_compilation.set_alignment(0, 0.5)
        label_compilation.set_selectable(True)
        compilation = dict_details['compilation']
        compilation = unys[compilation]
        label_compilation.set_text(compilation)
        table_details.attach(label_compilation, 1, 2, n, n + 1, False, False, 5, 0)
        
        n += 1

        label_detail_company = gtk.Label()
        label_detail_company.set_alignment(0, 0.5)
        label_detail_company.set_text("Company: ")
        table_details.attach(label_detail_company, 0, 1, n, n + 1, False, False, 5, 0)      
        
        label_company = gtk.Label()
        label_company.set_alignment(0, 0.5)
        label_company.set_selectable(True)
        company = dict_details['company']
        if company:
            label_company.set_text(company)
            table_details.attach(label_company, 1, 2, n, n + 1, False, False, 5, 0)
        
        n += 1
        
        label_detail_year = gtk.Label()
        label_detail_year.set_alignment(0, 0.5)
        label_detail_year.set_text("Release Year: ") 
        table_details.attach(label_detail_year, 0, 1, n, n + 1, False, False, 5, 0)      

        label_year = gtk.Label()
        label_year.set_alignment(0, 0.5)
        label_year.set_selectable(True)
        year = dict_details['year']
        if year:
            year = str(year)
            label_year.set_text(year) 
            table_details.attach(label_year, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_cpa = gtk.Label()
        label_detail_cpa.set_alignment(0, 0.5)
        label_detail_cpa.set_text("Country: ")
        table_details.attach(label_detail_cpa, 0, 1, n, n + 1, False, False, 5, 0)      
       
        label_cpa = gtk.Label()
        label_cpa.set_alignment(0, 0.5)
        label_cpa.set_selectable(True)
        cpa = dict_details['cpa']
        if cpa:
            label_cpa.set_text(cpa)
            table_details.attach(label_cpa, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_genre = gtk.Label()
        label_detail_genre.set_alignment(0, 0.5)
        label_detail_genre.set_text("Genre: ")
        table_details.attach(label_detail_genre, 0, 1, n, n + 1, False, False, 5, 0)      
       
        
        label_genre = gtk.Label()
        label_genre.set_alignment(0, 0.5)
        label_genre.set_selectable(True)
        genre = dict_details['genre']
        if genre:
            label_genre.set_text(genre)
            table_details.attach(label_genre, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_createwho = gtk.Label()
        label_detail_createwho.set_alignment(0, 0.5)
        label_detail_createwho.set_text("Added By: ")
        table_details.attach(label_detail_createwho, 0, 1, n, n + 1, False, False, 5, 0)      
       
        
        label_createwho = gtk.Label()
        label_createwho.set_alignment(0, 0.5)
        label_createwho.set_selectable(True)
        createwho = dict_details['createwho']
        if createwho:
            createwho = self.dict_creator[createwho]
            label_createwho.set_text(createwho)
            table_details.attach(label_createwho, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1
       
        label_detail_createwhen = gtk.Label()
        label_detail_createwhen.set_alignment(0, 0.5)
        label_detail_createwhen.set_text("Date Added: ")
        table_details.attach(label_detail_createwhen, 0, 1, n, n + 1, False, False, 5, 0)      
         
        label_createwhen = gtk.Label()
        label_createwhen.set_alignment(0, 0.5)
        label_createwhen.set_selectable(True)
        createwhen = dict_details['createwhen']
        if createwhen:
            createwhen = datetime.datetime.fromtimestamp(createwhen)
            createwhen = createwhen.strftime("%d/%m/%Y")
            label_createwhen.set_text(createwhen)
            table_details.attach(label_createwhen, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1
                
        label_detail_id = gtk.Label()
        label_detail_id.set_text("CD ID Number: ")
        label_detail_id.set_alignment(0, 0.5)
        table_details.attach(label_detail_id, 0, 1, n, n + 1, False, False, 5, 0)
        
        label_id = gtk.Label()
        cdid = dict_details["cdid"]
        cdid = str(cdid)
        label_id.set_text(cdid)
        label_id.set_selectable(True)
        label_id.set_alignment(0, 0.5)
        table_details.attach(label_id, 1, 2, n, n + 1, False, False, 5, 0)

        n += 1

        label_detail_comment = gtk.Label()
        label_detail_comment.set_text("Comments: ")
        label_detail_comment.set_alignment(0, 0.5)
        table_details.attach(label_detail_comment, 0, 1, n, n + 1, False, False, 5, 0)

        label_comment = gtk.Label()
        label_comment.set_alignment(0, 0.5)
        label_comment.set_selectable(True)
        label_comment.set_line_wrap(True)        
        
        cdcomment = dict_details['comment']
        if cdcomment:
            label_comment.set_text(cdcomment)
            table_details.attach(label_comment, 1, 2, n, n + 1, False, False, 5, 0)

        dialog.show_all()
        dialog.run()    
        dialog.destroy()        

    def play_from_menu(self, widget, treeview):
        selection = treeview.get_selection()
        model, iter = selection.get_selected()
        dict_data = self.get_details(model, iter)        
        cdid = (dict_data["cdid"])
        cdid = str(cdid).zfill(7)
        tracknum = (dict_data["tracknum"])
        tracknum = str(tracknum).zfill(2)
        
        ID = cdid + "-" + tracknum
        # print(ID)
        filepath = self.get_filepath(ID)
        # print(filepath)
        if filepath:
            img = self.btn_pre_play_pause.get_image()
            if img.get_name() != "play":
                self.player_pre.stop()
                          
            self.btn_pre_play_pause.set_image(self.image_pause)
            self.player_pre.start(filepath)

        
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

    def get_filepath(self, ID):
        filename = ID + ".mp3"
        dir_cd = ID[0:-3] + "/"
        filepath = dir_mus + dir_cd + filename
        if not os.path.isfile(filepath):
            return False
        else:
            return filepath

    # message dialogs
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

    
lm = List_Maker()
lm.main()
        
'''
Feature request
Tooltip over list to show artist name

'''
