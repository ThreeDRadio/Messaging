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
import time
from psycopg2 import sql
import psycopg2.extras


# programmes database table details
'''
                     Table "public.programmes"
   Column    |          Type          | Collation | Nullable | Default 
-------------+------------------------+-----------+----------+---------
 code        | character varying(6)   |           | not null | 
 name        | character varying(36)  |           | not null | 
 day         | character varying(9)   |           | not null | 
 start       | time without time zone |           |          | 
 presenters  | character varying(50)  |           |          | 
 description | character varying(70)  |           |          | 
Indexes:
    "programmes_pkey" PRIMARY KEY, btree (code)

'''



#variables

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

class Common():
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

    def cb_setup(self, cb):
        '''
        Populate the drop down list with days of the week
        Set the active day as today (-6 hours for 6am start of day)
        '''
        for day in tup_day:
            cb.append_text(day)
        now = datetime.datetime.now()
        delta = datetime.timedelta(hours=-6)
        day = now + delta
        index = int(day.strftime("%w"))
        cb.set_active(index)

    def error_dialog(self, str_error):
        messagedialog = gtk.MessageDialog(None, 0, 
                    gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE, 
                    str_error)
        messagedialog.run()
        messagedialog.destroy()  



class ProgrammeInfo():
    def __init__(self, programme):
        dialog = gtk.Dialog("Edit Programme", None, 
        0, 
        (gtk.STOCK_OK, gtk.RESPONSE_CANCEL))



        table = gtk.Table(7, 2, False)
        
        code = programme['code']
        day = programme['day']
        start = programme['start']
        name = programme['name']
        presenters = programme ['presenters']
        description = programme['description']


        label_ref_code = gtk.Label("Code: ")
        table.attach(label_ref_code, 0, 1, 0, 1, False, False, 5, 0)
        label_code = gtk.Label(code)
        label_code.set_selectable(True)
        table.attach(label_code, 1, 2, 0, 1, False, False, 5, 0)
        
        label_ref_name = gtk.Label("Name: ")
        table.attach(label_ref_name, 0, 1, 1, 2, False, False, 5, 0)
        label_name = gtk.Label(name)
        label_name.set_selectable(True)
        table.attach(label_name, 1, 2, 1, 2, False, False, 5, 0)

        label_ref_day = gtk.Label("Day: ")
        table.attach(label_ref_day, 0, 1, 2, 3, False, False, 5, 0)
        label_day = gtk.Label(day)
        label_day.set_selectable(True)

        table.attach(label_day, 1, 2, 2, 3, False, False, 5, 0)

        label_ref_start = gtk.Label("Start Time: ")
        table.attach(label_ref_start, 0, 1, 3, 4, False, False, 5, 0)
        start = start.strftime("%H:%M")
        label_start = gtk.Label(start)
        label_start.set_selectable(True)

        table.attach(label_start, 1, 2, 3, 4, False, False, 5, 0)

        label_ref_pres = gtk.Label("Presenters: ")
        table.attach(label_ref_pres, 0, 1, 4, 5, False, False, 5, 0)
        label_pres = gtk.Label(presenters)
        label_pres.set_selectable(True)

        table.attach(label_pres, 1, 2, 4, 5, False, False, 5, 0)

        label_ref_desc = gtk.Label("Description: ")
        table.attach(label_ref_desc, 0, 1, 5, 6, False, False, 5, 0)
        label_desc = gtk.Label(description)
        label_desc.set_selectable(True)

        table.attach(label_desc, 1, 2, 5, 6, False, False, 5, 0)

        dialog.vbox.pack_start(table, True, True, 0)
        dialog.show_all()
        response = dialog.run()    
        dialog.destroy()



