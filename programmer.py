#!/usr/bin/python

#programmer.py
# tool for configuring program timetable

import pygtk
import gtk
import gobject
import psycopg2
import time
import pango
import ConfigParser
import datetime
from psycopg2 import sql
import psycopg2.extras

config = ConfigParser.SafeConfigParser()
config.read('/usr/local/etc/threedradio.conf')

dir_img = config.get('Paths', 'dir_img')
logo = config.get('Images', 'logo')

pg_user = config.get('Programmer', 'pg_user')
pg_password = config.get('Programmer', 'pg_password')
pg_server = config.get('Common', 'pg_server')
pg_msg_database = config.get('Common', 'pg_msg_database')


tup_day = ( "Sunday",
            "Monday", 
            "Tuesday", 
            "Wednesday", 
            "Thursday", 
            "Friday", 
            "Saturday")


class EditProgramme():
    def __init__(self, prg_info):
        dialog = gtk.Dialog("Edit Programme", None, 0, (
            gtk.STOCK_SAVE, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        self.programmer = Programmer()
        self.prg_info = prg_info

        table = gtk.Table(6, 2, False)

        gtk.Table(8, 2, False)
        
        label_code = gtk.Label("Code")
        label_name = gtk.Label("Name")
        label_day = gtk.Label("Day")
        label_start = gtk.Label("Start Time")
        label_presenters = gtk.Label("Presenters")
        label_description = gtk.Label("Description")


        dialog.vbox.pack_start(table, True, True, 0)
        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self.update_programme(None)       
        dialog.destroy()

    def update_programme(self, widget):
        print self.prg_info

class Programmer():
    def __init__(self):
        '''
        Set up the main window and graphical elements
        '''
        print("make window")
        window = gtk.Window()
        window.set_title("Programmer")
        window.set_position(gtk.WIN_POS_CENTER)
        filepath_logo = dir_img + logo
        window.set_icon_from_file(filepath_logo)
        window.connect("destroy", gtk.main_quit)
        
        # Boxes and scrolled windows
        vbox = gtk.VBox(False, 0)
        hbox = gtk.HBox(False, 0)
        sw = gtk.ScrolledWindow()
        sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        sw.set_size_request(200, 300)
        
        # drop down day selection
        self.cb = gtk.combo_box_new_text()
        self.cb_setup()

        # buttons
        btn_info = gtk.Button(stock=gtk.STOCK_INFO)
        btn_edit = gtk.Button(stock=gtk.STOCK_EDIT)
        btn_add = gtk.Button(stock=gtk.STOCK_ADD)
        btn_del = gtk.Button(stock=gtk.STOCK_DELETE)
        
        #make the list
        store = gtk.ListStore(str, str)         
        self.treeview = gtk.TreeView(store)
        self.treeview.set_rules_hint(True)
        self.make_columns(self.treeview)

        self.show_programmes(self.cb)

        # connect signals and events
        self.cb.connect("changed", self.show_programmes)
        btn_info.connect("clicked", self.dialog_info)
        btn_edit.connect("clicked", self.dialog_edit)
        btn_add.connect("clicked", self.dialog_add)
        btn_del.connect("clicked", self.dialog_delete)
        
        # pack the gui
        hbox.pack_start(self.cb, False, False, 5)
        hbox.pack_end(btn_del, False, False, 5)
        hbox.pack_end(btn_add, False, False, 5)
        hbox.pack_end(btn_edit, False, False, 5)
        hbox.pack_end(btn_info, False, False, 5)
        
        vbox.pack_start(hbox, False, False, 5)
        vbox.pack_start(sw)
        sw.add(self.treeview)
        window.add(vbox)
        window.show_all()


    def cb_setup(self):
        '''
        Populate the drop down list with days of the week
        Set the active day as today (-6 hours for 6am start of day)
        '''
        for day in tup_day:
            self.cb.append_text(day)
        now = datetime.datetime.now()
        delta = datetime.timedelta(hours=-6)
        day = now + delta
        index = int(day.strftime("%w"))
        self.cb.set_active(index)


    def make_columns(self, treeview):
        '''
        Two columns to display the days programmes
        '''
        # column ONE
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                     text=0)
        column.set_sort_column_id(0)
        treeview.append_column(column)

        # column TWO
        column = gtk.TreeViewColumn('Title', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)        
        treeview.append_column(column)

    def dialog_info(self, widget):
        '''
        Open a dialog window with details for the selected programme
        '''
        print("info button clicked")
    
    def dialog_edit(self, widget):
        '''
        Open a dialog window to enable editing of the selected programme
        '''
        print("edit button clicked")
        prg_info = "stuff"
        edit_programme = EditProgramme(prg_info)
        edit_programme
        self.show_programmes(self.cb)


    def dialog_add(self, widget):
        '''
        Open a dialogue window to add a new programme
        '''
        print("add button clicked")

    def dialog_delete(self, widget):
        '''
        Open a confirm message and delete the selected programme
        '''
        print("delete button clicked")

    def show_programmes(self, widget):
        '''
        Get the selected day of the week from the drop down list
        Populate the programme list from the selected day
        '''
        day = widget.get_active_text()
        db, query, search_terms = self.get_programmes_query(day)
        result = self.execute_query(db, query, search_terms)
        programmes = [{k:v for k, v in record.items()} for record in result]
        self.populate_list(programmes)

    def get_programmes_query(self, day):
        '''
        Create a query for retreiving the selected day's programmes
        '''
        day_int = tup_day.index(day)
        if day_int==6:
            next_day = tup_day[0]
        else:
            next_day = tup_day[day_int+1]

        search_terms = (day, next_day)    
        select_statement =  sql.SQL("SELECT * FROM programmes")
        where_statement = sql.SQL ("WHERE day = %s AND start >= '6:00'")
        or_statement = sql.SQL(" OR day = %s AND start < '06:00'")
        order_statement = sql.SQL("ORDER BY start")
        query = sql.SQL(' ').join([
            select_statement, 
            where_statement, 
            or_statement,
            order_statement
            ])
        
        db = 'msglist'
        
        return (db, query, search_terms)

    def execute_query(self, db, query, search_terms):
        '''
        execute the provided query against the specified database
        '''
        if db == 'msglist':
            conn = self.pg_connect_msg()
        
        else:
            return
        
        # show the query for debugging
        #query_string = query.as_string(conn)
        #print(query_string)

        dict_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        dict_cur.execute(query, (search_terms))
        programmes = dict_cur.fetchall()
        
        dict_cur.close()
        conn.close()  
        return programmes

    def populate_list(self, programmes):
        '''
        Populate the list store with programme details
        '''
        model = self.treeview.get_model()
        six_am = datetime.time(6)

        for programme in programmes:
            start = programme['start']
            if start >= six_am:
                start = start.strftime("%H:%M")
                name = programme['name']
                model.append((start, name))
        
        for programme in programmes:
            start = programme['start']
            if start < six_am:
                start = start.strftime("%H:%M")
                name = programme['name']
                model.append((start, name))

    def pg_connect_msg(self):
        '''
        connect to the message database
        '''
        #connection variables
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            pg_msg_database, pg_user, pg_server, pg_password)
        conn = psycopg2.connect(conn_string)
        #cur = conn.cursor()
        return conn

Programmer()
gtk.main()
