#!/usr/bin/python3
'''
listmaker
search for tracks and add them to a list which can be saved
for loading into the studio player
'''
import datetime
import pickle
import os
import time
import base64
import threading
import configparser

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk
from gi.repository import Gst
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Pango

import psycopg2
import psycopg2.extras
from psycopg2 import sql
import json
from lxml import etree
import pydub

import player
from player import Player


#get variables from config file
config = configparser.ConfigParser()
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
    "cdcomment.comment",
    "cdcomment.createwho"
    )

order_results = {
            "Newest Albums First": (("year", "DESC"), ("id", "DESC")),
            "Oldest Albums First": (("year", "ASC"), ("id", "ASC")),
            "Artist Alphabetical": (("artist", "ASC"), ("id", "DESC")),
            "Album Alphabetical": (("title", "ASC"), ("id", "DESC")),
            "Most Recently Added": (("createwhen", "DESC"), ("id", "DESC"))
}

class SpinnerDialog(Gtk.Dialog):
    '''
    show spinner and run export
    '''
    def __init__(self, parent, filelist, export_file):
        Gtk.Dialog.__init__(self, "My Dialog", parent, 0, None)
        box = self.get_content_area()
        spinner = Gtk.Spinner()
        spinner.start()
        box.add(spinner)
        label = Gtk.Label(label="Exporting playlist, please wait")
        box.add(label)
        
        # Connect to the 'delete-event' signal
        self.connect('delete-event', Gtk.main_quit)

        # Run the time-consuming task in a separate thread

        self.task_thread = threading.Thread(target=self.combine_export, args=[filelist, export_file])
        self.task_thread.start()

        # Set the dialog to be modal
        self.set_modal(True)

        # Show the dialog
        self.show_all()
        
    def combine_export(self, filelist, export_file):
        '''
        subfunction run in thread to create combined export
        '''
        print("exporting") 
        combined = pydub.AudioSegment.empty()
        
        for song in filelist:
            audiosegment = pydub.AudioSegment.from_file(song, format="mp3")
            combined = combined + audiosegment
        combined.export(export_file, format="mp3")
        print("export completed")
        GLib.idle_add(self.destroy)


    def run_task(self):
        # Simulate a time-consuming task
        print(self.parameter1)
        time.sleep(10)
        print(self.parameter2)
        # Schedule the dialog to be closed
        GLib.idle_add(self.destroy)

