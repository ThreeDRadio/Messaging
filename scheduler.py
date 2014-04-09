#!/usr/bin/python

#scheduler-0.02.py
#tool for scheduling messages

import pygtk
import gtk
import gobject
import psycopg2
import time
import pango
import ConfigParser
import datetime

#get variables from config file
config = ConfigParser.SafeConfigParser()
config.read('/usr/local/etc/threedradio.conf')

dir_msg = config.get('Paths', 'dir_msg')
dir_img = config.get('Paths', 'dir_img')
logo = config.get('Images', 'logo')

pg_user = config.get('Scheduler', 'pg_user')
pg_password = config.get('Scheduler', 'pg_password')
pg_server = config.get('Common', 'pg_server')
pg_msg_database = config.get('Common', 'pg_msg_database')

tup_day = ("Monday", 
            "Tuesday", 
            "Wednesday", 
            "Thursday", 
            "Friday", 
            "Saturday", 
            "Sunday")

class Scheduler(gtk.Window):
   
    def __init__(self, parent=None):
        # create window, etc
        gtk.Window.__init__(self)
        try:
            self.set_screen(parent.get_screen())
        except AttributeError:
            self.connect('destroy', lambda *w: gtk.main_quit())
        self.set_title("Scheduler")
        self.set_position(gtk.WIN_POS_CENTER)
        filepath_logo = dir_img + logo
        self.set_icon_from_file(filepath_logo)
        self.connect("destroy", gtk.main_quit)
        
        # Boxes and scrolled windows
        hbox_main = gtk.HBox(False, 0)
        vbox = gtk.VBox(False, 0)
        sw = gtk.ScrolledWindow()
        sw.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        hbox_weeks = gtk.HBox(False, 0)
        hbox_sum = gtk.HBox(False, 0)
        
        ### widgets to display ###
        
        #calendar
        self.calendar = gtk.Calendar() 
        self.calendar.connect("day_selected", self.on_day_selected)
        
        #Main Label
        label_msg_add = gtk.Label("\nAdd messages")
        subheader_font = pango.FontDescription("Sans Bold 12")
        label_msg_add.modify_font(subheader_font)
        
        #message selection
        label_sel = gtk.Label("Click below to select a message:")
        self.cb_msg = gtk.combo_box_new_text()
        list_msg = self.all_messages()
        for item in list_msg:
            self.cb_msg.append_text(item)
        
        # weeks to run
        label_add_for = gtk.Label("\nAdd for the next  \n")
        #label_add_for.set_size_request(20, 40)
        adj_spin_weeks = gtk.Adjustment(1, 1, 8, 1, 4, 0)
        self.spinbutton_weeks = gtk.SpinButton(adj_spin_weeks, 0, 0)
        #self.spinbutton.weeks.set_numeric(True)
        label_weeks = gtk.Label("\n  weeks.\n")     
        
        #Add
        button_add = gtk.Button("Add to Schedule")
        button_add.connect("clicked", self.add_message)
        
        #delete
        label_del_head = gtk.Label("\nRemove Message")
        label_del_head.modify_font(subheader_font)
        str_del = "Select a message on the right \nand click the button below\n"
        label_del = gtk.Label(str_del)
        
        button_del = gtk.Button("Remove from Schedule")
        button_del.connect("clicked", self.del_message)
        
        # stats
        label_stats = gtk.Label("Stats")
        subheader_font = pango.FontDescription("Sans Bold 12")
        label_stats.modify_font(subheader_font)
        button_stats = gtk.Button("Show Stats")
        button_stats.connect("clicked", self.show_stats)
        
        #make the list
        self.store_sch = gtk.ListStore(str ,str, str, str, str)         
        self.treeview_sch = gtk.TreeView(self.store_sch)
        self.treeview_sch.set_rules_hint(True)
        self.make_columns(self.treeview_sch)
        
        self.set_up()
    
        #pack the gui
        vbox.pack_start(self.calendar, False)
        vbox.pack_start(label_msg_add, False)
        vbox.pack_start(label_sel, False)
        vbox.pack_start(self.cb_msg, False)
        hbox_weeks.pack_start(label_add_for, False)
        hbox_weeks.pack_start(self.spinbutton_weeks, False)
        hbox_weeks.pack_start(label_weeks, False)
        vbox.pack_start(hbox_weeks, False)
        vbox.pack_start(button_add, False)
        vbox.pack_start(label_del_head, False)
        vbox.pack_start(label_del, False)
        vbox.pack_start(button_del, False)
        vbox.pack_start(label_stats, False)
        vbox.pack_start(button_stats, False)
        hbox_main.pack_start(vbox, False)
        sw.add(self.treeview_sch)
        hbox_main.pack_end(sw, True)
        self.add(hbox_main)
        self.show_all()

    def set_up(self):
        wrong_date = self.calendar.get_date()
        selected_date = (wrong_date[0], wrong_date [1]+1, wrong_date[2])     
        sch_list = self.create_list(selected_date)
        self.make_treelist(sch_list)        

    def pg_connect(self):     
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            pg_msg_database, pg_user, pg_server, pg_password)
        conn = psycopg2.connect(conn_string)
        
        return conn

    def on_day_selected(self, widget):
        wrong_date = widget.get_date()
        selected_date = (wrong_date[0], wrong_date [1]+1, wrong_date[2])     
        sch_list = self.create_list(selected_date)
        self.make_treelist(sch_list)
        
    def create_list(self, selected_date):
        schedule_list = self.query_schedule(selected_date)
        programme_list = self.query_programmes(selected_date)
        sch_list = self.prepare_list(schedule_list, programme_list)
        return sch_list
        
    def query_schedule(self, selected_date):
        selected_date = datetime.date(selected_date[0], selected_date[1], selected_date[2])
        str_selected_date = str(selected_date)
        plus_one = datetime.timedelta(1, 0, 0)
        next_morning = selected_date + plus_one
        str_next_morning = str(next_morning)
        conn = self.pg_connect()
        cur = conn.cursor()
        query = "SELECT schedule.time_date,  schedule.msg_code, messagelist.title FROM schedule "\
        "JOIN messagelist ON schedule.msg_code=messagelist.code "\
        "WHERE time_date >= '%s 06:00' AND time_date < '%s 06:00' ORDER BY time_date" % (str_selected_date, next_morning)
        cur.execute(query)
        schedule_list = cur.fetchall()
        cur.close()
        conn.close()
        return schedule_list
    
    def query_programmes(self, selected_date):
        datetime_date = datetime.date(selected_date[0], selected_date[1], selected_date[2])
        day_int = datetime_date.weekday()
        day_of_week = tup_day[day_int]
        if day_int==6:
            next_day = 0
        else:
            next_day = tup_day[day_int+1]
        conn = self.pg_connect()
        cur = conn.cursor()
        query = "SELECT code, name, start FROM programmes WHERE day='%s' "\
        "AND start >= '6:00' OR day='%s' AND start<'06:00'" % (day_of_week, next_day) 
        cur.execute(query) 
        programme_list = cur.fetchall()
        cur.close()
        conn.close()
        return programme_list
    
    def prepare_list(self, schedule_list, programme_list):
        time_list = [["06:00", "", "", "", ""],
             ["06:30", "", "", "", ""],
             ["07:00", "", "", "", ""],
             ["07:30", "", "", "", ""],
             ["08:00", "", "", "", ""],
             ["08:30", "", "", "", ""],
             ["09:00", "", "", "", ""],
             ["09:30", "", "", "", ""],
             ["10:00", "", "", "", ""],
             ["10:30", "", "", "", ""],
             ["11:00", "", "", "", ""],
             ["11:30", "", "", "", ""],
             ["12:00", "", "", "", ""],
             ["12:30", "", "", "", ""],
             ["13:00", "", "", "", ""],
             ["13:30", "", "", "", ""],
             ["14:00", "", "", "", ""],
             ["14:30", "", "", "", ""],
             ["15:00", "", "", "", ""],
             ["15:30", "", "", "", ""],
             ["16:00", "", "", "", ""],
             ["16:30", "", "", "", ""],
             ["17:00", "", "", "", ""],
             ["17:30", "", "", "", ""],
             ["18:00", "", "", "", ""],
             ["18:30", "", "", "", ""],
             ["19:00", "", "", "", ""],
             ["19:30", "", "", "", ""],
             ["20:00", "", "", "", ""],
             ["20:30", "", "", "", ""],
             ["21:00", "", "", "", ""],
             ["21:30", "", "", "", ""],
             ["22:00", "", "", "", ""],
             ["22:30", "", "", "", ""],
             ["23:00", "", "", "", ""],
             ["23:30", "", "", "", ""],
             ["00:00", "", "", "", ""],
             ["00:30", "", "", "", ""],
             ["01:00", "", "", "", ""],
             ["01:30", "", "", "", ""],
             ["02:00", "", "", "", ""],
             ["02:30", "", "", "", ""],
             ["03:00", "", "", "", ""],
             ["03:30", "", "", "", ""],
             ["04:00", "", "", "", ""],
             ["04:30", "", "", "", ""],
             ["05:00", "", "", "", ""],
             ["05:30", "", "", "", ""]]
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
                msg_start = str(msg[0])[-8:-3]

                if msg_start==starttime:
                    if item[4] == "":
                        item[3] = msg[1]
                        item[4] = msg[2]
                        
                    else:
                        time_list.insert(n, ["", "", "", msg[1], msg[2]])
        return time_list
        
    def make_treelist(self, sch_list):
        self.store_sch.clear()
        for item in sch_list:
            iter = self.store_sch.append()
            self.store_sch.set(iter,
                0, item[0],
                1, item[1],
                2, item[2],
                3, item[3],
                4, item[4],)
        treeselection = self.treeview_sch.get_selection()
        treeselection.select_path(0)

    def make_columns(self, treeview):
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                     text=0)
        column.set_sort_column_id(0)
        column.set_clickable(False)
        self.treeview_sch.append_column(column)
        
        column = gtk.TreeViewColumn('Programme Code', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(False)
        column.set_visible(False)
        self.treeview_sch.append_column(column) 

        column = gtk.TreeViewColumn('Programme', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        self.treeview_sch.append_column(column)
        
        column = gtk.TreeViewColumn('ID Code', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        self.treeview_sch.append_column(column)
        
        column = gtk.TreeViewColumn('Message', gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        self.treeview_sch.append_column(column)
    
    def all_messages(self):
        today = datetime.date.today()
        list_msg = []
        conn = self.pg_connect()
        cur = conn.cursor()
        query =  "SELECT code,title FROM messagelist "\
        "WHERE (LOWER(type)=LOWER('SPONSORSHIP') "\
        "OR LOWER(type)=LOWER('3D_RADIO'))"\
        "AND expirydate >= now()"

        cur.execute(query)
        msg_list = cur.fetchall()
        cur.close()
        conn.close()
        for item in msg_list:
            list_msg.append(item[0] + ", " + item[1])
        return list_msg
  
    def get_sch_time(self):
        treeselection = self.treeview_sch.get_selection()
        model, iter = treeselection.get_selected()
        datatuple = model.get(iter, 0, 1, 2, 3, 4)
        
        
        
        str_time = datatuple[0]
        selected_rows = treeselection.get_selected_rows()
        list_row_path = selected_rows[1]
        tup_row_path = list_row_path[0]
        row_path = tup_row_path[0]
        path_above = row_path - 1
        
        while not str_time:
            treeselection.select_path(path_above)
            treeselection = self.treeview_sch.get_selection()
            model, iter = treeselection.get_selected()
            datatuple = model.get(iter, 0, 1, 2, 3, 4)
            str_time = datatuple[0]
            path_above = path_above - 1
        treeselection.select_path(row_path)
        sch_time = str_time
        return sch_time
        
    def get_code(self):
        treeselection = self.treeview_sch.get_selection()      
        model, iter = treeselection.get_selected()
        datatuple = model.get(iter, 0, 1, 2, 3, 4)
        str_code = datatuple[3]
        return str_code

    def cb_msg_get_active(self, cb_msg):
        model = cb_msg.get_model()
        active = cb_msg.get_active()
        if active < 0:
            return None
        return model[active][0]
        
    def add_message(self, clicked):
        str_msg = self.cb_msg_get_active(self.cb_msg)
        str_time = self.get_sch_time()
        wrong_date = self.calendar.get_date()
        tup_date = (wrong_date[0], wrong_date [1]+1, wrong_date[2])
        int_weeks = self.spinbutton_weeks.get_value_as_int()
        str_weeks = str(int_weeks)
        if str_msg:
            self.insert_to_schedule(str_time, str_msg, tup_date, str_weeks)
        else:
            self.msg_error()
       
    def insert_to_schedule (self, str_time, str_msg, tup_date, str_weeks):
        obj_date = datetime.date(tup_date[0], tup_date[1], tup_date[2])
        ls_msg = str_msg.split(',')
        msg_code = ls_msg[0]
        add_week = datetime.timedelta(7, 0, 0)
        add_day = datetime.timedelta(1, 0, 0)
        if str_time >= "00:00" and str_time < "06:00":
            obj_date = obj_date + add_day
            
        int_weeks = int(str_weeks)
        n = 1
        
        while n <= int_weeks:
            conn = self.pg_connect()
            cur = conn.cursor()
            str_date = str(obj_date)
            str_date_time = str_date + " " + str_time + ":00"
            query = "INSERT INTO schedule (msg_code, time_date) VALUES ('%s', '%s')" % (msg_code, str_date_time)
            cur.execute(query)
            conn.commit()
            
            obj_date = obj_date + add_week
            n+=1
        cur.close()
        sch_list = self.create_list(tup_date)
        self.make_treelist(sch_list)
        return

    def del_message(self, clicked):
        conn = self.pg_connect()
        cur = conn.cursor()
        
        str_code = self.get_code()
        str_time = self.get_sch_time()

        wrong_date = self.calendar.get_date()
        tup_date = (wrong_date[0], wrong_date [1]+1, wrong_date[2])
        obj_date = datetime.date(tup_date[0], tup_date[1], tup_date[2])   
        add_day = datetime.timedelta(1, 0, 0)
        if str_time >= "00:00" and str_time < "06:00":
            obj_date = obj_date + add_day
        str_date = str(obj_date)
        #str_date = str(tup_date[0]) + "-" + str(tup_date[1]) + "-" + str(tup_date[2])
        str_date_time = str_date + " " + str_time + ":00"
        
        query = "DELETE FROM schedule WHERE msg_code='%s' AND time_date='%s'" % (str_code, str_date_time)
        cur.execute(query)
        conn.commit()
        conn.close
        sch_list = self.create_list(tup_date)
        self.make_treelist(sch_list)       

    def msg_error(self):
        md = gtk.MessageDialog(self, 
            gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, 
            gtk.BUTTONS_CLOSE, "You need to select a message!")
        md.run()
        md.destroy()

    def show_stats(self, clicked):
        str_msg = self.cb_msg_get_active(self.cb_msg)
        try:
            msg_code = str_msg.split(',')[0]
            stats = self.get_stats(msg_code)
            self.sch_stats(str_msg, stats)
        except AttributeError:
            self.msg_error() 

    def get_stats(self, msg_code):
        conn = self.pg_connect()
        cur = conn.cursor()
        query = "SELECT time_date FROM schedule WHERE msg_code='{0}' ORDER BY time_date DESC".format(msg_code)
        cur.execute(query)
        stats = cur.fetchall()
        cur.close()
        conn.close()
        return stats
    
    def sch_stats(self, str_msg, stats):
        msg_details = str_msg.split(',')
        msg_code = msg_details[0]
        msg_title = msg_details[1]
        dialog_title = msg_code + " :  " + msg_title
        dialog = gtk.Dialog(dialog_title, None, 
            gtk.DIALOG_DESTROY_WITH_PARENT | gtk.DIALOG_NO_SEPARATOR, 
            buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
        #dialog.set_size_request(420, 60)
        sw = gtk.ScrolledWindow()
        sw.set_size_request(360, 340)
        vbox = gtk.VBox(False, 0)
        
        n = len(stats)
        count = "Message has been scheduled {0} times".format (n)
        label = gtk.Label(count)
        dialog.vbox.pack_start(label, False, True, 5)
        label.show()
        sep = gtk.HSeparator()
        nw = datetime.datetime.now()
        for item in stats: 
            if item[0] > nw:
                str_dt = item[0].strftime("%A, %d. %B   %I:%M   %Y     ")
                label = gtk.Label(str_dt)
                label.set_justify(gtk.JUSTIFY_RIGHT)
                label.set_alignment(1, 0.5)
                vbox.pack_start(label, False)
                label.show()
               
        vbox.pack_start(sep, False)
        sep.show()
    
        for item in stats:
             if item[0] <= nw:
                str_dt = item[0].strftime("%A, %d. %B   %I:%M   %Y     ")
                label = gtk.Label(str_dt)
                vbox.pack_start(label, False)
                label.set_justify(gtk.JUSTIFY_RIGHT)
                label.set_alignment(1, 0.5)
                label.show()
        
        
        sw.add_with_viewport(vbox)
        dialog.vbox.pack_start(sw, True)
        vbox.show()
        sw.show()
        dialog.run()
        dialog.destroy()
    
    

Scheduler()
gtk.main()

'''
To Fix
make query case insensitive
make query exclude outdated messages 
'''

