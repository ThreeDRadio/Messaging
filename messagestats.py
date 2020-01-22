#!/opt/local/bin/python2.7
# messagestats.py
# display information about when messages have been scheduled and played

import datetime
import os
import operator
import csv
import psycopg2
import pygtk
import gtk
import pango
import ConfigParser
from psycopg2 import extras


config = ConfigParser.SafeConfigParser()
config.read('/usr/local/etc/threedradio.conf')

dir_img = config.get('Paths', 'dir_img')
logo = config.get('Images', 'logo')
pg_user = config.get('ThreeDPlayer', 'pg_msg_user')
pg_password = config.get('ThreeDPlayer', 'pg_msg_password')
pg_server = config.get('Common', 'pg_server')
pg_msg_database = config.get('Common', 'pg_msg_database')


class Stats(gtk.Window):
   
    def __init__(self, parent=None):
        # create window and containers
        gtk.Window.__init__(self)
        try:
            self.set_screen(parent.get_screen())
        except AttributeError:
            self.connect('destroy', lambda *w: gtk.main_quit())
        self.set_title("Message Statistics")
        self.set_position(gtk.WIN_POS_CENTER)
        filepath_logo = dir_img + logo
        self.set_icon_from_file(filepath_logo)
        self.connect("destroy", gtk.main_quit)

        hbox_main = gtk.HBox(False, 0)
        vbox = gtk.VBox(False, 0)
        hbox_btn = gtk.HBox(False, 0)
        sw = gtk.ScrolledWindow()
        sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)

        #message type selection
        label_type = gtk.Label("Message Type")
        self.cb_msgtype = gtk.combo_box_new_text()
        self.cb_msgtype.append_text('All')
        
        list_msgtype = self.message_types()
        for item in list_msgtype:
            self.cb_msgtype.append_text(item)
        
        self.cb_msgtype.set_active(0)
        
        #message selection
        label_sel = gtk.Label("Message")
        self.cb_msg = gtk.combo_box_new_text()
        self.cb_msg.append_text('All')
        self.cb_msg.set_active(0)

        self.cb_msgtype.connect('changed', self.type_selected)
        
        hseparator0 = gtk.HSeparator()

        self.cb_timeframe = gtk.combo_box_new_text()
        list_timeframes = [
            'Last Hour',
            'Last Day',
            'Last Week',
            'Last 4 Weeks',
            'Last Year'           
            ]
       
        for item in list_timeframes:
            self.cb_timeframe.append_text(item)
        
        self.cb_timeframe.set_active(2)
        self.cb_timeframe.connect('changed', self.set_timeframe)
        
        self.entry0 = gtk.Entry()
        self.entry1 = gtk.Entry()
        self.set_timeframe(None)
        
        hseparator1 = gtk.HSeparator()

        # buttons - Show Save Quit
        
        hbox_btn = gtk.HBox()

        btn0 = gtk.Button('Stats')
        btn0.connect("clicked", self.show_stats)
        btn1 = gtk.Button('Save')
        btn1.connect("clicked", self.save_stats)
        btn2 = gtk.Button('Quit')
        btn2.connect("clicked", self.quit_program)
        
        self.store = gtk.ListStore(str ,str, str, str)         
        self.treeview = gtk.TreeView(self.store)
        self.treeview.set_rules_hint(True)        
        self.make_columns(self.treeview)
        self.list1 = []

        #pack the gui
        vbox.pack_start(label_type, False)
        vbox.pack_start(self.cb_msgtype, False)
        vbox.pack_start(label_sel, False)
        vbox.pack_start(self.cb_msg, False)        
        vbox.pack_start(hseparator0, False, True, 5)
        vbox.pack_start(self.cb_timeframe, False)        
        vbox.pack_start(self.entry0, False)
        vbox.pack_start(self.entry1, False)        
        vbox.pack_start(hseparator1, False, True, 5)
                
        vbox.pack_start(hbox_btn, False)
        hbox_btn.pack_start(btn0, False)
        hbox_btn.pack_start(btn1, False)
        hbox_btn.pack_start(btn2, False)

        hbox_main.pack_start(vbox, False)
        sw.add(self.treeview)
        hbox_main.pack_end(sw, True)
        self.add(hbox_main)
        self.show_all()

        
    def message_types(self):
        '''
        Get the message types for populating the drop down  
        list of message types
        '''
        list_msgtypes = []
        #query =  "SELECT type FROM typelist WHERE scheduled = TRUE ORDER BY type"
        query =  "SELECT type FROM typelist ORDER BY type"
        msg_types = self.result_query(query)
        for item in msg_types:
            list_msgtypes.append(item[0])
        return list_msgtypes
    
    def all_messages(self, entry):
        '''
        Get a list of messages of the selected type.
        '''
        today = datetime.date.today()
        msg_type = entry.get_active_text()
        list_msg = []
        conn = self.pg_connect()
        cur = conn.cursor()
        query =  """SELECT code,title FROM messagelist 
        WHERE LOWER(type)=LOWER('%s') 
        ORDER BY code""" %(msg_type)
        cur.execute(query)
        msg_list = cur.fetchall()
        cur.close()
        conn.close()
        for item in msg_list:
            list_msg.append(item[0] + ", " + item[1])
        return list_msg
          
    def type_selected(self, entry):
        '''
        populate the messages drop down list once the message type has 
        been selected 
        '''
        self.cb_msg.get_model().clear()
        self.cb_msg.append_text('All')
        if entry != 'All':
            list_msg = self.all_messages(entry)
            for item in list_msg:
                self.cb_msg.append_text(item)
            
            self.cb_msg.set_active(0)

    def set_timeframe(self, widget):
        print("get timeframe")
        time_span = self.cb_timeframe.get_active()        
        print(str(time_span))
        if time_span == 0:
            # hour
            delta = datetime.timedelta(hours = 1)
        elif time_span ==1:
            # day
            delta = datetime.timedelta(days = 1)
        elif time_span ==2:
            # week
            delta = datetime.timedelta(days = 7)
        elif time_span ==3: 
            # 4 weeks
            delta = datetime.timedelta(days = 30)
        elif time_span ==4: 
            # year
            delta = datetime.timedelta(days = 365)


        now = datetime.datetime.now()
        then = now - delta
        time_from = then.strftime("%Y-%m-%d %H:%M")
        time_to = now.strftime("%Y-%m-%d %H:%M")        
        self.entry0.set_text(time_from)
        self.entry1.set_text(time_to)

    def get_timeframe(self):
        str_from = self.entry0.get_text()
        str_to = self.entry1.get_text()
        try:
            time_from = datetime.datetime.strptime(str_from, "%Y-%m-%d %H:%M")
            time_to = datetime.datetime.strptime(str_to, "%Y-%m-%d %H:%M")
        except ValueError:
            message = """you need to have the time and date in the format: yyyy-mm-dd hh:mm 
            for example 2018-02-16 13:25"""
            self.error_message(message)
        return (time_from, time_to)
        
    def make_columns(self, treeview):
        '''
        Create the columns that are to be used for the list that 
        displays when messages were scheduled and played.
        '''
        column = gtk.TreeViewColumn('ID Code', gtk.CellRendererText(),
                                     text=0)
        column.set_sort_column_id(0)
        column.set_clickable(True)
        self.treeview.append_column(column)
        
        column = gtk.TreeViewColumn('Scheduled', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(True)
        self.treeview.append_column(column) 

        column = gtk.TreeViewColumn('Played', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(True)
        self.treeview.append_column(column)
        
        column = gtk.TreeViewColumn('computer', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(True)
        self.treeview.append_column(column)
        
    def show_stats(self, clicked):
        self.store.clear()
        (time_from, time_to) = self.get_timeframe()
        msg_type = self.cb_msgtype.get_active_text()
        str_msg = self.cb_msg.get_active_text()       
        
        if msg_type == 'All':
            sch_query = """SELECT msg_code AS code, time_date AS scheduled_time FROM schedule 
            WHERE time_date BETWEEN SYMMETRIC '%s' AND '%s' 
            """ % (time_from, time_to)
            
            log_query = """SELECT id_code AS code, when_played AS played_time, hostname AS computer FROM playlog 
            WHERE when_played BETWEEN SYMMETRIC '%s' AND '%s' 
            AND playlog.id_type = 'msg'
            """ % (time_from, time_to)

        else:                
            if str_msg == 'All':
                sch_query = """SELECT msg_code AS code, time_date AS scheduled_time FROM schedule 
                JOIN messagelist ON schedule.msg_code = messagelist.code 
                WHERE messagelist.type = '%s' 
                AND schedule.time_date BETWEEN SYMMETRIC '%s' AND '%s' 
                """ % (msg_type, time_from, time_to)
                
                log_query = """SELECT id_code AS code, when_played AS played_time, hostname AS computer FROM playlog 
                JOIN messagelist on playlog.id_code = messagelist.code 
                WHERE messagelist.type = '%s' 
                AND playlog.id_type = 'msg' 
                AND when_played BETWEEN SYMMETRIC '%s' AND '%s' 
                """ % (msg_type, time_from, time_to)
            
            else:
                try:
                    msg_code = str_msg.split(',')[0]
                except AttributeError:
                    #self.msg_error()
                    print("oops")
                    
                sch_query = """SELECT msg_code AS code, time_date AS scheduled_time FROM schedule 
                WHERE msg_code = '%s' 
                AND time_date BETWEEN SYMMETRIC '%s' AND '%s' 
                """ % (msg_code, time_from, time_to)
                
                log_query = """SELECT id_code AS code, when_played AS played_time, hostname AS computer FROM playlog 
                WHERE id_code = '%s' 
                AND playlog.id_type = 'msg' 
                AND when_played BETWEEN SYMMETRIC '%s' AND '%s' 
                """ % (msg_code, time_from, time_to)

        scheduled = self.result_dict_query(sch_query)       
        logged = self.result_dict_query(log_query)

        print(scheduled[0]['scheduled_time'])
        print("----------------------------")
        print("----------------------------")
        print(logged[0])
 
        self.list1 = []
        dict1 = {}
        
        for schedule in scheduled:
            dict1['code'] = schedule['code']
            dict1['scheduled_time'] = (schedule['scheduled_time']).strftime("%Y-%m-%d %H:%M")
            dict1['timestamp'] = dict1['scheduled_time']
            dict1['played_time'] = ""
            dict1['computer'] = ""
            self.list1.append(dict1.copy())

        for log in logged:
            dict1['code'] = log['code']
            dict1['played_time'] = (log['played_time']).strftime("%Y-%m-%d %H:%M")
            dict1['timestamp'] = dict1['played_time']
            dict1['computer'] = log['computer']
            dict1['scheduled_time'] = ""

            self.list1.append(dict1.copy())
            
        #lists and dictionaries
        #list_sorted = sorted(list1, key=operator.itemgetter ('timestamp'), reverse = True)
        self.list1.sort(key=operator.itemgetter ('timestamp'), reverse = True)

        for item in self.list1:
            row_iter = self.store.append()
            self.store.set(row_iter,
                0, item['code'],
                1, item['scheduled_time'],
                2, item['played_time'],
                3, item['computer']
                )

    def save_stats(self, clicked):
        filepath = self.get_filepath()
        if not os.path.isfile(filepath):
            self.write_file(filepath)
        else:
            response = self.confirm_overwrite(filepath)
            if response == gtk.RESPONSE_OK:
                os.remove(filepath)        
                self.write_file(filepath)
            else:
                print("cancelled")

                    
    def write_file(self, filepath):
        with open(filepath, 'w') as csvfile:
            field_names = ['code', 'scheduled_time', 'played_time', 'computer']
            writer = csv.DictWriter(csvfile, fieldnames=field_names)
            writer.writeheader()
            for dict1 in self.list1:
                dict2 = {x:dict1[x] for x in field_names}
                writer.writerow(dict2)        
    

    def quit_program(self, clicked):
        print("clicked quit")
        gtk.main_quit()


    def pg_connect(self):    
        '''
        used to connect to the database that contains the schedule
        ''' 
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            pg_msg_database, pg_user, pg_server, pg_password)
        conn = psycopg2.connect(conn_string)
        return conn
        
    def result_query (self, query):
        conn = self.pg_connect()
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        return result
        
    def result_dict_query (self, query):
        conn = self.pg_connect()
        dict_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        dict_cur.execute(query)
        result = dict_cur.fetchall()
        dict_cur.close()
        conn.close()
        return result
        
    def get_filepath(self):
        action = gtk.FILE_CHOOSER_ACTION_SAVE
        btn = gtk.STOCK_SAVE
        rsp = gtk.RESPONSE_ACCEPT

        dialog = gtk.FileChooserDialog(
            "Save csv file",
            None,
            action,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
            btn, rsp)
            )
        dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        from os.path import expanduser
        home = expanduser("~")
        dialog.set_current_folder(home)
        dfilter = gtk.FileFilter()
        dfilter.set_name("Csv files")
        dfilter.add_pattern("*.csv")
        dialog.add_filter(dfilter)

        response = dialog.run()
        filepath = dialog.get_filename()        
        sfx = ".csv"
        if not filepath[-4:] == sfx:
            filepath = filepath + sfx        
        dialog.destroy()    
        return filepath
        
    def confirm_overwrite (self, filepath):
        message = filepath + " exists. Do you want to overwrite this file?"
        dialog = gtk.MessageDialog(self, 
        gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_QUESTION, 
        gtk.BUTTONS_OK_CANCEL, message)
        response = dialog.run()
        dialog.destroy()
        return response
        
        
    def error_message (self, message):
        md = gtk.MessageDialog(self, 
        gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, 
        gtk.BUTTONS_CLOSE, message)
        md.run()
        md.destroy()


Stats()
gtk.main()
