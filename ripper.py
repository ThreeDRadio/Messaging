#!/usr/bin/python
#ripper.py
'''
rip CDs into the ThreeD catalogue
version 1.1.1 
    add full keystroke functionality (shift tab and text buffer)
    have artist first
'''


import os
import sys
import pango
import pwd
import time
import datetime
import calendar
import locale
import ConfigParser

import CDDB
import DiscID
import pycountry
import vte
import subprocess
import psycopg2
import pygtk
import gtk
import gobject
import glib
import pygame
import musicbrainz2.disc as mbdisc
import musicbrainz2.webservice as mbws

#get variables from config file
config = ConfigParser.SafeConfigParser()
config.read('/usr/local/etc/threedradio.conf')

dir_wav = config.get('Paths', 'dir_wav')
dir_mus = config.get('Paths', 'dir_mus')
pg_user = config.get('Ripper', 'pg_user')
pg_password = config.get('Ripper', 'pg_password')
pg_server = config.get('Common', 'pg_server')
pg_cat_database = config.get('Common', 'pg_cat_database')

encoding = locale.getpreferredencoding()
utf8conv = lambda x : unicode(x, encoding).encode('utf8')

path_image_cd = "/usr/local/share/images/Chrisdesign_CD_DVD.svg"
header_font = pango.FontDescription("Sans Bold 18")
subheader_font = pango.FontDescription("Sans Bold 12")

#Initialise cdrom and get CD instance
#will need to edit if more than one CD device is used
pygame.cdrom.init()
CD = pygame.cdrom.CD(0)
CD.init()

class Progress():
    '''
    display the progress of the cdparanoia ripping program using vte
    '''
    def __init__(self, destination):
        str_head = "Ripping in Progress - Please do not Close"    
        dialog = gtk.Dialog(str_head, None, 0, None)    
  
        v = vte.Terminal ()
        v.set_sensitive(False)
        v.connect ("child-exited", lambda term: dialog.destroy())
        pid = v.fork_command('bash')
        
        str_rip = 'cdparanoia -ZB 1:- {0}\n'.format(destination)
        v.feed_child(str_rip)
        v.feed_child('sleep 6\n')
        v.feed_child('\n exit \n')  
 
        dialog.vbox.pack_start(v, True, True, 0)
        dialog.show_all()
        dialog.run()    
        dialog.destroy()  
       
