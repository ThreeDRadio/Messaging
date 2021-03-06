#!/usr/bin/env python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, GdkPixbuf
import datetime

import queries

query = queries.Queries()

#import dialogs
#from dialogs import ComputerList



class Player(object):
    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file('player.glade')
        self.builder.connect_signals(self)
        go = self.builder.get_object
        
        # Main window widgets
        self.window = go("window")
        self.box_msgtype = go('box_msgtype')  
        self.make_buttons()     
        # Messages widgets
        self.liststore_msg = go("liststore_msg")
        self.treeview_msg = go('treeview_msg')
        self.create_msg_columns()   
        self.displayed_messages = []
        
        # Schedule widgets
        self.liststore_sch = go("liststore_sch")
        self.treeview_sch = go('treeview_sch')
        self.create_sch_columns()   
        self.show_schedule()
        
        self.window.show_all()
        
        
    def make_buttons(self):
        '''
        create a button for each type of message
        '''
        ls_btn = self.box_msgtype.get_children()
        if ls_btn:
            for item in ls_btn:
                self.box_msgtype.remove(item)
                
        type_rows = query.get_types()

        for msg_type in type_rows:
            button_id = msg_type['type']
            self.button = Gtk.Button.new_with_label(button_id)
            #button.set_size_request(215, 30)
            #size fill as True, expand as False
            tooltip = msg_type['description']
            self.button.set_tooltip_text(tooltip)
            #button.connect("clicked", self.msg_btn_clicked, button_id)
            self.button.connect("clicked", self.on_button_msg_clicked, button_id)
            self.box_msgtype.pack_start(self.button, False, True, 0)
        
        # Messages widgets

        
        # Music Catalogue widgets

        
        # Load Playlist widgets




    # ----- Window signal handlers -----

    def on_window_destroy(self, widget):
        Gtk.main_quit()

    def on_button_msg_clicked(self, widget, button_id):
        print(button_id)
        self.list_messages(button_id)
        
    def on_button_sch_now_clicked(self, widget): 
        print("on_button_sch_now_clicked")   
        # update the schedule and display the current time slot

    def on_button_sch_add_clicked(self, widget): 
        print("on_button_sch_add_clicked")
        # add the selected message to the broadcast list

    def on_togglebutton_pre_playpause_toggled(self, widget): 
        print("on_togglebutton_pre_playpause_toggled")
        # play/pause the selected item

    def on_button_pre_stop_clicked(self, widget): 
        print("on_button_pre_stop_clicked")
        # stop playing

    def on_button_brc_skip_clicked(self, widget): 
        print("on_button_brc_skip_clic  ked")
        # stop playing the broadcasted item

    def on_button_info_clicked(self, widget): 
        print("on_button_info_clicked")
        # display details of selected item

    def on_button_remove_clicked(self, widget): 
        print("on_button_remove_clicked")
        # remove selected item from the brc list

    def on_button_msg3_clicked(self, widget): 
        print("on_button_msg3_clicked")
        # display information of messages played in past 3 hours

    def on_button_history_clicked(self, widget): 
        print("on_button_history_clicked")
        # show details of the last few broadcast items

    def on_button_cat_simple_clicked(self, widget): 
        print("on_button_cat_simple_clicked")
        # simple search of music catalogue

    def on_button_cat_adv_clicked(self, widget): 
        print("on_button_cat_adv_clicked")
        # advanced search of music catalogue

    def on_button_list_all_clicked(self, widget): 
        print("on_button_list_all_clicked")
        # add all items to the broadcast list

    def on_button_list_sel_clicked(self, widget): 
        print("on_button_list_sel_clicked")
        # add selected items to the broadcast list

    def on_notebook_change_current_page(self, widget): 
        print("on_notebook_change_current_page")
        # refresh/update playlist selection treeview

    def on_scale_pre_move_slider(self, widget): 
        print("on_scale_pre_move_slider")
        # move to relative place in the audio file


    # ----- Message Tab -----

    def create_msg_columns(self):
        '''
        columns for the list of messages
        '''
        # column ZERO
        column = Gtk.TreeViewColumn('Code', Gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_clickable(True)
        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        self.treeview_msg.append_column(column)
        
        #Column ONE
        column = Gtk.TreeViewColumn('Message', Gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_clickable(True)
        column.set_expand(True)
        self.treeview_msg.append_column(column)
        
        #Column TWO
        column = Gtk.TreeViewColumn('Ending', Gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        column.set_expand(True)
        self.treeview_msg.append_column(column)
        
        #Column THREE
        column = Gtk.TreeViewColumn('Time', Gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(True)
        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        self.treeview_msg.append_column(column)
        

    def list_messages(self, msgtype):
        '''
        get messages of the selected type and display as a list
        '''
        self.liststore_msg.clear()
        messages = query.get_messages(msgtype)
        for message in messages:
            self.displayed_messages.append(dict(message))
            code = message['code']
            title = message['title']
            nq = message['nq']
            duration = message['duration']
            
            if duration:
                str_duration = self.convert_time(duration)
            else:
                str_duration = "NA"
                
            row = (code, title, nq, str_duration)
            self.liststore_msg.append(row)

    #-------- Schedule ----------
    
    def create_sch_columns(self):
        # column ZERO
        column = Gtk.TreeViewColumn('Time', Gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        column.set_clickable(False)
        column.set_expand(False)
        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        self.treeview_sch.append_column(column)
        
        #Column ONE
        column = Gtk.TreeViewColumn('Program', Gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        column.set_expand(True)
        column.set_clickable(False)
        column.set_resizable(True)
        self.treeview_sch.append_column(column)
        
        #Column TWO
        column = Gtk.TreeViewColumn('ID Code', Gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_clickable(False)
        column.set_expand(False)
        self.treeview_sch.append_column(column)
        
        #Column THREE
        column = Gtk.TreeViewColumn('Message', Gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_resizable(True)
        column.set_clickable(False)
        self.treeview_sch.append_column(column)
        
        #Column FOUR
        column = Gtk.TreeViewColumn('Length', Gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        column.set_expand(False)
        column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        self.treeview_sch.append_column(column)
        
        
    def show_schedule(self):
        '''
        get messages of the selected type and display as a list
        Creates a list of half hour time slots. Adds programmes and 
        scheduled messages        
        '''
        self.liststore_sch.clear()
        schedule = query.get_schedule()
        programmes = query.get_programmes()
        timeslot = datetime.time(6, 0)
        add = datetime.timedelta(minutes=30)
        finaltime = datetime.time(5, 30)
        time_list = [["06:00", "", "", "", ""]]

        while (timeslot != finaltime):
            timeslot = ((datetime.datetime.combine(datetime.date(1,1,1),timeslot)) + add).time()
            timestring = timeslot.strftime("%H:%M")
            row = [timestring,  "", "", "", ""]
            time_list.append(row)
        
        n = 0    
        for row in time_list:
            #check if there is a programme starting at that time
            n+=1
            m = n
            starttime = row[0]
            
            for prog in programmes:
                prog_time = (prog['start']).strftime('%H:%M')

                if prog_time==starttime:
                   row[1] = prog['name']
            #then check if there are messages scheduled for that time
         
            for msg in schedule:                
                # modify duration                
                msg_sch_time = (msg['time_date']).strftime('%H:%M')
                duration = msg['duration'] 
                
                if duration:
                    str_duration = self.convert_time(duration)
                else:
                    str_duration = "NA"
                                
                if msg_sch_time==starttime:
                    if row[2] == "":
                        row[2] = msg['msg_code']
                        row[3] = msg['title']
                        row[4] = str_duration      

                    else:
                        time_list.insert(m, [
                            "", 
                            "", 
                            msg['msg_code'], 
                            msg['title'], 
                            msg['duration']
                            ])
                m+=1
        
        for row in time_list:
            self.liststore_sch.append(row)    

    #common functions
    def convert_time(self, duration):
        s = int(duration)
        m,s = divmod(s, 60)

        if m < 60:
            str_duration = "%02i:%02i" %(m,s)
            return str_duration
        else:
            h,m = divmod(m, 60)
            str_duration = "%i:%02i:%02i" %(h,m,s)
            return str_duration   



if __name__ == "__main__":
    gui = Player()
    Gtk.main()