class List_Maker():
    
    def delete_event(self, widget, event, data=None):
        '''
        Check for confirmation or need to save before application quits.
        '''
        if self.changed:
            response = self.save_change()
            if response == Gtk.ResponseType.ACCEPT:
                self.save(None)
                self.window.destroy()
                return False
            elif response == Gtk.ResponseType.REJECT:
                self.window.destroy()
                return False
            elif response == Gtk.ResponseType.CANCEL:
                return True
            
        else:
            response = self.confirm_close()
        
        return response
        
    def destroy(self, widget, data=None):
        Gtk.main_quit()

    def main(self):
        '''defines the layout of the graphical interface
           and the events connected to the widgets
        '''
        super().__init__()
        self.window = Gtk.Window() 
        self.window.set_position(Gtk.WindowPosition.CENTER)
        filepath_logo = dir_img + logo
        self.window.set_icon_from_file(filepath_logo)
        self.window.set_title("Listmaker")
        
        
        ###   create containers - boxes and scrolled windows  ###        
        # hbox for music catalogue
        hbox_cat = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        hbox_cat.set_margin_top(5)
        
        # vbox for catalogue search
        vbox_cat_search = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_cat_search.set_margin_left(5)
        # table for music catalogue search
        grid_cat = Gtk.Grid(hexpand=False, vexpand=False)
        grid_cat.set_valign(Gtk.Align.FILL)
        grid_cat.set_margin_top(margin=5)                                                                            
        grid_cat.set_margin_end(margin=5)                                                                            
        grid_cat.set_margin_bottom(margin=5)                                                                         
        grid_cat.set_margin_start(margin=5)                                                                          
        grid_cat.set_row_spacing(spacing=5)                                                                          
        grid_cat.set_column_spacing(spacing=5)
        grid_cat.set_row_homogeneous(False)
        grid_cat.set_column_homogeneous(False)
        
        # vbox for catalogue list
        vbox_cat_lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_cat_lst.set_halign(Gtk.Align.FILL)
        vbox_cat_lst.set_valign(Gtk.Align.FILL)
        # scrolled window for catalogue list treeview
        self.sw_cat_lst = Gtk.ScrolledWindow()
        self.sw_cat_lst.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        self.sw_cat_lst.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC) 
        self.sw_cat_lst.set_propagate_natural_width(True)
        
        # hbox for preview player buttons
        hbox_pre_btn = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        # vbox for playlist
        vbox_pl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_pl.set_margin_right(5)
        # hbox for list option buttons in the playlist
        hbox_pl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        
        # scrolled holder for the playlist treelist
        sw_pl = Gtk.ScrolledWindow()
        sw_pl.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        sw_pl.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
 
        # hbox for Total Time 
        hbox_pl_time = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        ### ----------------Music Catalogue Search ---------------- ###
        
        label_search = Gtk.Label(label="")
        label_search.set_markup("<span font='Sans Bold 14'> Search </span>")
        label_search.set_halign(Gtk.Align.START)
        label_search_artist = Gtk.Label(label="Artist")
        label_search_artist.set_halign(Gtk.Align.END)
        self.entry_search_artist = Gtk.Entry()
        label_search_album = Gtk.Label(label="Album")
        label_search_album.set_halign(Gtk.Align.END)
        self.entry_search_album = Gtk.Entry()
        label_search_track = Gtk.Label(label="Track")
        label_search_track.set_halign(Gtk.Align.END)
        self.entry_search_track = Gtk.Entry()
        label_search_cmpy = Gtk.Label(label="Company")
        label_search_cmpy.set_halign(Gtk.Align.END)
        self.entry_search_cmpy = Gtk.Entry()
        label_search_genre = Gtk.Label(label="Genre")
        label_search_genre.set_halign(Gtk.Align.END)
        self.entry_search_genre = Gtk.Entry()        
        label_search_com = Gtk.Label(label="Comments")
        label_search_com.set_halign(Gtk.Align.END)
        self.entry_search_com = Gtk.Entry()
        label_search_cpa = Gtk.Label(label="Country")
        label_search_cpa.set_halign(Gtk.Align.END)
        self.entry_search_cpa = Gtk.Entry()
        label_search_year = Gtk.Label(label="Release year")
        label_search_year.set_halign(Gtk.Align.END)
        self.entry_search_year = Gtk.Entry()
        self.entry_search_year.set_max_length(4)
        label_search_creator = Gtk.Label(label="Added by")
        label_search_creator.set_halign(Gtk.Align.END)
        self.cb_search_creator = Gtk.ComboBoxText()
        self.cb_search_creator = Gtk.ComboBoxText()
        self.cb_search_creator.set_name('mycombo')
        self.dict_creator = self.get_dict_creator()
        self.cb_creator_add(self.dict_creator)        
        self.chk_search_comp = Gtk.CheckButton.new_with_label("Compilation")
        self.chk_search_comp.set_active(False)
        self.chk_search_aus = Gtk.CheckButton.new_with_label("Australian")
        self.chk_search_aus.set_active(False)        
        self.chk_search_demo = Gtk.CheckButton.new_with_label("Demo")
        self.chk_search_demo.set_active(False)
        self.chk_search_local = Gtk.CheckButton.new_with_label("Local")
        self.chk_search_local.set_active(False)       
        self.chk_search_fem = Gtk.CheckButton.new_with_label("Female")
        self.chk_search_fem.set_active(False)
        self.chk_search_nr = Gtk.CheckButton.new_with_label("New Entries")
        self.chk_search_nr.set_active(False)
        
        label_search_order = Gtk.Label(label="Order by")
        label_search_order.set_halign(Gtk.Align.END)
        self.cb_search_order = Gtk.ComboBoxText()
        self.cb_order_add()

        label_search_max = Gtk.Label(label="Maximum Results")
        label_search_max.set_halign(Gtk.Align.END)
        query_limit = config.getint('Listmaker', 'query_limit')
        adjustment_max = Gtk.Adjustment(
            value=query_limit, 
            lower=1, 
            upper=10000, 
            step_increment=50, 
            page_increment=500, 
            page_size=50)
        self.spin_search_max = Gtk.SpinButton()
        self.spin_search_max.set_adjustment(adjustment_max)
        self.spin_search_max.set_value(query_limit)
       
        btn_search = Gtk.Button(label="Search")
        btn_search.set_halign(Gtk.Align.START)
        self.label_search_result = Gtk.Label()

        ### ----------- Search Results Section -----------###

        label_results = Gtk.Label()
        label_results.set_halign(Gtk.Align.START)
        label_results.set_markup("<span font='Sans Bold 14'> Results </span>")
        
        #make the list
        self.store_cat = Gtk.TreeStore(str ,str ,str, str, str)
        self.treeview_cat = Gtk.TreeView(model = self.store_cat)
        self.treeview_cat.set_name("cat")
        self.treeview_cat.set_halign(Gtk.Align.FILL)
        treeselection_cat = self.treeview_cat.get_selection()
        self.add_cat_columns(self.treeview_cat)
        self.dict_results = {}
        
        # button to expand or collapse all in treeview
        button_expand = Gtk.Button(
            label="Expand All",
            halign=Gtk.Align.START
            )
        button_expand.connect("clicked", self.expand_collapse)
        
        ### ------------ Preview Section ------------  ###

        self.btn_pre_play_pause = Gtk.Button()
        self.image_play = Gtk.Image.new_from_icon_name("media-playback-start", Gtk.IconSize.BUTTON)
        self.image_pause = Gtk.Image.new_from_icon_name("media-playback-pause", Gtk.IconSize.BUTTON)
        self.btn_pre_play_pause.set_image(self.image_play)
        btn_pre_stop = Gtk.Button()
        image_stop = Gtk.Image.new_from_icon_name("media-playback-stop", Gtk.IconSize.BUTTON)
        
        btn_pre_stop.set_image(image_stop)
        btn_pre_stop.connect("clicked", self.on_stop_clicked)
        #Label of track to preview
        self.str_dur="00:00"
        self.label_pre_time = Gtk.Label(label="00:00 / 00:00")        

        self.hscale_pre = Gtk.HScale(
            halign=Gtk.Align.FILL,
            hexpand=True)
        self.hscale_pre.set_range(0, 100)
        self.hscale_pre.set_increments(1, 10)
        self.hscale_pre.set_digits(0)
        self.hscale_pre.set_draw_value(False)

        # the preview player
        soundcard = "default"
        self.player = Player(
            self.label_pre_time, self.hscale_pre, soundcard)


        ### ---------- Playlist Section ---------- ###
        
        self.changed = False
        self.dict_pl = {}
        label_pl = Gtk.Label()
        label_pl.set_markup("<span font='Sans Bold 14'> Playlist </span>")
        label_pl.set_valign(Gtk.Align.START)
        label_pl.set_halign(Gtk.Align.START)     
        
        # Create a menu and items
        menu = Gtk.Menu()
        item_detail = Gtk.MenuItem(label="Details")
        item_remove = Gtk.MenuItem(label="Remove")
        item_new = Gtk.MenuItem(label="New")
        item_open = Gtk.MenuItem(label="Open")
        item_save = Gtk.MenuItem(label="Save")
        item_saveas = Gtk.MenuItem(label="Save as")
        item_export = Gtk.MenuItem(label="Export")
        item_quit = Gtk.MenuItem(label="Quit")

        # Add items to the menu
        menu.append(item_detail)
        menu.append(item_remove)
        menu.append(item_new)
        menu.append(item_open)
        menu.append(item_save)
        menu.append(item_saveas)
        menu.append(item_export)
        menu.append(item_quit)

        # Show the menu items
        menu.show_all()

        # Create a MenuButton with icon
        menu_button = Gtk.MenuButton()
        menu_button.set_popup(menu)
        menu_image = Gtk.Image.new_from_icon_name(
            "open-menu-symbolic", 
            Gtk.IconSize.BUTTON
            )
        menu_button.add(menu_image)
        
        # create treeview with store model        
        self.store_pl = Gtk.ListStore(str, str, str)
        self.treeview_pl = Gtk.TreeView(model=self.store_pl)
        self.treeview_pl.set_name("pl")
        treeselection_pl = self.treeview_pl.get_selection()
        self.add_pl_columns(self.treeview_pl)        
        
        # total track time
        label_time_0 = Gtk.Label(label="Playlist Total Time - ")
        self.label_time_1 = Gtk.Label(label="00:00  ")

        ### dnd and connections ###
        self.treeview_cat.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK, 
            [("text/plain", 0, 0)], 
            Gdk.DragAction.COPY
            )
        self.treeview_pl.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK, 
            [("text/plain", 0, 0)], 
            Gdk.DragAction.MOVE
            )
        self.treeview_pl.enable_model_drag_dest(
            [("text/plain", 0, 0)], 
            Gdk.DragAction.MOVE | Gdk.DragAction.COPY
            )                                  
        self.treeview_cat.connect("drag_data_get", self.cat_drag_data_get_data)
        self.treeview_pl.connect("drag_data_get", self.pl_drag_data_get_data)
        self.treeview_pl.connect("drag_data_received",
                              self.drag_data_received_data)
        
        self.window.connect("delete_event", self.delete_event)
        self.window.connect("destroy", self.destroy)

        treeselection_cat.connect('changed', self.cat_selection_changed)
        self.entry_search_artist.connect("activate", self.search_catalogue)
        self.entry_search_album.connect("activate", self.search_catalogue)
        self.entry_search_track.connect("activate", self.search_catalogue)
        self.entry_search_cmpy.connect("activate", self.search_catalogue)
        self.entry_search_genre.connect("activate", self.search_catalogue)
        self.entry_search_com.connect("activate", self.search_catalogue)
        self.entry_search_cpa.connect("activate", self.search_catalogue)
        self.entry_search_year.connect("activate", self.search_catalogue)
        self.cb_search_order.connect("changed", self.search_catalogue)           
        btn_search.connect("clicked", self.search_catalogue)
        self.btn_pre_play_pause.connect("clicked", self.play_pause_clicked)
        btn_pre_stop.connect("clicked", self.on_stop_clicked)
        
        item_detail.connect("activate", self.info_row)
        item_remove.connect("activate", self.remove_row)
        item_new.connect("activate", self.new)
        item_open.connect("activate", self.open_dialog)
        item_save.connect("activate", self.save)
        item_saveas.connect("activate", self.saveas)
        item_export.connect("activate", self.export)
        item_quit.connect("activate", self.delete_event, None)
        
        self.treeview_cat.connect('button-release-event' , self.right_click_cat_list_menu)
        self.treeview_pl.connect('button-release-event' , self.right_click_pl_list_menu)
        
        ### do the packing ###

        hbox_pre_btn.pack_start(button_expand, False, False, 5)
        hbox_pre_btn.pack_start(self.btn_pre_play_pause, False, False, 0)
        hbox_pre_btn.pack_start(btn_pre_stop, False, False, 0)
        hbox_pre_btn.pack_start(self.hscale_pre, True, True, 0)
        hbox_pre_btn.pack_start(self.label_pre_time, False, False, 0)   

        grid_cat.attach(
            child=label_search_artist, 
            left=0, 
            top=0, 
            width=1, 
            height=1)
        grid_cat.attach(
            child=self.entry_search_artist, 
            left=1, 
            top=0, 
            width=2, 
            height=1)
        grid_cat.attach(
            child=label_search_track, 
            left=0, 
            top=1, 
            width=1, 
            height=1
            )
        grid_cat.attach(
            child=self.entry_search_track, 
            left=1, 
            top=1, 
            width=2, 
            height=1
            )
        grid_cat.attach(
            child=label_search_album, 
            left=0, 
            top=2,
            width=1, 
            height=1
            )
        grid_cat.attach(
            child=self.entry_search_album, 
            left=1, 
            top=2, 
            width=2, 
            height=1
            )
        grid_cat.attach(
            child=label_search_cmpy, 
            left=0, 
            top=3, 
            width=1, 
            height=1
            )
        grid_cat.attach(
            child=self.entry_search_cmpy, 
            left=1, 
            top=3,
            width=2, 
            height=1
            )
        grid_cat.attach(
            child=label_search_com, 
            left=0, 
            top=4,
            width=1, 
            height=1
            )
        grid_cat.attach(
            child=self.entry_search_com, 
            left=1,
            top=4, 
            width=2, 
            height=1
            )
        grid_cat.attach(
            child=label_search_genre, 
            left=0, 
            top=5, 
            width=1, 
            height=1
            )
        grid_cat.attach(
            child=self.entry_search_genre, 
            left=1,
            top=5, 
            width=2, 
            height=1
            )
        grid_cat.attach(
            child=label_search_cpa, 
            left=0,
            top=6,
            width=1, 
            height=1
            )
        grid_cat.attach(
            child=self.entry_search_cpa, 
            left=1, 
            top=6, 
            width=2, 
            height=1
            )
        grid_cat.attach(
            child=label_search_year, 
            left=0, 
            top=7, 
            width=1, 
            height=1
            )
        grid_cat.attach(
            child=self.entry_search_year, 
            left=1, 
            top=7, 
            width=2, 
            height=1
            )
        grid_cat.attach(
            child=label_search_creator, 
            left=0,
            top=8, 
            width=1, 
            height=1
            )
        grid_cat.attach(
            child=self.cb_search_creator, 
            left=1, 
            top=8, 
            width=2, 
            height=1
            )
 
        grid_cat.attach(
            child=self.chk_search_local,
            left=0,
            top=9,
            width=1,
            height=1
            )
        #grid_cat.attach(
        #    child=self.chk_search_aus,
        #    left=1,
        #    top=9,
        #    width=2,
        #    height=1
        #    )
        grid_cat.attach(
            child=self.chk_search_fem,
            left=0,
            top=10,
            width=1,
            height=1
            )
        grid_cat.attach(
            child=self.chk_search_nr,
            left=1,
            top=9,
            width=2,
            height=1
            )
        grid_cat.attach(
            child=self.chk_search_demo	,
            left=0,
            top=11,
            width=1,
            height=1
            )
        grid_cat.attach(
            child=self.chk_search_comp	,
            left=1,
            top=10,
            width=2,
            height=1
            )
        grid_cat.attach(
            child=label_search_order,
            left=0,
            top=12,
            width=1,
            height=1
        )
        grid_cat.attach(
            child=self.cb_search_order,
            left=1,
            top=12,
            width=2,
            height=1
            )
        grid_cat.attach(
            child=label_search_max,
            left=0,
            top=13,
            width=2,
            height=1
            )
        grid_cat.attach(
            child=self.spin_search_max,
            left=2,
            top=13,
            width=1,
            height=1
            )
        
        vbox_cat_search.pack_start(label_search, False, False, 0)
        
        vbox_cat_search.pack_start(grid_cat, False, False, 0)
        vbox_cat_search.pack_start(btn_search, False, False, 0)
        vbox_cat_search.pack_start(self.label_search_result, False, False, 0)
        self.sw_cat_lst.add(self.treeview_cat)
        sw_pl.add(self.treeview_pl)   
        vbox_cat_lst.pack_start(label_results, False, False, 0)
        vbox_cat_lst.pack_start(self.sw_cat_lst, True, True, 0)
        vbox_cat_lst.pack_start(hbox_pre_btn, False, False, 0)

        hbox_pl_time.pack_end(self.label_time_1, False, False, 0)
        hbox_pl_time.pack_end(label_time_0, False, False, 0)
        hbox_pl.pack_start(label_pl, False, False, 0)
        hbox_pl.pack_end(menu_button, False, False, 5)
        vbox_pl.pack_start(hbox_pl, False, False, 0)
        vbox_pl.pack_start(sw_pl, True, True, 0)
        vbox_pl.pack_start(hbox_pl_time, False, False, 0)
        
        
        
        hbox_cat.pack_start(vbox_cat_search, False, False, 0)  
        hbox_cat.pack_start(vbox_cat_lst, True, True, 0) 
        hbox_cat.pack_start(vbox_pl, False, False, 0)  


        self.window.add(hbox_cat)
        self.window.show_all()
        
        self.Saved = False
        self.name_of_open_file = None

        Gtk.main()

    # columns for the lists
    def add_cat_columns(self, treeview):
        '''
        Columns for the list of search results. The first column is hidden 
        and contains all the information about the track/CD in that row
        '''        
        
        #Column ONE
        column = Gtk.TreeViewColumn('ID', Gtk.CellRendererText(), 
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)
                
        #Column TWO
        column = Gtk.TreeViewColumn('Artist', Gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        column.set_expand(True)
        column.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
        column.set_fixed_width(120)        
        treeview.append_column(column)
       
        #Column THREE
        column = Gtk.TreeViewColumn('Album/Title', Gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        column.set_expand(True)
        column.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
        column.set_fixed_width(120)
        treeview.append_column(column)

        #Column FOUR
        column = Gtk.TreeViewColumn('Quota', Gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        column.set_expand(False)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(66)
        treeview.append_column(column)
        
        #Column FIVE
        column = Gtk.TreeViewColumn('Length', Gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_expand(False)
        column.set_clickable(False)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_fixed_width(68)
        treeview.append_column(column)        
                        
    def add_pl_columns(self, treeview):
        '''
        Columns for the playlist of tracks. The first column is hidden 
        and contains all the information about the track in that row
        '''
        # Column ONE
        column = Gtk.TreeViewColumn('ID', Gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_visible(False)
        treeview.append_column(column)

        # Column TWO
        column = Gtk.TreeViewColumn('Title/Artist', Gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        column.set_max_width(360)
        column.set_fixed_width(180)
        column.set_expand(True)
        column.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
        treeview.append_column(column)
        
        # Column THREE
        column = Gtk.TreeViewColumn('Time', Gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        treeview.append_column(column)
        
    # dnd    
    def cat_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        copy the track id from the hidden first column of the selected 
        row for drag n drop from the search results list. If the
        track length, it is a CD and set the track_id to "0"
        '''
        treeselection = treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        track_id = model.get_value(tree_iter, 0)      
        title = model.get_value(tree_iter, 2) 
        artist = model.get_value(tree_iter, 1) 
        duration = model.get_value(tree_iter, 4)
        title_artist = title + '\n' + artist
        drag_data = (track_id, title_artist, duration)
        text = str(drag_data)
                    
        selection.set_text(text, -1)

    def pl_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        '''
        copy the track id from the hidden first column of the selected 
        row for drag n drop within the playlist.
        '''                                                           
        treeselection = treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        track_id = model.get_value(tree_iter, 0)
        title_artist = model.get_value(tree_iter, 1)
        duration = model.get_value(tree_iter, 2)
        items = (track_id, title_artist, duration)
        text = str(items)
        selection.set_text(text, -1)
        #model.remove(tree_iter)
    
    def drag_data_received_data(self, treeview, context, x, y, selection,
                                info, etime):
        '''
        add or move a row in the playlist using details copied with drag n drop.
        '''
        actions = context.get_actions()
        model = treeview.get_model()
        str_drag_data = selection.get_text()
        track_id, title_artist, duration = eval(str_drag_data)
        if "copy" in actions.value_nicks:
            dict_track = self.dict_results[track_id]
            cdid = str(format(dict_track['cdid'], '07d'))
            tracknum = str(format(dict_track['tracknum'], '02d'))
            filename = cdid + "-" + tracknum
            print(filename)
            filepath = self.get_filepath(filename)
            if not filepath:
                 str_error = "Unable to add to the list, file does not exist. That track has probably not yet been ripped into the music store"
                 self.error_dialog(str_error) 
                 return
            
        treeview_name = treeview.get_name()
        drop_list = (track_id, title_artist, duration)
        path, position = treeview.get_dest_row_at_pos(x, y) or (
            None, None)

        if path:
            tree_iter = model.get_iter(path)
            if (position == Gtk.TreeViewDropPosition.BEFORE
                or position == Gtk.TreeViewDropPosition.INTO_OR_BEFORE):
                tree_iter = model.insert_before(model.get_iter(path), drop_list)
            else:
                tree_iter = model.insert_after(model.get_iter(path), drop_list)                
        else:
            tree_iter = model.append(drop_list)
        
        #If moving, delete originating row
        if "move" in actions.value_nicks:
            source_liststore = treeview.get_model()
            source_selection = treeview.get_selection()
            source_model, source_treeiter = source_selection.get_selected()
            source_liststore.remove(source_treeiter)
            
        else:
            self.dict_pl[track_id] = self.dict_results[track_id]

        path = model.get_path(tree_iter)
        treeview.set_cursor(path)

        self.update_time_total()
        self.changed = True
                    
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
        search_terms = self.get_search_terms()
        query = self.create_query(search_terms)
        result = self.execute_query(query, search_terms)
        
        if result:
            int_res = len(result)
            self.update_result_label(int_res)
            self.length_check(result)
            list_dict_data = self.process_result(result)
            self.add_to_cat_store(list_dict_data)
            
        else:
            self.clear_cat_list()
            int_res = 0
            self.update_result_label(int_res)
    
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
        
        if not (artist or 
            album or 
            track or 
            company or 
            comments or 
            creator or 
            genre or 
            new_release or 
            year or 
            cpa):
            self.error_dialog(str_error_none)
            return False
            
        return search_terms

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
        

        
    def execute_query(self, query, search_terms):
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
            str_warn = (str_warn_0 + 
                str(query_limit) + 
                str_warn_1 + 
                str(query_limit) + 
                str_warn_2 + 
                str_warn_3)
            self.warn_dialog(str_warn)

    def process_result(self, result):
        list_dict_data = []
        first = True
        separator = '''
        -----------------------
        '''
        for item in result:
            if first:
                list_dict_data.append(item)
                first = False
            else:
                # is there a second result for the comment?
                if item["trackid"] == list_dict_data[-1]["trackid"]:
                    list_dict_data[-1]["comment"] = list_dict_data[-1]["comment"] + separator + item["comment"]
                else:
                    list_dict_data.append(item)
        return list_dict_data
    
    def add_to_cat_store(self, list_dict_data):
        '''
        take the results of the search and display as rows in a treeview list
        full search details for each item go into the hidden column 
        '''

        # remove extra results caused by multiple comments 
        # and then concatenate the comments
        self.dict_results = {}
        self.clear_cat_list()
        var_album = ""
        model = self.treeview_cat.get_model()
            
        for item in list_dict_data:
            track_id = item['trackid']
            track_id = str(track_id)
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
                n = model.append(None, [track_id, artist, album, quota, ""])
                model.append(n, [track_id, trackartist, tracktitle, "", dur_time])
            else:
                model.append(n, [track_id, trackartist, tracktitle, "", dur_time])
            var_album = album
            
            self.dict_results[track_id] = item
        
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
        cur.execute(query)
        list_creator = cur.fetchall()
        cur.close()
        conn.close()
        return list_creator

    def cb_creator_add(self, dict_creator):
        '''
        populate the drop down list of contributors
        '''
        liststore_creator = Gtk.ListStore(str)        
        list_creator = sorted(dict_creator.values())
        

        for creator in list_creator:
            self.cb_search_creator.append_text(creator)
        self.cb_search_creator.prepend_text("")
        self.cb_search_creator.append_text("")

    def cb_order_add(self):
        '''
        populate the drop down list for selecting the order to list 
        search results 
        '''
        list_order = list(order_results.keys())
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

    def expand_collapse(self, widget):
        if widget.get_label() == "Expand All":
            self.treeview_cat.expand_all()
            widget.set_label("Collapse All")
        
        elif widget.get_label() == "Collapse All":
            self.treeview_cat.collapse_all()
            widget.set_label("Expand All")
        

    # preview section  
    def get_sel_filepath(self):
        '''
        get the filepath of the track selected in the search results. 
        Combine the cdid with the track number to get the name of the file
        then call the function to get the full path 
        '''
        treeselection = self.treeview_cat.get_selection()
        model, tree_iter = treeselection.get_selected()
        track_id = model.get_value(tree_iter, 0)
        track_data = self.dict_results[track_id]
        ID = track_data['cdid']
        tracknum = track_data['tracknum']
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
            self.player.set_filepath(filepath)
            img = self.btn_pre_play_pause.get_image()
            if img == self.image_play:          
                self.btn_pre_play_pause.set_image(self.image_pause)
                self.player.play()
                
            else:
                self.player.pause()
                self.btn_pre_play_pause.set_image(self.image_play)
                
    def on_stop_clicked(self, widget):
        '''
        stop playing the track
        '''
        self.player.stop()
        self.btn_pre_play_pause.set_image(self.image_play)
        self.label_pre_time.set_text("00:00 / " + self.str_dur)
        self.hscale_pre.set_value(0)
    
    def cat_selection_changed(self, selection):
        '''
        stop playing the preview when another track is selected
        '''
        playstatus = self.player.get_state()     
        if (playstatus == Gst.State.PLAYING) or (playstatus == Gst.State.PAUSED):
            self.player.stop()

    # playlist section
    def update_time_total(self):
        model = self.treeview_pl.get_model()
        tree_iter = model.get_iter_first()
        total_time = 0
        while tree_iter:
            str_duration = model.get_value(tree_iter, 2)
            numbers = reversed(str_duration.split(':'))
            seconds = sum(int(x) * 60 ** i for i, x in enumerate(numbers))
            total_time = total_time + seconds
            tree_iter = model.iter_next(tree_iter)
            
        str_time = self.convert_time(total_time)
        self.label_time_1.set_text(str_time)

    def get_filename(self, act, name):
        '''
        open a file chooser window to open or save a playlist file
    
        '''
        if act == "open_file":
            action = Gtk.FileChooserAction.OPEN
            btn = Gtk.STOCK_OPEN
            title = "Select a Playlist"

        elif act == "save_file":
            action = Gtk.FileChooserAction.SAVE
            btn = Gtk.STOCK_SAVE
            title = "Save Playlist"

        dialog = Gtk.FileChooserDialog(
            title=title,
            action=action
            )
        
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            btn, Gtk.ResponseType.ACCEPT
            )

        dialog.set_default_response(Gtk.ResponseType.ACCEPT)

        dialog.set_current_folder(dir_pl3d)
        dialog.set_do_overwrite_confirmation(True)
        if name:
            dialog.set_current_name(name)
            filetype = name.split(".")[-1]
        
            filter = Gtk.FileFilter()
            if filetype == "p3d":
                filter.set_name("Playlist files")
                filter.add_pattern("*.pl3d")
                filter.add_pattern("*.p3d")

            elif filetype == "mp3":
                filter.set_name("mp3 files")
                filter.add_pattern("*.mp3")
                dialog.set_current_folder(os.path.expanduser('~'))                
        
            dialog.add_filter(filter)   
                 
        response = dialog.run()
        
        if response == Gtk.ResponseType.ACCEPT:
            filename = dialog.get_filename()
            dialog.destroy()
            return filename
           
        else:
            dialog.destroy()    
            return None

    def info_row(self, widget):    
        self.show_details(widget, self.treeview_pl)

    def remove_row(self, widget):    
        treeselection = self.treeview_pl.get_selection()
        model, tree_iter = treeselection.get_selected()
        if tree_iter:
            model.remove(tree_iter) 
            model = self.treeview_pl.get_model()
            self.changed = True
        else:
            print("Nothing selected")
        tree_iter = model.get_iter_first()
        if tree_iter:
            self.update_time_total()
        else:
            self.label_time_1.set_text("00:00  ")

    def get_tracklist(self):
        model = self.treeview_pl.get_model()
        tree_iter = model.get_iter_first()
        ls_tracklist = []
        while tree_iter:
            track_id = model.get_value(tree_iter, 0)
            dict_row = self.dict_pl[track_id]
            ls_tracklist.append(dict_row)
            tree_iter = model.iter_next(tree_iter)

        return ls_tracklist
            
    def open_dialog(self, widget):
        '''
        simply open a playlist - or
        check if there is a changed playlist open and ask if you want to save 
        it before opening another
        '''
        if self.changed:
            response = self.save_change()
            
            if response == Gtk.ResponseType.ACCEPT:
                self.save(None)
            
            elif response == Gtk.ResponseType.CANCEL:
                return

        action = "open_file"
        
        filename = self.get_filename(action, None)
        filesp, filesfx = os.path.splitext(filename)
        self.window.set_title(filesp)
        

        if not (filesfx == sfx or filesfx == sfx_old):
            filename = filename + sfx

        
        if filename:
            title = os.path.basename(filesp)
            self.window.set_title(title)
            self.changed = False
            
        if filesfx == ".p3d":
            ls_data = pickle.load((open(filename, "rb")), encoding='latin1')
            
        elif filesfx == ".pl3d":
            ls_data = self.pl3d2pylist(filename)

        model = self.treeview_pl.get_model()
        model.clear()
        self.dict_pl = {}
        
        for dict_data in ls_data:
            track_id = str(dict_data['trackid'])
            int_time = dict_data['tracklength']
            tracktime = self.convert_time(int_time)
            tracktitle = dict_data['tracktitle']
            trackartist = dict_data['trackartist']
            
            if not trackartist:
                artist = dict_data['artist']
                trackartist = artist
                
            tracktitle = trackartist + '\n' + tracktitle
            
                
            model.append((track_id, tracktitle, tracktime))
            
            self.update_time_total()
            self.name_of_open_file = filename
            self.dict_pl[track_id] = dict_data

    
    def confirm_close(self):
        dialog = Gtk.Dialog("Confirm Close")
        dialog.set_default_size(150, 100)
        message = "Are you sure you want to close ListMaker?"
        dialog.add_buttons("OK", Gtk.ResponseType.OK,
                "Cancel", Gtk.ResponseType.CANCEL)
        label = Gtk.Label(label=message)
        label.set_line_wrap(True)
        box = dialog.get_content_area()
        box.add(label)
        dialog.show_all()
        
        response = dialog.run()
        dialog.destroy()
    
        if response == Gtk.ResponseType.OK:
            self.window.destroy()
            return False
        else:
            return True        
    
    
    def save_change(self):
        dialog = Gtk.Dialog("List Changed")
        dialog.set_default_size(150, 100)
        dialog.add_buttons("Save", Gtk.ResponseType.ACCEPT,
                  "Discard", Gtk.ResponseType.REJECT,
                  "Cancel", Gtk.ResponseType.CANCEL)

        message = "Your list has changed, do you want to save it?"
        label = Gtk.Label(label=message)
        label.set_line_wrap(True)
        box = dialog.get_content_area()
        box.add(label)
        dialog.show_all()

        response = dialog.run()
        dialog.destroy()
        return response
        

                
    def new(self, widget):
        '''
        confirm save existing playlist
        clear tracks from treeviews and dictionaries
        use filechooser to select name and path of new list
        '''
        if self.changed:
            response = self.save_change()
        
            if response == Gtk.ResponseType.ACCEPT:
                self.save(None)
            
            elif response == Gtk.ResponseType.CANCEL:
                return
            
        model = self.treeview_pl.get_model()
        model.clear()
        model = self.treeview_cat.get_model()
        model.clear()
        
        self.changed = False
        
        self.dict_pl = {}
        self.dict_results = ()
        self.window.set_title("Untitled")
        self.Saved = False
        self.name_of_open_file = None
        
    def save(self, widget):
        '''
        save the file. First check that it is not a new file.
        '''
        if self.name_of_open_file:
            filename = self.name_of_open_file      
            ls_tracklist = self.get_tracklist()
            pickle.dump(ls_tracklist, open(filename, "wb"), protocol=0)

        else:
            action = "save_file"
            filename = self.get_filename(action, 'Untitled.p3d')
            filesp, filesfx = os.path.splitext(filename)

            if not filesfx == sfx:
                filename = filesp + sfx
                
            if filename: 
                ls_tracklist = self.get_tracklist()
                try: 
                    pickle.dump(ls_tracklist, open(filename, "wb"), protocol=0)
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
        
        if filename:
            filesp, filesfx = os.path.splitext(filename)
            if not (filesfx == sfx):
                filename = filesp + sfx
            
            title = os.path.basename(filesp)
            self.window.set_title(title)
            self.changed = False
            
            ls_tracklist = self.get_tracklist()
            pickle.dump(ls_tracklist, open(filename, "wb"), protocol=0)
            self.name_of_open_file = filename

    def export(self, widget):
        '''
        combine and save the tracks in the playlist into a single mp3
        '''
        # get and the file path for each track and add to a list
        filelist = []
        model = self.treeview_pl.get_model()
        for row in model:
            track_id = row[0]
            dict_data = self.dict_pl[track_id]
            cdid = dict_data['cdid'] 
            tracknum = dict_data['tracknum']
            ID = str(cdid).zfill(7) + "-" + str(tracknum).zfill(2)
            filepath = self.get_filepath(ID)
            filelist.append(filepath)
        
        
        if filelist:
            # run the filechooser to select where to save
            action = "save_file"
            name = "Untitled.mp3"  
            export_file =  self.get_filename(action, name)
            if export_file:
                dialog = SpinnerDialog(self.window, filelist, export_file)
            else:
                message = "Export cancelled"
                self.error_dialog(message)            
        else:
            message = "You need to have something in the playlist before you can export it"
            self.error_dialog(message)
            
                
    def pl3d2pylist(self, filename):
        '''
        convert the information in an pl3d file to a python list
        '''
        doc = etree.parse(filename)
        pl3d_ns = "http://xspf.org/ns/0/"
        ns = "{%s}" % pl3d_ns
        el_tracklist = doc.findall("//%strack" % ns)
        ls_tracklist = []
        ls_data = []

        for track in el_tracklist:
            if track.find("%sidentifier" % ns) is not None:
                track_id = track.find("%sidentifier" % ns).text
                track_id = int(track_id)
                ls_tracklist.append(track_id)
        
        for track_id in ls_tracklist:
            search_terms = {}
            search_terms["cdtrack.trackid"] = track_id
            query = self.create_query(search_terms)
            result = self.execute_query(query, search_terms)
            dict_data = self.process_result(result)
            ls_data += dict_data
            
        return ls_data


    #common functions
    def right_click_cat_list_menu(self, treeview, event):
        if event.button == 3: # right click
            selection = treeview.get_selection()
            model, tree_iter = selection.get_selected()
            track_id = model.get_value(tree_iter, 0)
            duration = model.get_value(tree_iter, 4)
            dict_data = self.dict_results[track_id]
            context_menu = Gtk.Menu()
            details_item = Gtk.MenuItem(label = "Details")
            details_item.connect( "activate", self.show_details, treeview)
            details_item.show()
            play_item = Gtk.MenuItem(label = "Play")
            play_item.connect("activate", self.play_from_menu, treeview, track_id)
            play_item.show()
            add_item = Gtk.MenuItem(label = "Add")
            add_item.connect("activate", self.add_to_playlist, treeview)
            add_item.show()
            context_menu.append(details_item)
            context_menu.append(play_item)
            context_menu.append(add_item)
            
            if not duration:
                play_item.set_sensitive(False)
                add_item.set_sensitive(False)
                
            context_menu.popup_at_pointer()
    
    def right_click_pl_list_menu(self, treeview, event):
        if event.button == 3: # right click
            selection = treeview.get_selection()
            model, tree_iter = selection.get_selected()
            track_id = model.get_value(tree_iter, 0)
            context_menu = Gtk.Menu()
            remove_item = Gtk.MenuItem(label = "Remove")
            remove_item.connect("activate", self.remove_row)
            remove_item.show()
            details_item = Gtk.MenuItem(label = "Details")
            details_item.connect("activate", self.show_details, treeview)
            details_item.show()
            play_item = Gtk.MenuItem(label = "Play")
            play_item.connect( "activate", self.play_from_menu, treeview, track_id)
            play_item.show()
            context_menu.append(remove_item)
            context_menu.append(details_item)
            context_menu.append(play_item)
            context_menu.popup_at_pointer()

    def add_to_playlist(self, widget, treeview):
        '''
        from right-click menu add the selected track to the playlist
        '''
        treeselection = treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        track_id = model.get_value(tree_iter, 0)      
        title = model.get_value(tree_iter, 2) 
        artist = model.get_value(tree_iter, 1) 
        duration = model.get_value(tree_iter, 4)
        title_artist = title + '\n' + artist
        add_list = (track_id, title_artist, duration)
        
        model_pl = self.treeview_pl.get_model()
        tree_iter = model_pl.append(add_list)
        self.dict_pl[track_id] = self.dict_results[track_id]
        
        path = model_pl.get_path(tree_iter)
        self.treeview_pl.set_cursor(path)

        self.update_time_total()
        self.changed = True
        
    def get_details(self, treeview):
        treeview_name = treeview.get_name()
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        track_id = model.get_value(tree_iter, 0)
        
        if treeview_name == "pl":
            dict_data = self.dict_pl[track_id]
            dict_data["is_cd"] = False 
            
        else:
            duration = model.get_value(tree_iter, 4)
        
            if not duration:
                dict_data = self.dict_results[track_id]
                dict_data["is_cd"] = True
            
            else:
                dict_data = self.dict_results[track_id]
                dict_data["is_cd"] = False        
            
        return dict_data
        
    def show_details(self, widget, treeview):
        
        dialog = Gtk.Dialog(
            title = "Details", 
            transient_for = self.window,
            flags = 0
            )
        dialog.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        grid_details = Gtk.Grid(hexpand=True, vexpand=False)
        grid_details.set_row_homogeneous(False)
        grid_details.set_column_homogeneous(False)
        grid_details.set_valign(Gtk.Align.FILL)
        grid_details.set_margin_top(margin=5)                                                                            
        grid_details.set_margin_end(margin=5)                                                                            
        grid_details.set_margin_bottom(margin=5)                                                                         
        grid_details.set_margin_start(margin=5)                                                                          
        grid_details.set_row_spacing(spacing=5)                                                                          
        grid_details.set_column_spacing(spacing=5)
        
        dialog.vbox.pack_start(grid_details, True, True, 0)
        dict_details = self.get_details(treeview)
        is_cd = dict_details["is_cd"]
        
        n = 0

        artist = dict_details["artist"]
            
        label_detail_artist = Gtk.Label()

        label_detail_artist.set_halign(Gtk.Align.START)
        label_detail_artist.set_hexpand(True)
        label_detail_artist.set_justify(Gtk.Justification.LEFT)
        label_detail_artist.set_text("Album Artist: ")        
        grid_details.attach(
            child=label_detail_artist, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )
        
        label_artist = Gtk.Label()
        label_artist.set_halign(Gtk.Align.START)
        label_artist.set_hexpand(True)
        label_artist.set_justify(Gtk.Justification.LEFT)
        label_artist.set_text(artist)
        label_artist.set_selectable(True)
        grid_details.attach(
            child=label_artist, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )

        n += 1 

        if not is_cd:
            trackartist = dict_details["trackartist"]
            
            if trackartist and trackartist != artist:
                label_detail_trackartist = Gtk.Label()
                label_detail_trackartist.set_halign(Gtk.Align.START)
                label_detail_trackartist.set_hexpand(True)
                label_detail_trackartist.set_justify(Gtk.Justification.LEFT)
                label_detail_trackartist.set_text("Track Artist: ")        
                grid_details.attach(
                    child=label_detail_trackartist, 
                    left=0, 
                    top=n, 
                    width=1,
                    height=1
                    )
                
                label_trackartist = Gtk.Label()
                label_trackartist.set_halign(Gtk.Align.START)
                label_trackartist.set_hexpand(True)
                label_trackartist.set_justify(Gtk.Justification.LEFT)
                label_trackartist.set_text(trackartist)
                label_trackartist.set_selectable(True)
                grid_details.attach(
                    child=label_trackartist, 
                    left=1, 
                    top=n, 
                    width=1,
                    height=1
                    )

            n += 1 

        if "tracktitle" in dict_details and not is_cd:
            label_detail_track = Gtk.Label()
            label_detail_track.set_text("Track: ")
            label_detail_track.set_halign(Gtk.Align.START)
            label_detail_track.set_hexpand(True)
            label_detail_track.set_justify(Gtk.Justification.LEFT)
            grid_details.attach(
                child=label_detail_track, 
                left=0, 
                top=n, 
                width=1,
                height=1
                )
            
            label_track = Gtk.Label()
            track = dict_details['tracktitle']
            label_track.set_text(track)
            label_track.set_selectable(True)
            label_track.set_halign(Gtk.Align.START)
            label_track.set_hexpand(True)
            label_track.set_justify(Gtk.Justification.LEFT)
            grid_details.attach(
                child=label_track, 
                left=1, 
                top=n, 
                width=1,
                height=1
                )
            
            n += 1    
                
        label_detail_album = Gtk.Label()
        label_detail_album.set_text("Album: ")
        label_detail_album.set_halign(Gtk.Align.START)
        label_detail_album.set_hexpand(True)
        label_detail_album.set_justify(Gtk.Justification.LEFT)
        grid_details.attach(
            child=label_detail_album, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )
        
        label_album = Gtk.Label()
        album = dict_details['title']
        label_album.set_text(album)
        label_album.set_selectable(True)
        label_album.set_halign(Gtk.Align.START)
        label_album.set_hexpand(True)
        label_album.set_justify(Gtk.Justification.LEFT)
        grid_details.attach(
            child=label_album, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )

        n += 1

        label_detail_local = Gtk.Label()
        label_detail_local.set_halign(Gtk.Align.START)
        label_detail_local.set_hexpand(True)
        label_detail_local.set_justify(Gtk.Justification.LEFT)
        label_detail_local.set_text("Local: ")
        grid_details.attach(
            child=label_detail_local, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )
                
        label_local = Gtk.Label()
        label_local.set_halign(Gtk.Align.START)
        label_local.set_hexpand(True)
        label_local.set_justify(Gtk.Justification.LEFT)
        local = dict_details['local']
        local = unys[local]
        label_local.set_text(local)
        grid_details.attach(
            child=label_local, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )
        
        n += 1

        label_detail_female = Gtk.Label()
        label_detail_female.set_halign(Gtk.Align.START)
        label_detail_female.set_hexpand(True)
        label_detail_female.set_justify(Gtk.Justification.LEFT)
        label_detail_female.set_text("Female: ")
        grid_details.attach(
            child=label_detail_female, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )   

        label_female = Gtk.Label()
        label_female.set_halign(Gtk.Align.START)
        label_female.set_hexpand(True)
        label_female.set_justify(Gtk.Justification.LEFT)
        label_female.set_selectable(True)
        female = dict_details['female']
        female = unys[female]
        label_female.set_text(female)
        grid_details.attach(
            child=label_female, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )
        
        n += 1
        
        if "tracklength" in dict_details and not is_cd:
            label_detail_tracklength = Gtk.Label()
            label_detail_tracklength.set_halign(Gtk.Align.START)
            label_detail_tracklength.set_hexpand(True)
            label_detail_tracklength.set_justify(Gtk.Justification.LEFT)
            label_detail_tracklength.set_text("Track Length: ")
            grid_details.attach(
                child=label_detail_tracklength, 
                left=0, 
                top=n, 
                width=1,
                height=1
                )
            
            label_tracklength = Gtk.Label()
            label_tracklength.set_halign(Gtk.Align.START)
            label_tracklength.set_hexpand(True)
            label_tracklength.set_justify(Gtk.Justification.LEFT)            
            tracklength = dict_details['tracklength']
            str_tracklength = self.convert_time(tracklength)
            label_tracklength.set_text(str_tracklength)
            label_tracklength.set_selectable(True)
            grid_details.attach(
                child=label_tracklength, 
                left=1, 
                top=n, 
                width=1,
                height=1
                )
        
        n += 1

        label_detail_demo = Gtk.Label()
        label_detail_demo.set_halign(Gtk.Align.START)
        label_detail_demo.set_hexpand(True)
        label_detail_demo.set_justify(Gtk.Justification.LEFT)
        label_detail_demo.set_text("Demo: ")
        grid_details.attach(
            child=label_detail_demo, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )

        label_demo = Gtk.Label()
        label_demo.set_halign(Gtk.Align.START)
        label_demo.set_hexpand(True)
        label_demo.set_justify(Gtk.Justification.LEFT)
        label_demo.set_selectable(True)
        demo = dict_details['demo']
        if not demo:
            demo = 0
        demo = unys[demo]
        label_demo.set_text(demo)
        grid_details.attach(
            child=label_demo, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )
        
        n += 1
        
        label_detail_compilation = Gtk.Label()
        label_detail_compilation.set_halign(Gtk.Align.START)
        label_detail_compilation.set_hexpand(True)
        label_detail_compilation.set_justify(Gtk.Justification.LEFT)
        label_detail_compilation.set_text("Compilation: ")
        grid_details.attach(
            child=label_detail_compilation, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )     

        label_compilation = Gtk.Label()
        label_compilation.set_halign(Gtk.Align.START)
        label_compilation.set_hexpand(True)
        label_compilation.set_justify(Gtk.Justification.LEFT)
        label_compilation.set_selectable(True)
        compilation = dict_details['compilation']
        compilation = unys[compilation]
        label_compilation.set_text(compilation)
        grid_details.attach(
            child=label_compilation, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )
        
        n += 1

        label_detail_company = Gtk.Label()
        label_detail_company.set_halign(Gtk.Align.START)
        label_detail_company.set_hexpand(True)
        label_detail_company.set_justify(Gtk.Justification.LEFT)
        label_detail_company.set_text("Company: ")
        grid_details.attach(
            child=label_detail_company, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )    
        
        label_company = Gtk.Label()
        label_company.set_halign(Gtk.Align.START)
        label_company.set_hexpand(True)
        label_company.set_justify(Gtk.Justification.LEFT)
        label_company.set_selectable(True)
        company = dict_details['company']
        if company:
            label_company.set_text(company)
        grid_details.attach(
            child=label_company, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )
        
        n += 1
        
        label_detail_year = Gtk.Label()
        label_detail_year.set_halign(Gtk.Align.START)
        label_detail_year.set_hexpand(True)
        label_detail_year.set_justify(Gtk.Justification.LEFT)
        label_detail_year.set_text("Release Year: ") 
        grid_details.attach(
            child=label_detail_year, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )   

        label_year = Gtk.Label()
        label_year.set_halign(Gtk.Align.START)
        label_year.set_hexpand(True)
        label_year.set_justify(Gtk.Justification.LEFT)
        label_year.set_selectable(True)
        year = dict_details['year']
        if year:
            year = str(year)
            label_year.set_text(year) 
        grid_details.attach(
            child=label_year, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )

        n += 1

        label_detail_cpa = Gtk.Label()
        label_detail_cpa.set_halign(Gtk.Align.START)
        label_detail_cpa.set_hexpand(True)
        label_detail_cpa.set_justify(Gtk.Justification.LEFT)
        label_detail_cpa.set_text("Country: ")
        grid_details.attach(
            child=label_detail_cpa, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )    
       
        label_cpa = Gtk.Label()
        label_cpa.set_halign(Gtk.Align.START)
        label_cpa.set_hexpand(True)
        label_cpa.set_justify(Gtk.Justification.LEFT)
        label_cpa.set_selectable(True)
        cpa = dict_details['cpa']
        if cpa:
            label_cpa.set_text(cpa)
        grid_details.attach(
            child=label_cpa, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )

        n += 1

        label_detail_genre = Gtk.Label()
        label_detail_genre.set_halign(Gtk.Align.START)
        label_detail_genre.set_hexpand(True)
        label_detail_genre.set_justify(Gtk.Justification.LEFT)
        label_detail_genre.set_text("Genre: ")
        grid_details.attach(
            child=label_detail_genre, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )  
       
        
        label_genre = Gtk.Label()
        label_genre.set_halign(Gtk.Align.START)
        label_genre.set_hexpand(True)
        label_genre.set_justify(Gtk.Justification.LEFT)
        label_genre.set_selectable(True)
        genre = dict_details['genre']
        if genre:
            label_genre.set_text(genre)
        grid_details.attach(
            child=label_genre, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )

        n += 1

        label_detail_createwho = Gtk.Label()
        label_detail_createwho.set_halign(Gtk.Align.START)
        label_detail_createwho.set_hexpand(True)
        label_detail_createwho.set_justify(Gtk.Justification.LEFT)
        label_detail_createwho.set_text("Added By: ")
        grid_details.attach(
            child=label_detail_createwho, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )   
       
        
        label_createwho = Gtk.Label()
        label_createwho.set_halign(Gtk.Align.START)
        label_createwho.set_hexpand(True)
        label_createwho.set_justify(Gtk.Justification.LEFT)
        label_createwho.set_selectable(True)
        createwho = dict_details['createwho']
        if createwho:
            createwho = self.dict_creator[createwho]
            label_createwho.set_text(createwho)
        grid_details.attach(
            child=label_createwho, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )

        n += 1
       
        label_detail_createwhen = Gtk.Label()
        label_detail_createwhen.set_halign(Gtk.Align.START)
        label_detail_createwhen.set_hexpand(True)
        label_detail_createwhen.set_justify(Gtk.Justification.LEFT)
        label_detail_createwhen.set_text("Date Added: ")
        grid_details.attach(
            child=label_detail_createwhen, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )   
         
        label_createwhen = Gtk.Label()
        label_createwhen.set_halign(Gtk.Align.START)
        label_createwhen.set_hexpand(True)
        label_createwhen.set_justify(Gtk.Justification.LEFT)
        label_createwhen.set_selectable(True)
        createwhen = dict_details['createwhen']
        if createwhen:
            createwhen = datetime.datetime.fromtimestamp(createwhen)
            createwhen = createwhen.strftime("%d/%m/%Y")
            label_createwhen.set_text(createwhen)
        grid_details.attach(
            child=label_createwhen, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )

        n += 1
                
        label_detail_id = Gtk.Label()
        label_detail_id.set_halign(Gtk.Align.START)
        label_detail_id.set_hexpand(True)
        label_detail_id.set_justify(Gtk.Justification.LEFT)
        label_detail_id.set_text("CD ID Number: ")
        grid_details.attach(
            child=label_detail_id, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )
        
        label_id = Gtk.Label()
        label_id.set_halign(Gtk.Align.START)
        label_id.set_hexpand(True)
        label_id.set_justify(Gtk.Justification.LEFT)
        cdid = dict_details["cdid"]
        cdid = str(cdid)
        label_id.set_text(cdid)
        label_id.set_selectable(True)
        grid_details.attach(
            child=label_id, 
            left=1, 
            top=n, 
            width=1,
            height=1
            )

        n += 1

        label_detail_comment = Gtk.Label()
        label_detail_comment.set_halign(Gtk.Align.START)
        label_detail_comment.set_hexpand(True)
        label_detail_comment.set_justify(Gtk.Justification.LEFT)
        label_detail_comment.set_text("Comments: ")
        grid_details.attach(
            child=label_detail_comment, 
            left=0, 
            top=n, 
            width=1,
            height=1
            )

        label_comment = Gtk.Label()
        label_comment.set_halign(Gtk.Align.FILL)
        label_comment.set_hexpand(True)
        label_comment.set_selectable(True)
        label_comment.set_max_width_chars(40)
        label_comment.set_line_wrap(True)        
        
        cdcomment = dict_details['comment']
        createwho = dict_details['createwho']
        
        f = base64.b64decode(b'ZnVjaw==').decode()
        c = base64.b64decode(b'Y3VudA==').decode()

        if cdcomment and (createwho != 60):
            l = cdcomment.lower()
            if any(s not in l for s in (f, c)):
                cdcomment = cdcomment.strip()
                label_comment.set_text(cdcomment)
                grid_details.attach(
                    child=label_comment, 
                    left=1, 
                    top=n, 
                    width=1,
                    height=1
                    )

        dialog.show_all()
        dialog.run()    
        dialog.destroy()        

    def play_from_menu(self, widget, treeview, track_id):
        if treeview.get_name() == 'pl':
            dict_data = self.dict_pl[track_id] 
        else:
            dict_data = self.dict_results[track_id]        
        cdid = (dict_data["cdid"])
        cdid = str(cdid).zfill(7)
        tracknum = (dict_data["tracknum"])
        tracknum = str(tracknum).zfill(2)
        
        ID = cdid + "-" + tracknum
        filepath = self.get_filepath(ID)
                   
        if filepath:
            self.player.stop()
            self.player.set_filepath(filepath)
            img = self.btn_pre_play_pause.get_image()
            if img == self.image_play:          
                self.btn_pre_play_pause.set_image(self.image_pause)
                self.player.play()

        
    def convert_time(self, dur):
        '''
        process number into hh:mm:ss
        '''
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
        messagedialog = Gtk.MessageDialog(
            #transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=str_warn)
        messagedialog.run()
        messagedialog.destroy()
    
    def error_dialog(self, str_error):
        messagedialog = Gtk.MessageDialog(
            #transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=str_error
            )

        messagedialog.run()
        messagedialog.destroy()  
        

lm = List_Maker()
lm.main()
        
'''
Feature request
Tooltip over list to show artist name

'''