class Ripper():

    def __init__(self):
        window = gtk.Window(gtk.WINDOW_TOPLEVEL) 
        window.set_position(gtk.WIN_POS_CENTER)
        window.set_size_request(620, 930)
        window.connect("destroy", lambda w: gtk.main_quit())          
        
        #---boxes and packing containers ---
        vbox_main = gtk.VBox(False, 5)
        hbox_head = gtk.HBox(False, 5)
        hbox_cb = gtk.HBox(False, 5)  
        table = gtk.Table(6, 6, False)
        hbox_btn = gtk.HBox(False, 5)
        hbox_btn.set_homogeneous(True)
        vbox_local = gtk.VBox(False, 5)
        vbox_local.set_border_width(1)
        vbox_female = gtk.VBox(False, 5)
        vbox_demo = gtk.VBox(False, 5)
        vbox_compilation = gtk.VBox(False, 5)
        vbox_released = gtk.VBox(False, 5)
        self.sw_tracks = gtk.ScrolledWindow()
        self.sw_tracks.set_size_request(600, 540)
        sw_comment = gtk.ScrolledWindow()
        sw_comment.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        hbox_info_labels = gtk.HBox(False, 5)
        hbox_created = gtk.HBox(False, 5)
        hbox_idcode = gtk.HBox(False, 5)
                
        # --- header section ---
        label_cd = gtk.Label("CD Ripper")
        label_cd.modify_font(header_font)
        
        pixbuf_cd = gtk.gdk.pixbuf_new_from_file_at_size(
                                    path_image_cd, 48, 48)
        image_cd = gtk.Image()
        image_cd.set_from_pixbuf(pixbuf_cd)
        image_cd2 = gtk.Image()
        image_cd2.set_from_pixbuf(pixbuf_cd)    
        
        # --- CD details ---
        label_artist = gtk.Label("Artist: ")
        label_artist.modify_font(subheader_font)
        self.entry_artist = gtk.Entry()
        self.entry_artist.set_width_chars(60)
        label_title = gtk.Label("CD Title: ")
        label_title.modify_font(subheader_font)
        self.entry_title = gtk.Entry()
        self.entry_title.set_width_chars(60)
        label_company = gtk.Label("Company: ")
        self.entry_company = gtk.Entry()
        self.entry_company.set_width_chars(60)
        label_genre = gtk.Label("Genre: ")
        self.entry_genre = gtk.Entry()
        self.entry_genre.set_width_chars(60)
        label_arrived = gtk.Label("Arrived at Three D:")
        self.entry_arrived = gtk.Entry()
        self.entry_arrived.set_width_chars(10)
        today = self.get_date()
        self.entry_arrived.set_text(today)
        label_country = gtk.Label("Country: ")
        self.entry_country = gtk.Entry()  
        label_copies = gtk.Label("Copies")
        adj = gtk.Adjustment(1, 0, 1000, 1, 10, 0)
        self.sb_copies = gtk.SpinButton(adj)
        
        hseparator0 = gtk.HSeparator()
        
        label_local = gtk.Label("Local    ")
        self.cb_local = gtk.combo_box_new_text()
        self.cb_local.append_text("Don't Know")
        self.cb_local.append_text("No")
        self.cb_local.append_text("Yes")
        self.cb_local.append_text("Some")
        self.cb_local.set_active(0)

        label_female = gtk.Label("Female    ")
        self.cb_female = gtk.combo_box_new_text()
        self.cb_female.append_text("Don't Know")
        self.cb_female.append_text("No")
        self.cb_female.append_text("Yes")
        self.cb_female.append_text("Some")
        self.cb_female.set_active(0)
        
        label_demo = gtk.Label("Demo    ")
        self.cb_demo = gtk.combo_box_new_text()
        self.cb_demo.append_text("Don't Know")
        self.cb_demo.append_text("No")
        self.cb_demo.append_text("Yes")
        self.cb_demo.append_text("Some")
        self.cb_demo.set_active(0)
        
        label_compilation = gtk.Label("Compilation    ")
        self.cb_compilation = gtk.combo_box_new_text()
        self.cb_compilation.append_text("Don't Know")
        self.cb_compilation.append_text("No")
        self.cb_compilation.append_text("Yes")
        self.cb_compilation.set_active(0)
        
        label_released = gtk.Label("Release Year    ")
        self.cb_released = gtk.combo_box_new_text()
        self.release_dates()
       
        # --- list the tracks ---
        store = gtk.ListStore(str, str, str, str, int)
        self.treeview = gtk.TreeView(store)
        self.treeview.set_rules_hint(True)
        self.add_columns(self.treeview)
        
        # --- comments section ---
        label_comment = gtk.Label("Comment")
        label_comment.set_alignment(0, 0)
        label_comment.set_padding(5, 0)
        self.textview_comment = gtk.TextView(buffer=None) 
        self.textview_comment.set_accepts_tab(False)
        self.textview_comment.set_wrap_mode(gtk.WRAP_WORD)
        self.textview_comment.set_border_window_size(
                                            gtk.TEXT_WINDOW_LEFT, 5)
        self.textview_comment.set_border_window_size(
                                            gtk.TEXT_WINDOW_RIGHT, 5)
        self.textview_comment.set_border_window_size(
                                            gtk.TEXT_WINDOW_BOTTOM, 5)
        self.textview_comment.set_border_window_size(
                                            gtk.TEXT_WINDOW_TOP, 5)
                                            
                                            
        # --- info labels ---
        label_created = gtk.Label("Ripped by:  ")
        self.label_usr = gtk.Label()
        user = self.get_pc_user()[1]
        user = user.strip(',')
        self.label_usr.set_text(user)
        self.label_date = gtk.Label()
        today = self.get_date()
        self.label_date.set_text(today)
        label_idcode = gtk.Label("ID Code: ")
        self.label_idcode_detail = gtk.Label()
        self.label_idcode_detail.set_width_chars(9)
        
        # --- buttons --- #
        btn_eject = gtk.Button("_Eject")        
        btn_clear = gtk.Button("Clear _All")        
        btn_trackcount = gtk.Button("_Tracks")
        str_trackcount = "Blank list of all the tracks on the CD"
        btn_trackcount.set_tooltip_text(str_trackcount)
        btn_online = gtk.Button("_Online")
        str_online = "Check the details, online search results can be "\
                                                                "wrong!"
        btn_online.set_tooltip_text(str_online)
        btn_dup = gtk.Button("_Catalogue")
        str_dup = "Check to see if this CD has been catalogued"
        btn_dup.set_tooltip_text(str_dup)
        
        btn_idcode = gtk.Button("_ID Code")
        str_idcode = "You know the CD is in the catalogue and you "\
                                                    "have the ID code" 
        btn_idcode.set_tooltip_text(str_idcode)
        btn_rip = gtk.Button("_Rip")
        btn_rip.set_size_request(32, 32)
                 
        # connecting
        btn_eject.connect("clicked", self.eject)
        btn_clear.connect("clicked", self.clear_entries)        
        btn_trackcount.connect("clicked", self.check_cd_drive)
        btn_online.connect("clicked", self.check_online)
        btn_dup.connect("clicked", self.check_dup)
        btn_idcode.connect("clicked", self.set_idcode)
        btn_rip.connect("clicked", self.rip)
        
        self.treeview.connect('key-press-event', self.key_tree)
        
        # packing
        table.attach(label_artist, 0, 1, 0, 1, False, False, 5, 0)
        table.attach(self.entry_artist, 1, 6, 0, 1, True, True, 5, 0)
        table.attach(label_title, 0, 1, 1, 2, False, False, 5, 0)
        table.attach(self.entry_title, 1, 6, 1, 2, True, True, 5, 0)        
        table.attach(label_company, 0, 1, 2, 3, False, False, 5, 0)
        table.attach(self.entry_company, 1, 6, 2, 3, True, True, 5, 0)
        table.attach(label_genre, 0, 1, 3, 4, False, False, 5, 0)
        table.attach(self.entry_genre, 1, 6, 3, 4, True, True, 5, 0)
        table.attach(label_country, 0, 1, 4, 5, False, False, 5, 0)
        table.attach(self.entry_country, 1, 2, 4, 5, True, True, 5, 0)
        table.attach(label_arrived, 2, 3, 4, 5, False, False, 5, 0)
        table.attach(self.entry_arrived, 3, 4, 4, 5, True, True, 5, 0)
        table.attach(label_copies, 4, 5, 4, 5, False, False, 5, 0)
        table.attach(self.sb_copies, 5, 6, 4, 5, True, True, 5, 0)
                 
        sw_comment.add(self.textview_comment)        
        self.sw_tracks.add(self.treeview)
        hbox_head.pack_start(image_cd, False)
        hbox_head.pack_start(label_cd, True)
        hbox_head.pack_end(image_cd2, False)
        
        vbox_local.pack_start(label_local, False)
        vbox_local.pack_start(self.cb_local, False)
        
        vbox_female.pack_start(label_female, False)
        vbox_female.pack_start(self.cb_female, False)
        
        vbox_demo.pack_start(label_demo, False)
        vbox_demo.pack_start(self.cb_demo, False)
        
        vbox_compilation.pack_start(label_compilation, False)
        vbox_compilation.pack_start(self.cb_compilation, False)
        
        vbox_released.pack_start(label_released, False)
        vbox_released.pack_start(self.cb_released, False)
        
        hbox_cb.pack_start(vbox_local, True)
        hbox_cb.pack_start(vbox_female, True)
        hbox_cb.pack_start(vbox_demo, True)
        hbox_cb.pack_start(vbox_compilation, True)
        hbox_cb.pack_start(vbox_released, True)
        
        hbox_created.pack_start(label_created, False)
        hbox_created.pack_start(self.label_usr, False)
        hbox_created.pack_start(self.label_date, False)

        hbox_idcode.pack_end(self.label_idcode_detail, False)
        hbox_idcode.pack_end(label_idcode, False)

        hbox_info_labels.pack_start(hbox_created, False)
        hbox_info_labels.pack_end(hbox_idcode)

        hbox_btn.pack_start(btn_eject, True)
        hbox_btn.pack_start(btn_clear, True)
        hbox_btn.pack_start(btn_trackcount, True)
        hbox_btn.pack_start(btn_online, True)
        hbox_btn.pack_start(btn_dup, True)
        hbox_btn.pack_start(btn_idcode, True)
        hbox_btn.pack_end(btn_rip, True)

        vbox_main.pack_start(hbox_head, False)
        vbox_main.pack_start(table, False)
        vbox_main.pack_start(hseparator0, False)
        vbox_main.pack_start(hbox_cb, False, False, 5)
        vbox_main.pack_start(self.sw_tracks, True)
        vbox_main.pack_start(label_comment, False)
        vbox_main.pack_start(sw_comment, True,)
        vbox_main.pack_start(hbox_info_labels, False)      
        vbox_main.pack_start(hbox_btn, False)

        window.add(vbox_main)
        
        dialog_type = gtk.MESSAGE_INFO
        string = '''
---  LAYOUT CHANGE  ---

The Artist entry is now at the top 
and the CD Title entry is below it. '''    
        self.message_dialog(dialog_type, string)
        
        window.show_all()

    def key_tree(self, treeview, event):
        '''
        enable (shift)tab key(s) to navigate track title and artist
        in the track list
        '''
        keyname = event.keyval
        path, col = treeview.get_cursor() 
        ## only visible columns!! 
        columns = [c for c in treeview.get_columns() if c.get_visible()] 
        colnum = columns.index(col)     


        if keyname==65289: #TAB
            self.tree_tab(treeview, path, columns, colnum, keyname)
            
        elif keyname==65056: #SHIFT+TAB
            self.tree_shifttab(treeview, path, columns, colnum, keyname)

    def tree_tab(self, treeview, path, columns, colnum, keyname):
        if colnum == 1: 
            move_to = columns[2]               

        else: 
            tmodel = treeview.get_model() 
            titer = tmodel.iter_next(tmodel.get_iter(path)) 
            if titer is None: 
                self.treeview.grab_focus()
                return True
            path = tmodel.get_path(titer) 
            move_to = columns[1] 


        if keyname == 65289:
            #Thank you Jordan!!!!!! Great hack!
            glib.timeout_add(50,
                            treeview.set_cursor,
                            path, move_to, True)
        elif keyname == 'Escape':
            pass
            
            #need to go to next widget (text buffer) from last row

    def tree_shifttab(self, treeview, path, columns, colnum, keyname):
        '''
        enable shift-tab press to reverse navigate track list
        '''
        if colnum == 2:
            move_to = columns[1]
            
        else:
            tmodel = treeview.get_model() 
            titer = tmodel.iter_next(tmodel.get_iter(path)) 
            if titer is tmodel.get_iter_first(): 
                self.treeview.grab_focus()
                return True
            path = (path[0] - 1,)
            move_to = columns[2] 
        
        if keyname == 65056:
            #Thank you Jordan!!!!!! Great hack!
            glib.timeout_add(50,
                            treeview.set_cursor,
                            path, move_to, True)
        elif keyname == 'Escape':
            pass


    def get_num_tracks():
        num_tracks  = CD.get_numtracks()
        return num_tracks

    def release_dates(self):
        '''
        get the current year and create a list of years from the 
        current one back to 1900. 

        Insert the list of years into the drop down list for selection
        '''
        self.cb_released.append_text("Don't Know")
        self.cb_released.set_active(0)
        str_date = datetime.date.today()
        int_year = str_date.year
        earliest = 1900
        while int_year >= earliest:
             str_year = str(int_year)
             self.cb_released.append_text(str_year)
             int_year -=1
        
    def get_pc_user(self):
        '''
        get the user name as (unix user, full name)
        '''
        usrid =  pwd.getpwuid(os.getuid())
        usr = (usrid.pw_name, usrid.pw_gecos)
        return usr

    def get_date(self):
        '''
        today's date as a string
        '''
        d = datetime.datetime.utcnow()
        today = d.strftime("%d/%m/%Y")
        return today
        
    def add_columns(self, treeview):
        '''
        create columns to hold the cd track information.
        second and third columns are editable
        '''
        model = treeview.get_model()
        # column ONE
        column = gtk.TreeViewColumn('No', gtk.CellRendererText(),
                                        text=0)
        column.set_sort_column_id(0)
        column.set_clickable(False)
        self.treeview.append_column(column)

        # column TWO

        editable_cell_1 = gtk.CellRendererText()
        editable_cell_1.set_property('editable', True)
        editable_cell_1.connect('edited', self.edited_cb, (model, 1) )

        column = gtk.TreeViewColumn('Title', editable_cell_1,
                                       text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        column.set_min_width(180)
        self.treeview.append_column(column)

        # column THREE
        editable_cell_2 = gtk.CellRendererText()
        editable_cell_2.set_property('editable', True)
        editable_cell_2.connect('edited', self.edited_cb, (model, 2) )

        column = gtk.TreeViewColumn('Artist', editable_cell_2,
                                       text=2)
        column.set_sort_column_id(2)
        column.set_min_width(180)
        column.set_clickable(False)
        treeview.append_column(column)
        
        #Column FOUR
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                       text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        treeview.append_column(column)
        
        #Column FIVE
        column = gtk.TreeViewColumn('Duration', gtk.CellRendererText(),
                                       text=4)
        column.set_sort_column_id(4)
        column.set_visible(False)
        
        treeview.append_column(column)        

    def edited_cb(self, cell, path, new_text, user_data):
        '''
        enable cell to be editable
        '''
        liststore, column = user_data
        liststore[path][column] = new_text
        return

    def new_track_list(self, list_details):
        '''
        populate column 1 (track number) and columnd 4 (track time) 
        using information supplied by the 'check_cd_drive' function
        '''
        model = self.treeview.get_model()     
        #clear existing rows
        model.clear()
        #add new rows
        n = 1
        for t in list_details:
             if t[0] == 1:
                 num = str(n)
                 title = ""
                 artist = ""
                 dur = t[3]
                 time = self.convert_time(dur)
                 dur = int(round(dur * 1000))
                 row = (num, title, artist, time, dur)
                 model.append(row)
                 n+=1

    def check_cd_drive(self, widget):
        '''
        determine whether the CD drive contains an audio CD. If so,
        count the number of tracks, get the length of each track, and 
        passes the details to the 'new_track_list' function
        '''
        
        empty = CD.get_empty()
        if empty:
             str_info = "the CD drive is empty"
             self.message_dialog(gtk.MESSAGE_INFO, str_info)
             return False

        #get the details  
        list_details = CD.get_all()
        
        # add details to list
        self.new_track_list(list_details)
        
        return(True)

    def check_online(self, widget):
        ''' 
        First check the music brainz database. If there is no result
        check freedb.org
        
        Return a dictionary of the CD and track information. Pass the 
        results to the 'add_info' function 
        '''
        
        check_cd = self.check_cd_drive(None)
        if not check_cd:
             return

        (dict_details, list_tracks) = self.check_musicbrainz()
        if list_tracks:
             self.add_info(dict_details, list_tracks)
        else:
             (dict_details, list_tracks) = self.check_freedb()
             if list_tracks:
                 self.add_info(dict_details, list_tracks)
             else:
                 (dict_details, list_tracks) = self.check_mbz_stub()
                 if list_tracks:
                     self.add_info(dict_details, list_tracks)

        '''
        #for testing freedb lookup
        check_cd = self.check_cd_drive(None)
        if not check_cd:
             return
        
        (dict_details, list_tracks) = self.check_freedb()
        if list_tracks:
             self.add_info(dict_details, list_tracks)
        '''
        
    def check_musicbrainz(self):
        '''
        retrieve information about the CD if available from 
        musicbrainz.
        
        return a dictionary of CD information and a list of 
        track details
        '''
        print("checking musicbrainz")
        service = mbws.WebService()
        query = mbws.Query(service)
        try:
             disc = mbdisc.readDisc()
        except mbdisc.DiscError, e:
            str_error = "Error: The Audio CD could not be read."
            self.message_dialog(gtk.MESSAGE_ERROR, str_error)
            return (None, None)

        try:
            filter = mbws.ReleaseFilter(discId=disc.getId())
            results = query.getReleases(filter)
        except mbws.WebServiceError, e:
            str_info =  "Error:", e
            self.message_dialog(gtk.MESSAGE_INFO, str_info)
            return (None, None)

        if len(results) == 0:
            return (None, None)
    

        selectedRelease = results[0].release
        
        try:
            inc = mbws.ReleaseIncludes(
                                        artist=True, 
                                        tracks=True, 
                                        releaseEvents=True
                                        )
            release = query.getReleaseById(
                                        selectedRelease.getId(), inc)
             
        except mbws.WebServiceError, e:
            print("Error:", e)
            return (None, None)
             
        except TypeError:
            print("Bailed Out")
            return (None, None)
        
        isSingleArtist = release.isSingleArtistRelease()
        
        if isSingleArtist:
            cd_artist = release.artist.name
        else:
            cd_artist = "Various"
            self.cb_compilation.set_active(2)
        cd_title = release.title
        release_date = release.getEarliestReleaseDate()
        re = release.getReleaseEvents()[0]
        country = re.country
        if country:
            try:
                country = pycountry.countries.get(alpha2=country)
                country = country.name
            except KeyError:
                pass
        company = re.label
        year = int(re.date[0:4])
        list_tracks = []
        i = 1
        for t in release.tracks:
            title = t.title
            if isSingleArtist:
                artist = ""
            else:
                artist = t.artist.name

            #(minutes, seconds) = t.getDurationSplit()
            #dur = t.duration
            track_info = (title, artist)
            list_tracks.append(track_info)
            i+=1
        dict_details = {"cd_artist": cd_artist, 
                    "cd_title" : cd_title, 
                    "company" : company, 
                    "year" : year, 
                    "country" : country,
                    "genre" : ""
                    }
        
        #print (list_tracks)

        return (dict_details, list_tracks) 
                 
    def check_freedb(self):
        '''
        retrieve information about the CD if available from freedb.
        return a dictionary of CD information and a list of track 
        details
        '''
        print("checking freedb")
        device = DiscID.open()
        try:
            disc_id = DiscID.disc_id(device)
             
        except DiscID.cdrom.error:
            str_error = "there is no CD in the drive"
            self.message_dialog(gtk.MESSAGE_ERROR, str_error)
            return (None, None)
        
        (status, info) = CDDB.query(disc_id)
        
        if not info:
            return (None, None)
        
        #if more than one result, get the first one returned

        if type(info) == list:
            info = info[0]
             
        (status, results) = CDDB.read(info['category'], info['disc_id'])

        
        #get the tracks
        list_tracks = []
        n = 0
        while n > -1:
            str_title = "TTITLE" + str(n)
            if str_title in results:        
                list_tracks.append(results[str_title])
                n += 1
            else:
                 n = -1
                 
        genre = results['DGENRE']
        year = results['DYEAR']
        artist_title = results['DTITLE']
        (artist, title) = artist_title.split(' / ')
        dict_details = {"cd_artist" : artist, 
                    "cd_title" : title, 
                    "year" : year, 
                    "company" : "",
                    "country" : "",
                    "genre" : genre
                    }
                    
        list_tracks = []
        list_titles = []
        n = 0
        while n > -1:
            str_title = "TTITLE" + str(n)
            if str_title in results:        
                list_titles.append(results[str_title])
                n += 1
            else:
                n = -1
                 
        if artist == "Various":
            self.cb_compilation.set_actice(2)
            for i in list_titles:
                (track_artist, track_title) = i.split(' / ')
                list_track.append(track_title. track_artist)
        else:
            for i in list_titles:
                list_tracks.append((i, ""))
        
        if dict_details:
            str_warning = "Unreliable online source. Please check"\
            " the details."
            self.message_dialog(gtk.MESSAGE_WARNING, str_warning)
             
        return (dict_details, list_tracks)
    
    def check_mbz_stub():
        '''
        if musicbrainz full lookup and freedb lookup fails, try mbz stub
        '''        
        print("later")
        '''
        without the extra query - works with 'stubs'
        
        rel = results[0].release
        rel.artist.name
        t0 = rel.tracks[0]
        t0.duration
        t0.title
        rel.releaseEvents
        
        
        
                     
             str_info = "No details found"
             self.message_dialog(gtk.MESSAGE_INFO, str_info)            
        
        '''
        
    def clear_entries(self, widget):
        '''
        remove all of the user added details from the interface
        '''
        model = self.treeview.get_model()     
        model.clear()        
        
        today = self.get_date()
        self.entry_arrived.set_text(today)
        

        self.entry_title.set_text("")
        self.entry_artist.set_text("")
        self.entry_company.set_text("")
        self.entry_genre.set_text("")

        self.entry_country.set_text("")
        self.sb_copies.set_value(1)
        self.cb_local.set_active(0)
        self.cb_female.set_active(0)
        self.cb_demo.set_active(0)
        self.cb_compilation.set_active(0)
        self.cb_released.set_active(0)

        bf = self.textview_comment.get_buffer()
        bf.set_text("")
        
        self.label_idcode_detail.set_text("")

    def add_info(self, dict_details, list_tracks):
        '''
        use the info from online (mbz or freedb) to populate the list 
        of tracks and the entry fields.
        '''
        
        model = self.treeview.get_model()        
        iter = model.get_iter_first()
        for track in list_tracks:
             model.set_value(iter, 1, track[0])
             model.set_value(iter, 2, track[1])
             iter = model.iter_next(iter)
        
        if dict_details["cd_title"]:
             self.entry_title.set_text(dict_details["cd_title"])
        if dict_details["cd_artist"]:
             self.entry_artist.set_text(dict_details["cd_artist"])
        if dict_details["company"]:
             self.entry_company.set_text(dict_details["company"])
        if dict_details["genre"]:
             self.entry_genre.set_text(dict_details["genre"])
        if dict_details["country"]:
             self.entry_country.set_text(dict_details["country"])
        
        if dict_details["year"]:
             rel_yr = int(dict_details["year"])
             str_date = datetime.date.today()
             int_year = str_date.year
             try:
                 index = int_year - rel_yr
                 self.cb_released.set_active(index)
             except TypeError:
                 pass

    def check_dup(self, widget):
        '''
        Check the database to see if the CD has been catalogued
    
        '''
        cdtitle = self.entry_title.get_text()
        cdartist = self.entry_artist.get_text()
        
        if (cdtitle and cdartist):
            idcode = self.check_catalogue(cdtitle, cdartist)
            idcode = str(idcode)
            self.label_idcode_detail.set_text(idcode)
            
        else:            
            str_error = "You need to enter a Title and Artist before"\
                        " checking the catalogue for duplicates"
            self.message_dialog(gtk.MESSAGE_ERROR, str_error)
            idcode = ""
            
        return idcode

    def set_idcode(self, widget):
        '''
        start the dialog to manually enter the ID code for the CD.
        '''
        idcode = self.enter_idcode()
        if idcode:
            self.clear_entries(None)
            self.label_idcode_detail.set_text(idcode)
            
        else:
            self.label_idcode_detail.set_text("")
                    
    def enter_idcode(self):
        '''
        enter an idcode manually 
        '''
        str_head = "ID Code"
        dialog = gtk.Dialog(
             str_head, None, 0, 
             (gtk.STOCK_OK, gtk.RESPONSE_OK,  
             gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
             ) 
        #dialog.set_default_size(400, 300)

        
        label_idcode = gtk.Label("Enter the ID Code")
        self.entry_idcode = gtk.Entry(7)
        self.entry_idcode.set_activates_default(True)

        dialog.set_default(self.entry_idcode)
        dialog.set_default_response(gtk.RESPONSE_OK)
                
        dialog.vbox.pack_start(label_idcode, True, True, 5)
        dialog.vbox.pack_start(self.entry_idcode, True, True, 5)
        
        #self.confirm_idcode(idcode)
        
        dialog.show_all()
        response = dialog.run()    
        
        if response == gtk.RESPONSE_OK:
            idcode = self.entry_idcode.get_text()
            if idcode:
                try: 
                    int_idcode = int(idcode)

                except ValueError:
                    str_error = "Unable to check the code, "\
                                "make sure you enter a number"
                    self.message_dialog(gtk.MESSAGE_ERROR, str_error)
                    idcode = ""
                    dialog.destroy()
                    return idcode
                
              
                cd_details = self.idcode_details(idcode)
                if not cd_details:
                    str_error = "Unable to find a CD "\
                                "catalogued with this code"
                    self.message_dialog(gtk.MESSAGE_ERROR, str_error)
                    idcode = ""
                    dialog.destroy()  
                    return idcode
                    
                confirm = self.idcode_details_dialog(cd_details)
                
                if not confirm:
                    idcode = ""
                    dialog.destroy()                    
                    return idcode
                          
                else:
                    idcode = int(idcode)
                    idcode = "%07d" %idcode
                    dialog.destroy()
                    return idcode
            else:
                str_error = "you did not enter anything"
                self.message_dialog(gtk.MESSAGE_ERROR, str_error)
                idcode = ""
                dialog.destroy()
                return idcode
                
        elif response == gtk.RESPONSE_CANCEL:
            idcode = ""
            dialog.destroy()
            return idcode

    def idcode_details(self, idcode):
        '''
        query the database with the idcode and return details 
        about the CD
        '''
        conn = self.pg_connect_cat()
        cur = conn.cursor()
        
        SQL = "SELECT cd.title, cd.artist, "\
              "cdtrack.tracktitle, cdtrack.tracknum "\
              "FROM cdtrack INNER JOIN cd ON cdtrack.cdid=cd.id "\
              "WHERE cd.id = " + idcode + " ORDER BY cdtrack.tracknum"
        
        cur.execute(SQL)
        cd_details = cur.fetchall()
        return cd_details
                
    def idcode_details_dialog(self, cd_details):
        '''
        display the details of a CD and confirm that they are correct
        '''
        str_head = "Confirm"
        dialog = gtk.Dialog(
             str_head, None, 0, 
             ("C_onfirm", gtk.RESPONSE_OK,  
             gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
             )
        dialog.set_size_request(400, 600)
        dialog.set_default_response(gtk.RESPONSE_OK)
        
        model = gtk.ListStore(str, str)
                     
        title = cd_details[0][0]
        artist = cd_details[0][1]
        
        label_title = gtk.Label(title)
        label_artist = gtk.Label(artist)
        
        sw_dialog = gtk.ScrolledWindow()
        sw_dialog.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_dialog.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

 
        for item in cd_details:
            track_title = item[2]
            track_no = item[3]
            track_no = str(track_no)
             
            model.append([track_no, track_title])
            
        self.treeview_dialog = gtk.TreeView(model)
        self.create_idcode_dialog_columns(self.treeview_dialog)            

        sw_dialog.add(self.treeview_dialog)
        dialog.vbox.pack_start(label_title, False, True, 0)
        dialog.vbox.pack_start(label_artist, False, True, 0)
        dialog.vbox.pack_start(sw_dialog, True, True, 0)   
        
        dialog.show_all()
        response = dialog.run()        
        
        if response == gtk.RESPONSE_OK:
            confirm = True
        elif response == gtk.RESPONSE_CANCEL:
            confirm = False
        dialog.destroy()
        
        return confirm

    def create_idcode_dialog_columns(self, treeview):
        '''
        create the columns that display the cds and tracks
        '''
        rendererText = gtk.CellRendererText()
        column = gtk.TreeViewColumn(None, rendererText, text=0)
        column.set_sort_column_id(0)    
        column.set_clickable(False)
        treeview.append_column(column)
        
        rendererText = gtk.CellRendererText()
        column = gtk.TreeViewColumn(None, rendererText, text=1)
        column.set_sort_column_id(1)    
        column.set_clickable(False)
        treeview.append_column(column)
        
    def rip(self, widget):
        '''    
        check if there is anything in the idcode label
        if not: 
        run the 'check catalogue' dialogue and exit this function
        
        If the idcode label = 'None':
        check if all required fields have been filled out
            if not, error message and exit this function
            if correct:
            add details to catalogue and get idcode, add comment
            rip as below
        If there is a number in the idcode label:
            rip as below:
        
        Rip
        create a folder named after the idcode
         (error message and exit if fails)
        run the 'Messages' class to rip and show progress
        rename the files idcode-trackno
        clear details
        eject
        success message (with timeout)
        '''
        
        idcode = self.label_idcode_detail.get_text()
        
        if not idcode:
            str_error = 'You have not checked the catalogue'
            self.message_dialog(gtk.MESSAGE_ERROR, str_error)
            return


        
        (cd_data, tracks) = self.get_data()
        
        if idcode == "Checked":
            if not self.check_data(cd_data, tracks):
                return
            else:
                idcode = self.insert_data(cd_data, tracks)
                idcode = "%07d" %idcode
            
        else:
            if self.check_files(idcode):
                str_error = 'This CD has already been ripped'
                self.message_dialog(gtk.MESSAGE_ERROR, str_error)
                return
                    
        comment = self.get_comment()
        if comment:
            self.query_comment(comment, cd_data, idcode)

        #create the ripping directory (named idcode)        
        destination = '{0}/{1}/'.format(dir_wav, idcode)
        
        print ("creating directory {0}".format(idcode))
        
        if not os.path.exists(destination):
            try:
                 os.mkdir(destination)
                 print('created directory')
            except OSError:
                 print("unable to create directory")
                 str_error = '''ERROR
                 
    Unable to create a destination folder. 
    If this problem persists restart 
    the computer and try again. 

    If it still fails, contact station tech support.'''
                 self.message_dialog(gtk.MESSAGE_ERROR, str_error)
                 return
                 
        else:
            pass

        #gtk dialog with vte to run rip command and show progress
        show_progress = Progress(destination)
        show_progress    
        
        #change track names from the cdparanoia default to idcode-n
        self.rename_tracks(idcode)
        
        self.eject(None)
        
        str_info = "Ripping Completed"
        self.message_dialog(gtk.MESSAGE_INFO, str_info)
        return

    def get_data(self):
        '''
        get the entry and ccombobox information 
        to enter into the database
        '''
        cdtitle = self.entry_title.get_text()
        cdartist = self.entry_artist.get_text()
        company = self.entry_company.get_text()
        genre = self.entry_genre.get_text()
        cpa = self.entry_country.get_text()
        copies = self.sb_copies.get_value_as_int()
        #copies = str(copies)
        local = self.cb_local.get_active()
        #local = str(local)
        female = self.cb_female.get_active()
        #female = str(female)
        demo = self.cb_demo.get_active()
        #demo = str(demo)
        compilation = self.cb_compilation.get_active()
        #compilation = str(compilation)
        year = self.cb_released.get_active_text()
        try:
            year = int(year)
        except ValueError:
            year = 0
        #comment = self.get_comment()
        arrivaldate = self.get_arrived()
        pc_user = self.get_pc_user()
        user = self.get_db_user(pc_user)
        today = self.get_unixtime()
        #today = str(today)
        
        tracks = self.get_track_data()
        
        cd_data = {
                     'artist' : cdartist,
                     'title' : cdtitle,
                     'year' : year,
                     'genre' : genre,
                     'company' : company,
                     'cpa' : cpa,
                     'arrivaldate' : arrivaldate,
                     'copies' : copies,
                     'compilation' : compilation,
                     'demo' : demo,
                     'local' : local,
                     'female' : female,
                     'createwho': user,
                     'createwhen' : today,
                     'modifywho' : user,
                     'modifywhen' : today,
                     #'comment' : comment,
                     'status' : '0',
                     'format' : '1'
                     }

        
        return cd_data, tracks

    def check_data(self, cd_data, tracks):
        '''
        - ensure that all necessary information is added before ripping
        - display error message for any (first) missing entry 
          encountered
        '''
        checklist_cd = (
             'title',
             'artist',
              )
             
        dict_error = {
             'title' : "the title of the CD",
             'artist' : "the CD artist (or 'Various' for a compilation)",
            }

                 
        for item in checklist_cd:
             i = cd_data[item]
             if not i:
                 str_error = "You need to enter " + dict_error[item]
                 self.message_dialog(gtk.MESSAGE_ERROR, str_error)
                 return False

        
        if not tracks:
             str_error = "You need to enter the track details"
             return False
        
        for track in tracks:
             if not track[1]:
                 n = track[0]
                 n = str(n)
                 str_error = "What is the title of track {0}?".format(n)
                 self.message_dialog(gtk.MESSAGE_ERROR, str_error)
                 return False
        
             if cd_data ['artist'] == 'Various':
                 if not track[2]:
                     n = track[0]
                     n = str(n)
                     str_error = "Who is the artist "\
                     "on track {0}?".format(n)
                     self.message_dialog(gtk.MESSAGE_ERROR, str_error)
                     return False
             
        return True
             
    def get_track_data(self):
        '''
        retrieve the track information from the list
        '''
        track_data = []
        model = self.treeview.get_model()
        iter = model.get_iter_first()
        while iter:
             track_info = model.get(iter, 0, 1, 2, 4)
             track_data.append(track_info)
             iter = model.iter_next(iter)
        return track_data
             
    def get_comment(self):
        '''
        retrieve the text from the comment buffer
        '''
        textbuffer = self.textview_comment.get_buffer()
        iter_start = textbuffer.get_start_iter()
        iter_end = textbuffer.get_end_iter()
        comment = textbuffer.get_text(iter_start, iter_end, False)
        return comment

    def get_arrived(self):
        '''
        retrieve the 'arrived' date
        '''
        arrived = self.entry_arrived.get_text()

        return arrived

    def check_catalogue(self, cdtitle, cdartist):
        '''
        use a 'fuzzy' query on title and artist to see if the cd exists 
        in the database.
        if it exists, return the idcode and check if the files exist
        return boolean for files existing or not
        if the cdtitle does not exist return None
        '''
        cdtitle = cdtitle.replace("'", "")
        cdartist = cdartist.replace("'", "")
        
        conn = self.pg_connect_cat()
        str_select = "SELECT cd.title, cd.artist, cdtrack.tracktitle, cd.id, "\
        "similarity(cd.title, '{0}') as sml1,  similarity(cd.artist, "\
        "'{1}') as sml2 ".format(cdtitle, cdartist)
        str_from = "FROM cdtrack INNER JOIN cd on cdtrack.cdid=cd.id "
        str_where = "where cd.title % '{0}' or cd.artist % '{1}' "\
        "order by sml1 desc, sml2 desc, cd.id, "\
        "cdtrack.tracknum ".format(cdtitle, cdartist)
        str_limit = "limit 60"
        
        query = str_select + str_from + str_where + str_limit
        #print(query)
        
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        
        #if fuzzy search returns result(s), dialog for user confirmation
        #to get the idcode of the cd if it is a duplicate
        #and check if the mp3 files exist
        
        if result:
            idcode = self.check_title(result)

        else:
            idcode = "Checked"
            str_info = "No likely duplicates were found"
            self.message_dialog(gtk.MESSAGE_INFO, str_info)             
             
                          
        return idcode

    #____________Start 'Check Duplicates' Dialogue Section_____________
                 
    def check_title (self, result):    
        '''
        Display CDs in the catalogue with similar titles and artist 
        to the one about to be ripped.
        Wait for user confirmation if CD is the same or not
        '''
        str_head = "Checking CD in Catalogue"
        dialog = gtk.Dialog(
             str_head, None, 0, 
             ("C_onfirm", gtk.RESPONSE_OK,  
             gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
             )  
        dialog.set_response_sensitive(gtk.RESPONSE_OK, False)
        dialog.set_default_size(500, 600)
        dialog.set_default_response(123)
        
        sw_dialog = gtk.ScrolledWindow()
        sw_dialog.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_dialog.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        
        str_dialog = '''        
    Checking The Catalogue
    
    Is the CD you are going to rip listed here?
    
    Click Confirm if it is listed in the catalogue
    
        '''
        label_dialog = gtk.Label(str_dialog)
        
        store = self.create_dialog_model(result)
        self.treeview_dialog = gtk.TreeView(store)

        self.create_dialog_columns(self.treeview_dialog)
        treeselection = self.treeview_dialog.get_selection()
        treeselection.connect("changed", self.set_OK_sensitive, dialog)
          
        sw_dialog.add(self.treeview_dialog)
        dialog.vbox.pack_start(label_dialog, False, True, 0)
        dialog.vbox.pack_start(sw_dialog, True, True, 0)

        idcode = ""
        
        dialog.show_all()
        response = dialog.run()

        if response == gtk.RESPONSE_OK:
             idcode = self.get_code()
        elif response == gtk.RESPONSE_CLOSE:
            idcode = "Checked"
        
        dialog.destroy()
        return idcode

    def create_dialog_model(self, result):
        '''
        This populates the list of cds and tracks that is displayed 
        using the results of the database query
        '''
        model = gtk.TreeStore(str, str, str)
        #cdtitle, cdartist, track_title, cd_idcode
        var_cd_code = ""
        for item in result:
             cd_title = item[0]
             cd_artist = item[1]
             track_title = item[2]
             cd_code = (item[3])
             cd_code = "%07d" %cd_code
             
             if not cd_title:
                 cd_title = "(No Title)"

             if not cd_code == var_cd_code:                 
                 n = model.append(None, [cd_title, cd_artist, cd_code])
                 model.append(n, [track_title, None, cd_code])
             else:
                 model.append(n, [track_title, None, cd_code])
             var_cd_code = cd_code
        return model

    def create_dialog_columns(self, treeview):
        '''
        create the columns that display the cds and tracks
        '''
        rendererText = gtk.CellRendererText()
        column = gtk.TreeViewColumn("CD Title", rendererText, text=0)
        column.set_sort_column_id(0)    
        column.set_clickable(False)
        treeview.append_column(column)
        
        rendererText = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Artist", rendererText, text=1)
        column.set_sort_column_id(1)    
        column.set_clickable(False)
        treeview.append_column(column)
        
        rendererText = gtk.CellRendererText()
        column = gtk.TreeViewColumn("ID", rendererText, text=2)
        column.set_sort_column_id(2)
        column.set_visible(False)
        treeview.append_column(column)

    def set_OK_sensitive(self, widget, dialog):
        dialog.set_response_sensitive(gtk.RESPONSE_OK, True)
        
    def get_code(self):
        '''
        get the cd id code from third column of the selected row
        '''
        treeselection = self.treeview_dialog.get_selection()
        (model, iter) = treeselection.get_selected()
        if iter:
             idcode = model.get(iter, 2)
             idcode = idcode[0]
             return idcode
             
    #____________End 'Check Duplicates' Dialogue Section_____________

    def check_files(self, idcode):
        '''
        check if ripped audio files exist
        '''        
        print("checking paths")
        mp3_path_hi = dir_mus + "/hi/" + idcode
        mp3_path_lo = dir_mus + "/lo/" + idcode


        
        if (os.path.isdir(mp3_path_hi) and os.path.isdir(mp3_path_lo)):            
            files = True
        else:
            files = False
        return files
        
    def insert_data(self, cd_data, tracks):
        '''
        Call queries which add the info to the database.
        Return the cd id code
        '''
        idcode = self.query_cd(cd_data)
        self.query_tracks(idcode, tracks)

        return idcode
        
    def query_cd(self, cd_data):
        '''
        Insert cd data into the database and return the cd id code
        '''
        
        conn = self.pg_connect_cat()
        cur = conn.cursor()
        
        str_ins = "INSERT INTO cd "
        str_val = " VALUES "
        str_ret = " RETURNING id "
        
        col_items = str(tuple(cd_data.keys()))
        col_items = col_items.replace("'", "")
        val_items = tuple(cd_data.values())
        
        print(val_items)
        
        SQL = "INSERT INTO cd " +  col_items + \
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, "\
        "%s, %s, %s, %s, %s, %s, %s, %s, %s)  RETURNING id"
        cur.execute(SQL, val_items) 
            
        conn.commit()
        idcode = cur.fetchall()
        cur.close()
        conn.close()
                
        #idcode = '34345'
        idcode = idcode[0][0]        
        return idcode

    def query_tracks(self, idcode, tracks):
        '''
        insert cd track information into the database
        '''
        conn = self.pg_connect_cat()
        cur = conn.cursor()
        
        for track in tracks:
            num = track[0]
            title = track[1]
            artist = track[2]
            dur = track[3]
            dur = dur/1000

            val_items = (
                idcode,
                num,
                title,
                artist,
                dur
                )

            SQL = "INSERT INTO cdtrack (cdid, tracknum, tracktitle, "\
            "trackartist, tracklength) VALUES (%s, %s, %s, %s, %s)"
            cur.execute(SQL, val_items)
            conn.commit()

        cur.close()
        conn.close()
    
    def query_comment(self, comment, cd_data, idcode):
        '''
        insert the comment into the cdcomment table
        use the idcode, user and date from cd_data
        '''
        conn = self.pg_connect_cat()
        cur = conn.cursor() 
        
        cdtrackid = 0
        createwho = cd_data['createwho']
        createwhen = cd_data['createwhen']
        modifywho = createwho
        modifywhen = createwhen
        
        
        val_items = (
                    idcode, 
                    cdtrackid, 
                    comment, 
                    createwho, 
                    createwhen, 
                    modifywho, 
                    modifywhen
                    )
        
        SQL = "INSERT INTO cdcomment (cdid, cdtrackid, comment, createwho, "\
        "createwhen, modifywho, modifywhen) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        cur.execute(SQL, val_items) 
            
        conn.commit()   
        cur.close()
        conn.close()        

    def rename_tracks(self, idcode):
        '''
        rename the tracks ripped from the cd to idcode-n where n is the 
        track number
        '''
        #idcode = str(idcode)
        cwd = os.getcwd()
        ripdir  = '{0}/{1}/'.format(dir_wav, idcode)
        
        os.chdir(ripdir)
        
        files = os.listdir('./')
        if files:
             for tr in files:
                 if tr[-8:] == 'cdda.wav' and tr[:5] == 'track':
                     n=(tr[5:7])
                     tr_new = idcode + '-' + n + '.wav'
                     os.rename(tr, tr_new)
        
        os.chdir(cwd) 
        
    def eject(self, widget):
        '''
        use pygame tp eject the CD. If it fails, call linux eject
        '''
        self.clear_entries(None)
        try:
            CD.eject()
        except pygame.error:
            self.subprocess_eject()
        except OSError:
            self.subprocess_eject()
     
    def subprocess_eject(self):
        '''
        use the linux eject command if pygame eject fails
        '''
        try:
             subprocess.check_call("eject")
        except subprocess.CalledProcessError:
             try: 
                 subprocess.check_call("/usr/bin/eject -i off")
                 subprocess.check_call("/usr/bin/eject")
             except subprocess.CalledProcessError:
                 str_error = "Oh No! - I can't eject the CD!"
                 self.message_dialog(gtk.MESSAGE_ERROR, str_error)       
                     
    def get_unixtime(self):
        d = datetime.datetime.utcnow()
        unixtime = calendar.timegm(d.utctimetuple())
        return unixtime

    def get_db_user(self, pc_user):
        '''
        check the user name of the pc login name (or first 
        and last name details) against the user
        list in the database to get the ID number. 
        If there is no match return 1.
        '''
        username = pc_user[0]
        full = pc_user[1]
        full = full.strip(',')
        full = full.split(' ')
        first = full[0]
        
        try:
            last = full[1]
        except IndexError:
            last = ""
                
        conn = self.pg_connect_cat()
        cur = conn.cursor()
        
        str_sel     = "SELECT id FROM users WHERE username = '"
        str_or = "' OR (first = '"
        str_and = "' AND last = '"

        query = str_sel + username + str_or + first + str_and + last + "')"
        
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close() 
        
        if not result:
            result = 1
        else:
            result = result[0][0]
        return result    

    def convert_time(self, dur):
        '''
        convert time from seconds to h:m:s
        '''
        
        m,s = divmod(dur, 60)
        if m < 60:
             str_dur = "%02i:%02i" %(m,s)
             return str_dur
        else:
             h,m = divmod(m, 60)
             str_dur = "%i:%02i:%02i" %(h,m,s)
             return str_dur  

    def message_dialog(self, dialog_type, string):
        '''
        display message according to type and text string
        '''
        messagedialog = gtk.MessageDialog(None, 0, 
                     dialog_type, gtk.BUTTONS_OK, 
                     string)
        messagedialog.run()
        messagedialog.destroy() 
          
    def pg_connect_cat(self):
        '''
        create a psycopg2 connection to the postgresql music catalogue database
        '''
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format(
             pg_cat_database, pg_user, pg_server, pg_password)
        conn = psycopg2.connect(conn_string)
        #cur = conn.cursor()
        return conn

       
Ripper()
gtk.main()
        