class DeleteProgramme():
    def __init__(self, programme):
        dialog = gtk.Dialog("Edit Programme", None, 
        0, 
        (gtk.STOCK_DELETE, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        
        self.programme = programme
        code = programme['code']
        name = programme['name']
        delete_confirm = "Are you sure you want to delete \n" + name + "?"
        label_confirm = gtk.Label(delete_confirm)

        dialog.vbox.pack_start(label_confirm, True, True, 0)
        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self.delete_programme(None, code)       
        dialog.destroy()

    def delete_programme(self, widget, code):
        query, variables = ("DELETE FROM programmes WHERE code = %s", (code,))
 
        common = Common()
        conn = common.pg_connect_msg()
        cur = conn.cursor()
        #print(query.as_string(conn))
        cur.execute(query, variables)
        conn.commit()
        cur.close()
        conn.close()      

class AddProgramme():
    def __init__(self):
        dialog = gtk.Dialog("Add Programme", None, 
        0, 
        (gtk.STOCK_SAVE, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))

        table = gtk.Table(7, 2, False)
        
        label_ref_code = gtk.Label("Code")
        table.attach(label_ref_code, 0, 1, 0, 1, False, False, 5, 0)
        self.entry_code = gtk.Entry()
        table.attach(self.entry_code, 1, 2, 0, 1, False, False, 5, 0)
        
        label_ref_name = gtk.Label("Name")
        table.attach(label_ref_name, 0, 1, 1, 2, False, False, 5, 0)
        self.entry_name = gtk.Entry(36)
        table.attach(self.entry_name, 1, 2, 1, 2, False, False, 5, 0)

        label_ref_day = gtk.Label("Day")
        table.attach(label_ref_day, 0, 1, 2, 3, False, False, 5, 0)
        self.cb_day = gtk.combo_box_new_text()
        common = Common()
        common.cb_setup(self.cb_day)
        table.attach(self.cb_day, 1, 2, 2, 3, False, False, 5, 0)

        label_ref_start = gtk.Label("Start Time")
        table.attach(label_ref_start, 0, 1, 3, 4, False, False, 5, 0)
        self.cb_start = gtk.combo_box_new_text()
        timeslot = datetime.time(0, 0)
        add = datetime.timedelta(minutes=30)
        finaltime = datetime.time(23, 30)
        ls_start = []
        self.cb_start.append_text('00:00')
        ls_start.append('00:00')

        while (timeslot != finaltime):
            timeslot = ((datetime.datetime.combine(datetime.date(1,1,1),timeslot)) + add).time()
            timestring = timeslot.strftime("%H:%M")                
            self.cb_start.append_text(timestring)
            ls_start.append(timestring)

        self.cb_start.set_active(0)
        table.attach(self.cb_start, 1, 2, 3, 4, False, False, 5, 0)

        label_ref_pres = gtk.Label("Presenters")
        table.attach(label_ref_pres, 0, 1, 4, 5, False, False, 5, 0)
        self.entry_pres = gtk.Entry(50)
        table.attach(self.entry_pres, 1, 2, 4, 5, False, False, 5, 0)

        label_ref_desc = gtk.Label("Description")
        table.attach(label_ref_desc, 0, 1, 5, 6, False, False, 5, 0)
        self.entry_desc = gtk.Entry(70)
        self.entry_desc.set_editable(True)
        table.attach(self.entry_desc, 1, 2, 5, 6, False, False, 5, 0)

        dialog.vbox.pack_start(table, True, True, 0)
        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self.add_programme(None)
            
        dialog.destroy()       
        

    def add_programme(self, widget):
        '''
        actions to add the new prgramme to the database 
        when the SAVE button is clicked
        '''
        dict_add = self.collect_values()
        list_check = self.check_values(dict_add)
        if list_check:
            str_error = self.create_error(dict_add, list_check)
            common = Common()
            common.error_dialog(str_error)
            return False
        
        else:
            self.add_to_database(dict_add)
            return True
            

    def collect_values(self):
        '''
        get values from modifiable items and compare with original values
        return dictionary of modified values
        '''
        code = self.entry_code.get_text()
        dict_add = {"code": code}
        
        name = self.entry_name.get_text()
        dict_add["name"] = name

        day = self.cb_day.get_active_text()
        dict_add["day"] = day

        start = self.cb_start.get_active_text()
        start = datetime.datetime.strptime(start, "%H:%M")
        dict_add["start"] = start
        
        presenters = self.entry_pres.get_text()
        dict_add["presenters"] = presenters

        description = self.entry_desc.get_text()
        if description:
            dict_add["description"] = description

        return dict_add

    def check_values(self, dict_add):
        '''
        Check that code and day/start are not in use
        '''
        code = dict_add['code']        
        day = dict_add['day']
        start = dict_add['start']
        start = start.strftime("%H:%M")

        search_terms = (code, day, start)
        query = "SELECT * FROM programmes WHERE code=%s OR (day=%s AND start=%s)"

        common = Common()
        conn = common.pg_connect_msg()

        dict_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        dict_cur.execute(query, search_terms)
        list_check = dict_cur.fetchall()
        dict_cur.close()
        conn.close() 

        return list_check

    def add_to_database(self, dict_add):
        '''
        Create and execute a query to add the programme to the database
        '''


        add_keys = dict_add.keys()
        query = sql.SQL("INSERT INTO programmes ({}) VALUES ({})").format(
            sql.SQL(', ').join(map(sql.Identifier, add_keys)),
            sql.SQL(', ').join(map(sql.Placeholder, add_keys))
            )
    
        common = Common()
        conn = common.pg_connect_msg()
        cur = conn.cursor()
        #print(query.as_string(conn))
        cur.execute(query, dict_add)
        conn.commit()
        cur.close()
        conn.close()       

    def create_error(self, dict_add, list_check):
        '''
        use the results from the checking to display conflict of start time or code
        '''
        str_error = ""
        code = dict_add['code']
        day = dict_add['day']
        start = dict_add['start']
        start = start.strftime("%H:%M")


        for item in list_check:
            item_start = (item['start']).strftime("%H:%M")
            name = item['name']
            if item['code'] == code:
                str_error = "{} has code {}\n".format(name, code)

            if item_start == start and item['day'] == day:
                str_error = "{} starts at {} on {}".format(name, start, day)

        return str_error

class EditProgramme():
    def __init__(self, programme):
        dialog = gtk.Dialog("Edit Programme", None, 
        0, 
        (gtk.STOCK_SAVE, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        self.programme = programme

        table = gtk.Table(7, 2, False)
        
        code = programme['code']
        day = programme['day']
        start = programme['start']
        name = programme['name']
        presenters = programme ['presenters']
        description = programme['description']


        label_ref_code = gtk.Label("Code")
        table.attach(label_ref_code, 0, 1, 0, 1, False, False, 5, 0)
        label_code = gtk.Label(code)
        table.attach(label_code, 1, 2, 0, 1, False, False, 5, 0)
        
        label_ref_name = gtk.Label("Name")
        table.attach(label_ref_name, 0, 1, 1, 2, False, False, 5, 0)
        self.entry_name = gtk.Entry(36)
        self.entry_name.set_text(name)
        table.attach(self.entry_name, 1, 2, 1, 2, False, False, 5, 0)

        label_ref_day = gtk.Label("Day")
        table.attach(label_ref_day, 0, 1, 2, 3, False, False, 5, 0)
        self.cb_day = gtk.combo_box_new_text()
        common = Common()
        common.cb_setup(self.cb_day)
        day_int = tup_day.index(day)
        self.cb_day.set_active(day_int)
        table.attach(self.cb_day, 1, 2, 2, 3, False, False, 5, 0)

        label_ref_start = gtk.Label("Start Time")
        table.attach(label_ref_start, 0, 1, 3, 4, False, False, 5, 0)
        self.cb_start = gtk.combo_box_new_text()
        timeslot = datetime.time(0, 0)
        add = datetime.timedelta(minutes=30)
        finaltime = datetime.time(23, 30)
        ls_start = []
        self.cb_start.append_text('00:00')
        ls_start.append('00:00')

        while (timeslot != finaltime):
            timeslot = ((datetime.datetime.combine(datetime.date(1,1,1),timeslot)) + add).time()
            timestring = timeslot.strftime("%H:%M")                
            self.cb_start.append_text(timestring)
            ls_start.append(timestring)

        start = start.strftime('%H:%M')
        int_start = ls_start.index(start)
        self.cb_start.set_active(int_start)
        table.attach(self.cb_start, 1, 2, 3, 4, False, False, 5, 0)

        label_ref_pres = gtk.Label("Presenters")
        table.attach(label_ref_pres, 0, 1, 4, 5, False, False, 5, 0)
        self.entry_pres = gtk.Entry(50)
        self.entry_pres.set_text(presenters)
        table.attach(self.entry_pres, 1, 2, 4, 5, False, False, 5, 0)

        label_ref_desc = gtk.Label("Description")
        table.attach(label_ref_desc, 0, 1, 5, 6, False, False, 5, 0)
        self.entry_desc = gtk.Entry(70)
        self.entry_desc.set_editable(True)
        if description:
            self.entry_desc.set_text(description)
        
        table.attach(self.entry_desc, 1, 2, 5, 6, False, False, 5, 0)

        dialog.vbox.pack_start(table, True, True, 0)
        dialog.show_all()
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self.update_programme(None)       
        dialog.destroy()



    def update_programme(self, widget):
        '''
        actions to update the database when the SAVE button is clicked
        '''
        dict_update = self.collect_modified_values()
        check_result = self.check_values(dict_update)
        if check_result:
            print("fail")        
        self.update_database(dict_update)

    def collect_modified_values(self):
        '''
        get values from modifiable items and compare with original values
        return dictionary of modified values
        '''
        code = self.programme["code"]
        dict_update = {"code": code}
        
        name = self.entry_name.get_text()
        if name != self.programme["name"]:
            dict_update["name"] = name

        day = self.cb_day.get_active_text()
        if day != self.programme["day"]:
            dict_update["day"] = day

        start = self.cb_start.get_active_text()
        start = datetime.datetime.strptime(start, "%H:%M")
        orig_start = self.programme["start"]
        if start != orig_start:
            dict_update["start"] = start
        
        presenters = self.entry_pres.get_text()
        if presenters != self.programme["presenters"]:
            dict_update["presenters"] = presenters

        description = self.entry_desc.get_text()
        orig_description = self.programme["description"]
        if not orig_description:
            orig_description = ""
        if description != orig_description:
            dict_update["description"] = description

        return dict_update

    def check_values(self, dict_add):
        '''
        Check that code and day/start are not in use
        '''

        print("work in progress")
        return None



    def update_database(self, dict_update):
        '''
        create and execute the query to update the programme details in the database
        '''
        updates = dict_update.keys()
        updates.remove('code')
        changes = len(updates)

        if changes == 0:
            return

        elif changes == 1:
            update = updates[0]
            query = sql.SQL("UPDATE programmes set {} = {} WHERE code = {}").format(
                sql.Identifier(update),
                sql.Placeholder(name=update),
                sql.Placeholder(name="code")
                )

        else:
            query = sql.SQL("UPDATE programmes SET ({}) = ({}) WHERE code = {}").format(
                sql.SQL(', ').join(map(sql.Identifier, updates)),
                sql.SQL(', ').join(map(sql.Placeholder, updates)),
                sql.Placeholder(name="code")
                )
    
        common = Common()
        conn = common.pg_connect_msg()
        cur = conn.cursor()
        #print(query.as_string(conn))
        cur.execute(query, dict_update)
        conn.commit()
        cur.close()
        conn.close()

class Programmer():
    def __init__(self):
        '''
        Set up the main window and graphical elements
        '''
        self.day_programmes = []
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
        sw.set_size_request(600, 300)
        
        # drop down day selection
        self.cb = gtk.combo_box_new_text()
        common = Common()
        common.cb_setup(self.cb)


        # buttons
        btn_info = gtk.Button(stock=gtk.STOCK_INFO)
        btn_info.set_tooltip_text("Show information about the selected programme")
        btn_edit = gtk.Button(stock=gtk.STOCK_EDIT)
        btn_edit.set_tooltip_text("Edit the selected programme")
        btn_add = gtk.Button(stock=gtk.STOCK_ADD)
        btn_add.set_tooltip_text("Add a new programme")
        btn_del = gtk.Button(stock=gtk.STOCK_DELETE)
        btn_del.set_tooltip_text("Delete the selected programme")
        
        #make the list
        store = gtk.ListStore(str, str, str, str)         
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
        column = gtk.TreeViewColumn('Code', gtk.CellRendererText(),
                                     text=1)
        column.set_sort_column_id(1)
        treeview.append_column(column)

        # column THREE
        column = gtk.TreeViewColumn('Title', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)        
        treeview.append_column(column)

        # column FOUR
        column = gtk.TreeViewColumn('Presenters', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)        
        treeview.append_column(column)


    def dialog_info(self, widget):
        '''
        Open a dialog window with details for the selected programme
        '''
        treeselection = self.treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        code = model.get_value(tree_iter, 1)
        programme = next(
            item for item in self.day_programmes if item["code"] == code
            )
        
        programme_info = ProgrammeInfo(programme)
        programme_info
    
    def dialog_edit(self, widget):
        '''
        Open a dialog window to enable editing of the selected programme
        '''
        treeselection = self.treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        code = model.get_value(tree_iter, 1)
        programme = next(
            item for item in self.day_programmes if item["code"] == code
            )
        
        edit_programme = EditProgramme(programme)
        edit_programme
        self.show_programmes(self.cb)


    def dialog_add(self, widget):
        '''
        Open a dialogue window to add a new programme
        '''
        add_programme = AddProgramme()
        add_programme
        self.show_programmes(self.cb)

    def dialog_delete(self, widget):
        '''
        Open a confirm message and delete the selected programme
        '''
        treeselection = self.treeview.get_selection()
        model, tree_iter = treeselection.get_selected()
        code = model.get_value(tree_iter, 1)
        programme = next(
            item for item in self.day_programmes if item["code"] == code
            )
        delete_programme = DeleteProgramme(programme)
        delete_programme
        self.show_programmes(self.cb)

    def show_programmes(self, widget):
        '''
        Get the selected day of the week from the drop down list
        Populate the programme list from the selected day
        '''
        self.day_programmes = []
        day = widget.get_active_text()
        db, query, search_terms = self.get_programmes_query(day)
        programmes = self.execute_query(db, query, search_terms)
        #programmes = [{k:v for k, v in record.items()} for record in programmes]

        for programme in programmes:
            self.day_programmes.append(programme)

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
            common = Common()
            conn = common.pg_connect_msg()
        
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
        model.clear()
        six_am = datetime.time(6)

        for programme in programmes:
            start = programme['start']
            if start >= six_am:
                start = start.strftime("%H:%M")
                code = programme['code']
                name = programme['name']
                presenters = programme['presenters']
                model.append((start, code, name, presenters))
        
        for programme in programmes:
            start = programme['start']
            if start < six_am:
                start = start.strftime("%H:%M")
                code = programme['code']
                name = programme['name']
                presenters = programme['presenters']
                model.append((start, code, name, presenters))


Programmer()
gtk.main()
