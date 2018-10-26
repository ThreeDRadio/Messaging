#!/opt/local/bin/python2.7

#scheduler-0.02.py
#tool for scheduling messages
# this version adds the ability to select message types

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

#used to select the day to query the schedule
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
        
        #message type selection
        label_type = gtk.Label("Select a message type:")
        self.cb_msgtype = gtk.combo_box_new_text()
        self.cb_msgtype.connect('changed', self.type_selected)
        list_msgtype = self.all_scheduled_types()
        for item in list_msgtype:
            self.cb_msgtype.append_text(item)
        
        #message selection
        label_sel = gtk.Label("Select a message:")
        self.cb_msg = gtk.combo_box_new_text()

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
        # 0 = timeslot
        # 1 = programme ID
        # 2 = programme name
        # 3 = message ID
        # 4 = message name
        # 5 = message duration
        # 6 = message order
        self.store_sch = gtk.ListStore(str ,str, str, str, str, str, int)         
        self.treeview_sch = gtk.TreeView(self.store_sch)
        self.treeview_sch.set_rules_hint(True)        
        self.make_columns(self.treeview_sch)        
        self.set_up()

        # right click menu

        self.treeview_sch.connect('button-press-event', self.right_click_list_menu)
                   
        #pack the gui
        vbox.pack_start(self.calendar, False)
        vbox.pack_start(label_msg_add, False)
        vbox.pack_start(label_type, False)
        vbox.pack_start(self.cb_msgtype, False)
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

    def right_click_list_menu(self, treeview, event):
        '''
        Action to take for right-click (or maybe other click events)
        '''
        if event.button == 3: # right click
            widget = self.create_menu(self, event)
            widget.popup(None, None, None, event.button, event.time)
            return True
        return False

    def set_up(self):
        '''
        Pick the day for displaying the schedule. Adjust the month
        (Gtk.calendar month goes from 0 - 11)
        call the function to make the treelist
        '''
        sch_list = self.create_list()
        self.make_treelist(sch_list)        

    def get_row(self, pathclicked):
        path = pathclicked[0]
        treeselection = self.treeview_sch.get_selection()
        treeselection.select_path(path)             
        model = self.treeview_sch.get_model()
        sch_iter = model.get_iter(path)
        #sch_time, prog_id, prog_name, msg_id, msg_name
        row = model.get(sch_iter, 0, 1, 2, 3, 4, 5, 6)       
        return row, model, sch_iter

    def create_menu(self, widget, event):
        '''
        create the right-click menu for the schedule treeview
        '''
        self.context_menu = gtk.Menu()            
        pathclicked = self.treeview_sch.get_path_at_pos(int(event.x), int(event.y))
        row, model, sch_iter = self.get_row(pathclicked)
        path = pathclicked[0]
        
        # Delete Item        
        self.delete_item = gtk.MenuItem( "Delete")
        self.delete_item.connect( "activate", self.del_message)
        self.delete_item.show()
        
        msg_id = row[3]
        msg_id = str(msg_id)
        if msg_id:
            self.delete_item.set_sensitive(True)
        else:
            self.delete_item.set_sensitive(False)
        
        # Move Up Item
        self.move_up_item = gtk.MenuItem("Move Up")    
        self.move_up_item.connect( "activate", self.move_up, pathclicked)
        if  msg_id and not(path[0]) == 0:
            self.move_up_item.set_sensitive(True)
        else:
            self.move_up_item.set_sensitive(False)
        self.move_up_item.show()        
        # Move Down Item
        self.move_down_item = gtk.MenuItem("Move Down")    
        self.move_down_item.connect( "activate", self.move_down, pathclicked)     
        
        sch_iter = model.get_iter(path)   
        iter_next = model.iter_next(sch_iter)
        if msg_id and iter_next:
            self.move_down_item.set_sensitive(True)
        else:
            self.move_down_item.set_sensitive(False)
        self.move_down_item.show()   
        self.context_menu.append(self.move_up_item)
        self.context_menu.append(self.move_down_item)
        self.context_menu.append(self.delete_item)
        return self.context_menu

    def pg_connect(self):    
        '''
        used to connect to the database that contains the schedule
        ''' 
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            pg_msg_database, pg_user, pg_server, pg_password)
        conn = psycopg2.connect(conn_string)
        
        return conn

    def on_day_selected(self, widget):
        '''
        appears to be the same as set_up but includes the widget.
        '''
        sch_list = self.create_list()
        self.make_treelist(sch_list)
        
    def create_list(self):
        '''
        queries the schedule and the programme list
        prepares a the list to display in the right pane.
        '''
        wrong_date = self.calendar.get_date()
        selected_date = (wrong_date[0], wrong_date [1]+1, wrong_date[2])
        returned_schedule = self.query_schedule(selected_date)
        schedule_list = self.prepare_schedule_list(returned_schedule)
        programme_list = self.query_programmes(selected_date)
        programme_list = self.prepare_programme_list(programme_list)
        sch_list = self.prepare_list(schedule_list, programme_list)
        return sch_list

    def prepare_programme_list(self, programme_list):
        '''
        formatting for the start time
        '''
        modified_programme_list = []
        for prog in programme_list:
            prog = list(prog)
            prog_start_datetime = prog[2]
            prog_start_str = str(prog_start_datetime)
            prog[2] = prog_start_str[-8:-3]
            modified_programme_list.append(prog)
        return modified_programme_list
        
    def prepare_schedule_list(self, returned_schedule):
        '''
        tidy up a couple of items in the list
        '''
        schedule_list = []
        for msg in returned_schedule:
            msg = list(msg)
            msg[0] = str(msg[0])[-8:-3]
            m, s = divmod((msg[3]), 60)
            h, m = divmod(m, 60)
            if h:
                msg[3] = "%d:%02d:%02d" % (h, m, s)
            
            else:
                msg[3] = "%02d:%02d" % (m, s)

            schedule_list.append(msg)
        return schedule_list

    def result_query (self, query):
        conn = self.pg_connect()
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        return result
        
    def commit_query (self, query):
        conn = self.pg_connect()
        cur = conn.cursor()
        cur.execute(query)
        conn.commit()
        conn.close
        
    def query_schedule(self, selected_date):
        '''
        query the database for scheduled messages on the selected date
        from 6am to mignight
        and from midnight to 6am the following morning
        '''
        selected_date = datetime.date(selected_date[0], selected_date[1], selected_date[2])
        str_selected_date = str(selected_date)
        plus_one = datetime.timedelta(1, 0, 0)
        next_morning = selected_date + plus_one
        str_next_morning = str(next_morning)
        query = "SELECT schedule.time_date,  schedule.msg_code, messagelist.title, messagelist.duration, schedule.msg_order FROM schedule "\
        "JOIN messagelist ON schedule.msg_code=messagelist.code "\
        "WHERE time_date >= '%s 06:00' AND time_date < '%s 06:00' ORDER BY time_date, msg_order" % (str_selected_date, next_morning)
        schedule_list = self.result_query(query)
        return schedule_list
    
    def query_programmes(self, selected_date):
        '''
        Get the list of programmes for the selected day
        from 6am to mignight
        and from midnight to 6am the following morning
        
        '''
        datetime_date = datetime.date(selected_date[0], selected_date[1], selected_date[2])
        day_int = datetime_date.weekday()
        day_of_week = tup_day[day_int]
        if day_int==6:
            next_day = tup_day[0]
        else:
            next_day = tup_day[day_int+1]
        query = "SELECT code, name, start FROM programmes WHERE day='%s' "\
        "AND start >= '6:00' OR day='%s' AND start<'06:00'" % (day_of_week, next_day) 
        programme_list = self.result_query(query)
        return programme_list
    
    def prepare_list(self, schedule_list, programme_list):
        '''
        Creates a list of half hour time slots. Adds programmes and 
        scheduled messages
        
        '''
        timeslot = datetime.time(6, 0)
        add = datetime.timedelta(minutes=30)
        finaltime = datetime.time(5, 30)
        time_list = [["06:00", "", "", "", "", "", 0]]

        while (timeslot != finaltime):
            timeslot = ((datetime.datetime.combine(datetime.date(1,1,1),timeslot)) + add).time()
            timestring = timeslot.strftime("%H:%M")
            timerow = [timestring,  "", "", "", "", "", 0]
            time_list.append(timerow)
            
        n = 0
        for item in time_list:
            n+=1
            m = n
            #check if there is a programme starting at that time
            starttime = item[0]
            for prog in programme_list:
                if prog[2]==starttime:
                   item[1] =  prog[0]
                   item[2] = prog[1]
            #then check if there are messages scheduled for that time
            for msg in schedule_list:
                if msg[4] == '':
                    msg[4] = 0
                
                if msg[0]==starttime:
                    if item[4] == "":
                        item[3] = msg[1]
                        item[4] = msg[2]
                        item[5] = msg[3]
                        item[6] = msg[4]
                        
                    else:
                        time_list.insert(m, ["", "", "", msg[1], msg[2], msg[3], msg[4]])
                        m+=1
        return time_list
        
    def make_treelist(self, sch_list):
        self.store_sch.clear()
        for item in sch_list:
            sch_iter = self.store_sch.append()
            self.store_sch.set(sch_iter,
                0, item[0],
                1, item[1],
                2, item[2],
                3, item[3],
                4, item[4],
                5, item[5],
                6, item[6])
        treeselection = self.treeview_sch.get_selection()
        treeselection.select_path(0)

    def make_columns(self, treeview):
        '''
        Create the columns that are to be used for the list that 
        displays the schedule.
        '''
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

        column = gtk.TreeViewColumn('Length', gtk.CellRendererText(),
                                    text=5)
        column.set_sort_column_id(5)
        column.set_clickable(False)
        self.treeview_sch.append_column(column)     

        column = gtk.TreeViewColumn('Order', gtk.CellRendererText(),
                                    text=6)
        column.set_sort_column_id(5)
        column.set_clickable(False)
        column.set_visible(False)
        self.treeview_sch.append_column(column)    

    def all_scheduled_types(self):
        '''
        Get the message types that have the scheduled property enabled 
        for populating the drop down list of message types
        '''
        list_msgtypes = []
        query =  "SELECT type FROM typelist WHERE scheduled = TRUE ORDER BY type"
        #query =  "SELECT type FROM typelist"
        msg_types = self.result_query(query)
        for item in msg_types:
            list_msgtypes.append(item[0])
        return list_msgtypes
    
    def all_messages(self, entry):
        '''
        Get a list of (non-expired) messages of the selected type.
        '''
        today = datetime.date.today()
        msg_type = entry.get_active_text()
        list_msg = []
        conn = self.pg_connect()
        cur = conn.cursor()
        query =  "SELECT code,title FROM messagelist "\
        "WHERE LOWER(type)=LOWER('%s') "\
        "AND expirydate >= now() ORDER BY code" %(msg_type)
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
        list_msg = self.all_messages(entry)
        for item in list_msg:
            self.cb_msg.append_text(item)
          
    def get_sch_time(self):
        '''
        this is run each time a message is added to or removed from a 
        scheduled slot. It retrieves the time slot from the list for 
        use in the database query for these actions.
        '''
        treeselection = self.treeview_sch.get_selection()
        model, sch_iter = treeselection.get_selected()
        row = model.get(sch_iter, 0, 1, 2, 3, 4, 5, 6)
        
        str_time = row[0]
        selected_rows = treeselection.get_selected_rows()
        list_row_path = selected_rows[1]
        tup_row_path = list_row_path[0]
        row_path = tup_row_path[0]
        path_above = row_path - 1
        
        while not str_time:
            treeselection.select_path(path_above)
            treeselection = self.treeview_sch.get_selection()
            model, sch_iter = treeselection.get_selected()
            row = model.get(sch_iter, 0, 1, 2, 3, 4, 5, 6)
            str_time = row[0]
            path_above = path_above - 1
        treeselection.select_path(row_path)
        sch_time = str_time
        return sch_time
        
    def get_selected_row(self):
        '''
        retrieve the message code of the selected message in the list. 
        For use in message deletion
        '''

        return datatuple

    def cb_msg_get_active(self, cb_msg):
        '''
        returns the message selected in the drop down list
        '''
        model = cb_msg.get_model()
        active = cb_msg.get_active()
        if active < 0:
            return None
        return model[active][0]
        
    def add_message(self, clicked):
        '''
        runs functions to collect information and add the schedule to
        the database
        '''
        str_msg = self.cb_msg_get_active(self.cb_msg)
        str_time = self.get_sch_time()
        wrong_date = self.calendar.get_date()
        #tup_date = (wrong_date[0], wrong_date [1]+1, wrong_date[2])
        obj_datetime = self.get_datetime(str_time)
        int_weeks = self.spinbutton_weeks.get_value_as_int()
        str_weeks = str(int_weeks)
        
        if str_msg:
            self.insert_to_schedule(str_msg, obj_datetime, str_weeks)
        else:
            self.msg_error()
       
    def insert_to_schedule (self, str_msg, obj_datetime, str_weeks):
        '''
        update the database with the newly added schedule
        '''
        #If the selected row does not have a message
            #added msg_order = 0

        #If the selected row has a message
            #n = msg_order of the selected row
            #for every message with that time and msg_order >= n
                #msg_order += 1
            #added msg_order = n
        
        treeselection = self.treeview_sch.get_selection()
        model, sch_iter = treeselection.get_selected()
        path = model.get_path(sch_iter)
        
        ls_msg = str_msg.split(',')
        msg_code = ls_msg[0]
        add_week = datetime.timedelta(7, 0, 0)

        int_weeks = int(str_weeks)
        n = 1
        
        while n <= int_weeks:
            msg_order = self.get_message_count(obj_datetime)
            query = "INSERT INTO schedule (msg_code, time_date, msg_order) VALUES ('%s', '%s', '%s')" % (msg_code, obj_datetime, msg_order)
            self.commit_query(query)           
            obj_datetime = obj_datetime + add_week
            n+=1
        sch_list = self.create_list()
        self.make_treelist(sch_list)
        treeselection.select_path(path)      
        return

    def get_message_count(self, obj_datetime):
        '''
        query the database for the number of messages at that given time
        '''
        query = "SELECT COUNT(*) FROM schedule WHERE time_date='%s'" % (obj_datetime)
        msg_count = self.result_query(query) 
        msg_count = (msg_count[0])[0]
        return msg_count

    def del_message(self, clicked):
        '''
        Actions to take on click of the delete button
        '''
        treeselection = self.treeview_sch.get_selection()
        model, sch_iter = treeselection.get_selected()
        path = model.get_path(sch_iter)
        sch_row = model.get(sch_iter, 0, 1, 2, 3, 4, 5, 6)
        msg_id = sch_row[3]
        msg_order = sch_row[6]
        str_time = self.get_sch_time()
        obj_datetime = self.get_datetime(str_time)
        query = "DELETE FROM schedule WHERE msg_code='%s' AND time_date='%s'" % (msg_id, obj_datetime)
        self.commit_query(query)
        query = "UPDATE schedule SET msg_order=msg_order-1 WHERE time_date='%s' AND msg_code>'%s'" %(obj_datetime, msg_id)
        self.commit_query(query)            
        sch_list = self.create_list()
        self.make_treelist(sch_list)
        self.make_treelist(sch_list)
        treeselection.select_path(path)      
        

    def move_up(self, widget, pathclicked):
        '''
        move the message up in the list
        -- still developing --
        '''
        row, model, sch_iter = self.get_row(pathclicked)

        sch_time = row[0] 
        msg_id = row[3]
        msg_order = row[6]

        path = pathclicked[0]
        path_above = ((path[0]) - 1,)

        iter_above = model.get_iter(path_above)
        sch_time_above = model[iter_above][0]
        msg_id_above = model[iter_above][3]
        msg_order_above = model[iter_above][6]
        
        iter_below = model.iter_next(sch_iter)
        sch_time_below = model[iter_below][0]
        msg_id_below = model[iter_below][3]
        msg_order_below = model[iter_below][6]        
        
        #if the selected message has a time
        if sch_time:
            # turn the time into a datetime object
            obj_datetime = self.get_datetime(sch_time)
            #if the row above has a time but not a message
            if sch_time_above and not msg_id_above:
                #time_date -= 00:30
                #msg_order = 0
                msg_order = 0
                self.modify_schedule(sch_time, sch_time_above, msg_id, msg_order)

                #if the row below has a message but not a time
                if msg_id_below and not sch_time_below: 
                    #for each row with the same time as the selected message msg_order -= 1 
                    #create and execute the query
                    query = "update schedule set msg_order=msg_order-1 where time_date='%s' and msg_code!='%s'" %(obj_datetime, msg_id)
                    self.commit_query(query)
                        

            #If the row above has a message but not a time
            if msg_id_above and not sch_time_above:
                #time_date -= 00:30
                sch_time_new = self.modify_timeslot("subtract", sch_time)
                #msg_order = (count messages scheduled for that time_date)
                obj_datetime_new = self.get_datetime(sch_time_new)
                msg_order = self.get_message_count(obj_datetime_new)
                self.modify_schedule(sch_time, sch_time_new, msg_id, msg_order)
                
                #if the row below has a message but not a time
                if msg_id_below and not sch_time_below:
                    query = "update schedule set msg_order=msg_order-1 where time_date='%s' and msg_code!='%s'" %(obj_datetime, msg_id)
                    self.commit_query(query)                    


            #if the row above has a time and a message
            if sch_time_above and msg_id_above:
                #time_date -= 00:30
                sch_time_previous = self.modify_timeslot("subtract", sch_time)
                #msg_order = 1
                msg_order = 1
                self.modify_schedule(sch_time, sch_time_previous, msg_id, msg_order)
                
                #if the row below has a message but not a time
                if msg_id_below and not sch_time_below:
                    #for each row with the same time as the selected message msg_order -= 1 
                    query = "update schedule set msg_order=msg_order-1 where time_date='%s' and msg_code!='%s'" %(obj_datetime, msg_id)
                    self.commit_query(query)

        #If the selected row has not a time
        if not sch_time:
            #If the row above has a time and a message
            if sch_time_above and msg_id_above:
                #msg_order = 0
                msg_order = 0
                sch_time = self.get_sch_time()
                self.modify_schedule(sch_time, sch_time, msg_id, msg_order)
                #row_above msg_order = 1
                msg_order_above = 1
                self.modify_schedule(sch_time_above, sch_time_above, msg_id_above, msg_order_above)

            #If the row above has a message but not a time
            if msg_id_above and not sch_time_above:
                #msg_order -= 1
                msg_order = msg_order - 1
                sch_time = self.get_sch_time()
                self.modify_schedule(sch_time, sch_time, msg_id, msg_order)
                #row_above msg_order +=1
                msg_order_above = msg_order_above + 1
                self.modify_schedule(sch_time, sch_time, msg_id_above, msg_order_above)
                
                
        sch_list = self.create_list()
        self.make_treelist(sch_list)
        treeselection = self.treeview_sch.get_selection()
        treeselection.select_path(path_above)
        
        
     
    def move_down(self, widget, pathclicked):
        '''
        move the message down in the list
        -- still developing --
        '''
        row, model, sch_iter = self.get_row(pathclicked)

        sch_time = row[0] 
        msg_id = row[3]
        msg_order = row[6]

        path = pathclicked[0]
        path_above = ((path[0]) - 1,)
        path_below = ((path[0]) + 1,)

        iter_above = model.get_iter(path_above)
        sch_time_above = model[iter_above][0]
        msg_id_above = model[iter_above][3]
        msg_order_above = model[iter_above][6]
        
        iter_below = model.iter_next(sch_iter)
        sch_time_below = model[iter_below][0]
        msg_id_below = model[iter_below][3]
        msg_order_below = model[iter_below][6]       

        #If the selected row has a time
        if sch_time:
            obj_datetime = self.get_datetime(sch_time)
            #If the row below has a time but not a message
            if sch_time_below and not msg_id_below:
                #msg_order = 0
                #time_date += 00:30 
                msg_order = 0
                self.modify_schedule(sch_time, sch_time_below, msg_id, msg_order)

            #If the row below has a time and a message
            if sch_time_below and msg_id_below:
                #for each row below with (time_date + 00:30) msg_order += 1
                obj_datetime_below = self.get_datetime(sch_time_below)
                query = "UPDATE SCHEDULE SET msg_order=msg_order+1 WHERE time_date='%s'" %(obj_datetime_below)
                self.commit_query(query)
                #time_date += 00:30 msg_order = 0
                self.modify_schedule(sch_time, sch_time_below, msg_id, msg_order)
                
            #If the row below has a message but no time
            if msg_id_below and not sch_time_below:
                msg_order = 1
                self.modify_schedule(sch_time, sch_time, msg_id, msg_order)
                msg_order_below = 0
                self.modify_schedule(sch_time, sch_time, msg_id_below, msg_order_below)

        #If the selected row does not have a time
        if not sch_time:
            sch_time = self.get_sch_time()
            #If the row below does has a message but not a time
            if msg_id_below and not sch_time_below:
                #swap the msg_order of the two rows
                self.modify_schedule(sch_time, sch_time, msg_id, msg_order_below)
                self.modify_schedule(sch_time, sch_time, msg_id_below, msg_order)

            #If the row below has a time and a message
            if msg_id_below and sch_time_below:
                #for each message row below with same time msg_order += 1
                obj_datetime_below = self.get_datetime(sch_time_below)
                query = "UPDATE SCHEDULE SET msg_order=msg_order+1 WHERE time_date='%s'" %(obj_datetime_below)
                #date_time += 00:30 msg_order = 0
                msg_order = 0
                self.modify_schedule(sch_time, sch_time_below, msg_id, msg_order)
                
                

            #If the row below has a time but not a message
            if sch_time_below and not msg_id_below:
                #date_time += 00:30 msg_order = 0
                msg_order = 0
                self.modify_schedule(sch_time, sch_time_below, msg_id, msg_order)
                
        
        sch_list = self.create_list()
        self.make_treelist(sch_list)
        treeselection = self.treeview_sch.get_selection()
        treeselection.select_path(path_below)
        
    def modify_timeslot(self, action, sch_time):
        #turn the string into a time object
        time_object = self.get_datetime(sch_time)

        #create a delta of 30 minutes
        if action == "add":
            delta = datetime.timedelta(minutes=30)
        elif action == "subtract":
            delta = datetime.timedelta(minutes=-30)
        
        #action - add or subtract the delta
        time_object = time_object + delta

        #convert the modified time object into a string        
        timestring = time_object.strftime("%H:%M")

        return timestring
    
    def modify_schedule(self, sch_time, sch_time_new, msg_id, msg_order):
        sch_time = self.get_datetime(sch_time)
        sch_time_new = self.get_datetime(sch_time_new)
        query = "UPDATE schedule SET time_date = '%s', msg_order = '%s' where msg_code = '%s' and time_date = '%s'" % (sch_time_new, msg_order, msg_id, sch_time)
        self.commit_query(query)

    def msg_error(self):
        '''
        message pop up 
        '''
        md = gtk.MessageDialog(self, 
            gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, 
            gtk.BUTTONS_CLOSE, "You need to select a message!")
        md.run()
        md.destroy()

    def show_stats(self, clicked):
        '''
        trigger the stats functions on click of the stats button
        '''
        str_msg = self.cb_msg_get_active(self.cb_msg)
        try:
            msg_code = str_msg.split(',')[0]
            stats = self.get_stats(msg_code)
            self.sch_stats(str_msg, stats)
        except AttributeError:
            self.msg_error() 

    def get_stats(self, msg_code):
        '''
        retrieve all schedules for the specified message
        '''
        query = "SELECT time_date FROM schedule WHERE msg_code='%s' ORDER BY time_date DESC" % (msg_code)
        stats = self.result_query(query)
        return stats
    
    def get_datetime(self, str_time):
        '''
        return a datetime object from the selected time and the selected date
        '''
        wrong_date = self.calendar.get_date()
        tup_date = (wrong_date[0], wrong_date [1]+1, wrong_date[2])
        obj_date = datetime.date(tup_date[0], tup_date[1], tup_date[2])   
        add_day = datetime.timedelta(1, 0, 0)
        
        if str_time >= "00:00" and str_time < "06:00":
            obj_date = obj_date + add_day
        
        str_date = str(obj_date)
        str_date_time = str_date + " " + str_time + ":00"
        h, m = str_time.split(':')
        obj_time = datetime.time(int(h), int(m))
        obj_datetime = datetime.datetime.combine(obj_date, obj_time)
        return obj_datetime
    
    def sch_stats(self, str_msg, stats):
        '''
        process and display the provided schedule information for the 
        message in question
        '''
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

