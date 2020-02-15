#!/usr/bin/python
'''messager-0.6.py
Manage scheduled messages. Add new messages, 
modify or delete existing messages.
change in v0.6 - enable change of message type
change in v0.7 - fix show information last played
add how often played and date created
'''
import pygtk
import gtk
import gobject
import pango
import sys
import psycopg2
import datetime
import calendar
import os
import time
import gst
import pygst
import threading
import thread
import subprocess
import shutil
import ConfigParser

config = ConfigParser.SafeConfigParser()
#get variables from config file
config = ConfigParser.SafeConfigParser()
config.read('/usr/local/etc/threedradio.conf')

dir_msg = config.get('Paths', 'dir_msg')
dir_backup = config.get('Paths', 'dir_backup')
dir_img = config.get('Paths', 'dir_img')
logo = config.get('Images', 'logo')

pg_user = config.get('Messager', 'pg_user')
pg_password = config.get('Messager', 'pg_password')
pg_server = config.get('Common', 'pg_server')
pg_msg_database = config.get('Common', 'pg_msg_database')

header_font = pango.FontDescription("Sans Bold 14")
subheader_font = pango.FontDescription("Sans Bold 12")

class ShowInfo():
    def __init__(self, msg_info):
        dialog = gtk.Dialog("Show Information", None, 0, (
            gtk.STOCK_OK, gtk.RESPONSE_OK))   
            
        self.messager = Messager()

        table_msg = gtk.Table(12, 2, False)

        code = msg_info[0]
        title = msg_info[1]
        msg_type = msg_info[2]
        nq = msg_info[3]
        expiry = self.format_expiry(msg_info[4])
        filename = msg_info[5]
        producer = msg_info[6]
        dur = msg_info[7]
        if dur:
            dur = self.format_dur(int(dur))
        else:
            dur = "N/A"

        created = msg_info[8]
        last_played = self.last_played(code)
        frequency = self.frequency(code) + " times"
        
        label_code0 = gtk.Label("ID Code: ")
        label_code1 = gtk.Label(code)
        label_title0 = gtk.Label("Message Title: ")
        label_title1 = gtk.Label(title)
        label_msg_type0 = gtk.Label("Message Type: ")
        label_msg_type1 = gtk.Label(msg_type)
        label_nq0 = gtk.Label("End Cue: ")
        label_nq1 = gtk.Label(nq)        
        label_expiry0 = gtk.Label("Expiry Date: ")
        label_expiry1 = gtk.Label(expiry)
        label_filename0 = gtk.Label("Audio File: ")
        label_filename1 = gtk.Label(filename)        
        label_producer0 = gtk.Label("Producer: ")
        label_producer1 = gtk.Label(producer)
        label_dur0 = gtk.Label("Duration: ")
        label_dur1 = gtk.Label(dur)
        label_created0 = gtk.Label("Created: ")
        label_created1 = gtk.Label(created)
        label_last_played0 = gtk.Label("Last Played: ")
        label_last_played1 = gtk.Label(last_played)
        label_frequency0 = gtk.Label("How often played: ")
        label_frequency1 = gtk.Label(frequency)

        table_msg.attach(label_code0, 0, 1, 0, 1, True, True, 5, 5)
        table_msg.attach(label_code1, 1, 2, 0, 1, True, True, 5, 5)
        table_msg.attach(label_title0, 0, 1, 1, 2, True, True, 5, 5)
        table_msg.attach(label_title1, 1, 2, 1, 2, True, True, 5, 5)
        table_msg.attach(label_msg_type0, 0, 1, 3, 4, True, True, 5, 5)
        table_msg.attach(label_msg_type1, 1, 2, 3, 4, True, True, 5, 5)
        table_msg.attach(label_nq0, 0, 1, 4, 5, True, True, 5, 5)
        table_msg.attach(label_nq1, 1, 2, 4, 5, True, True, 5, 5)
        table_msg.attach(label_expiry0, 0, 1, 5, 6, True, True, 5, 5)
        table_msg.attach(label_expiry1, 1, 2, 5, 6, True, True, 5, 5)
        table_msg.attach(label_filename0, 0, 1, 6, 7, True, True, 5, 5)
        table_msg.attach(label_filename1, 1, 2, 6, 7, True, True, 5, 5)
        table_msg.attach(label_producer0, 0, 1, 7, 8, True, True, 5, 5)
        table_msg.attach(label_producer1, 1, 2, 7, 8, True, True, 5, 5)
        table_msg.attach(label_dur0, 0, 1, 8, 9, True, True, 5, 5)
        table_msg.attach(label_dur1, 1, 2, 8, 9, True, True, 5, 5)
        table_msg.attach(label_created0, 0, 1, 9, 10, True, True, 5, 5)
        table_msg.attach(label_created1, 1, 2, 9, 10, True, True, 5, 5)
        table_msg.attach(label_last_played0, 0, 1, 10, 11, True, True, 5, 5)
        table_msg.attach(label_last_played1, 1, 2, 10, 11, True, True, 5, 5)        
        table_msg.attach(label_frequency0, 0, 1, 11, 12, True, True, 5, 5)
        table_msg.attach(label_frequency1, 1, 2, 11, 12, True, True, 5, 5)
                
        dialog.vbox.pack_start(table_msg, True, True, 0)
        dialog.show_all()
        dialog.run()    
        dialog.destroy()        
        
    def format_expiry(self, expiry):
        dt = datetime.datetime.strptime(expiry, "%Y-%m-%d")
        expiry = datetime.datetime.strftime(dt, "%d/%m/%Y")
        return expiry
    def format_dur(self, dur):
        m,s = divmod(dur, 60)
        if m < 60:
            str_dur = "%02i:%02i" %(m,s)
            return str_dur
        else:
            h,m = divmod(m, 60)
            str_dur = "%i:%02i:%02i" %(h,m,s)
            return str_dur
        return str_dur
        
    def last_played(self, code):
        query = "select when_played from playlog where id_type='msg' AND id_code='{0}' ORDER BY when_played DESC  LIMIT 1".format(code)
        conn = self.messager.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        tup_last_played = cur.fetchall()
        if tup_last_played:
            last_played = tup_last_played[0][0].strftime("%c")
        else:
            last_played = "Not Available"
        cur.close()
        conn.close()
        return last_played

    def frequency(self,code):
        query = "SELECT COUNT (*) FROM playlog WHERE id_code='{0}'".format(code)
        conn = self.messager.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        frequency = str(cur.fetchall()[0][0])
        cur.close()
        conn.close()
        return frequency
            
    def filetime(self,filename, msg_type):
        print("In Progress")
        
class ChangeMessage():
    def __init__(self, msg_info):
        dialog = gtk.Dialog("Change Message", None, 0, (
            gtk.STOCK_OK, gtk.RESPONSE_OK, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        self.messager = Messager()
        self.filepath_new = False
        print(msg_info)
        table_msg = gtk.Table(8, 2, False)
        hbox_filename = gtk.HBox(False, 0)
        self.msg_info = msg_info
        self.idcode = msg_info[0]
        self.title = msg_info[1]
        self.msg_type = msg_info[2]
        self.nq = msg_info[3]
        self.expiry = msg_info[4]
        self.filename = msg_info[5]        
        self.producer = msg_info[6]
        self.dur = str(msg_info[7])
        
        header = "ID Code: {0}".format(self.idcode)
        label_header = gtk.Label(header)
        label_header.modify_font(subheader_font)
        
        label_type = gtk.Label("Message Type")
        
        self.cb_msg = gtk.combo_box_new_text()
        self.make_type_cb()
        
        self.label_filename = gtk.Label(self.filename)
        self.label_dur_blank0 = gtk.Label("    ")
        self.label_dur_blank1 = gtk.Label("    ")
        self.label_dur = gtk.Label(self.dur)
        self.label_dur_sec= gtk.Label("sec")
        btn_filename = gtk.Button("Audio File")
        btn_filename.connect("clicked", self.select_file) 
        
        label_title = gtk.Label("Message Title")
        self.entry_title=gtk.Entry(30)
        self.entry_title.set_text(self.title)  
          
        label_nq = gtk.Label("End Cue")
        self.entry_nq = gtk.Entry(30)        
        self.entry_nq.set_text(self.nq)
        
        label_expiry = gtk.Label("Expiry Date")
        self.entry_expiry = gtk.Entry(10)
        expiry = self.format_expiry(self.expiry)       
        self.entry_expiry.set_text(expiry)
        
        label_prod = gtk.Label("Producer")
        self.entry_prod = gtk.Entry(50)        
        self.entry_prod.set_text(self.producer)
        
        btn_change = gtk.Button("Change")
        btn_change.set_size_request(180, 30)
        btn_change.modify_font(subheader_font)
        btn_change.connect("clicked", self.change_message)
        
        hbox_filename.pack_start(btn_filename, False)
        hbox_filename.pack_start(self.label_dur_blank0, True)
        hbox_filename.pack_start(self.label_filename, True)
        hbox_filename.pack_end(self.label_dur_sec, True)
        hbox_filename.pack_end(self.label_dur, True)
        hbox_filename.pack_end(self.label_dur_blank1, True)

        table_msg.attach(label_header, 0, 2, 0, 1, True, True, 0, 5)
        table_msg.attach(label_type, 0, 1, 1, 2, True, True, 0, 0)
        table_msg.attach(self.cb_msg, 1, 2, 1, 2, True, True, 5, 0)
        table_msg.attach(hbox_filename, 0, 2, 2, 3, True, True, 0, 0)
        table_msg.attach(label_title, 0, 1, 3, 4, True, True, 0, 0)
        table_msg.attach(self.entry_title, 1, 2, 3, 4, True, True, 0, 0)
        table_msg.attach(label_nq, 0, 1, 4, 5, True, True, 0, 0)
        table_msg.attach(self.entry_nq, 1, 2, 4, 5, True, True, 0, 0)
        table_msg.attach(label_expiry, 0, 1, 5, 6, True, True, 0, 0)
        table_msg.attach(self.entry_expiry, 1, 2, 5, 6, True, True, 0, 0)
        table_msg.attach(label_prod, 0, 1, 6, 7, True, True, 0, 0)
        table_msg.attach(self.entry_prod, 1, 2, 6, 7, True, True, 0, 0)
        table_msg.attach(btn_change, 0, 2, 7, 8, True, True, 5, 5)
       
        dialog.vbox.pack_start(table_msg, True, True, 0)
        dialog.show_all()

        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self.change_message(None)       
        dialog.destroy()
    
    def make_type_cb(self):
        type_rows = self.messager.get_types()
        msg_types = [i[0] for i in type_rows]

        for item in msg_types:
            self.cb_msg.append_text(item)
        cb_index = msg_types.index(self.msg_type)
        self.cb_msg.set_active(cb_index) 
    
    def format_expiry(self, expiry):
        dt = datetime.datetime.strptime(expiry, "%Y-%m-%d")
        expiry = datetime.datetime.strftime(dt, "%d/%m/%Y")
        return expiry
        
    def select_file(self, widget):
        self.filepath_new = self.messager.getfile()
        split_filename = os.path.split(self.filepath_new)
        filename = split_filename[-1]    
        
        #calculate duration
        ex = "/opt/local/bin/soxi"
        arg1 = "-D"
        filepath = self.filepath_new
        process = subprocess.Popen([ex,  arg1, filepath], shell=False, stdout=subprocess.PIPE)
        dur = process.communicate()[0]
        try:
            dur_seconds = int(round(float(dur)))
            dur_seconds = str(dur_seconds)
            self.label_dur.set_text(dur_seconds)
            self.label_dur_sec.set_text("  sec  ")
            self.label_filename.set_text(filename)
        except ValueError:
            self.label_dur.set_text("")
            str_error = "This does not appear to be a valid audio file"
            self.messager.error_dialog(str_error)
            

    def change_message(self, widget):
        #Check which fields have changed
        msg_type = self.cb_msg.get_active_text()
        print(msg_type)
        if msg_type == self.msg_type:
            msg_type = ""
        filename = self.label_filename.get_text()
        if filename == self.filename:
            filename = ""
        dur = self.label_dur.get_text()
        if dur == self.dur:
            dur = ""
        else:
            dur = int(dur)
        title = self.entry_title.get_text()
        if title == self.title:
            title = ""
        nq = self.entry_nq.get_text()
        if nq == self.nq:
            nq = ""
        expiry = self.entry_expiry.get_text()
        if expiry == self.expiry:
            expiry = ""
        producer = self.entry_prod.get_text()
        if producer == self.producer:
            producer = ""
        
        fields = dict([
            ("type", msg_type),
            ("filename", filename), 
            ("duration", dur), 
            ("title", title), 
            ("nq", nq), 
            ("expirydate", expiry),
            ("fldproducer", producer)
            ])
            
        self.make_change(fields)
        
        self.dialog_added()

        
    def make_change(self, fields):
        
        if self.filepath_new:
            filename_old = self.filename
            filepath_new = self.filepath_new
            self.replace_file(filename_old, filepath_new)

        conn = self.messager.pg_connect_msg()
        cur = conn.cursor()
        
        for item in fields:
            val = fields[item]
            if val:
                cur = conn.cursor()
                str_set = "UPDATE messagelist SET {0}=" .format(item)
                str_code = "'{0}'".format(self.idcode)

                query = "UPDATE messagelist SET %s=" % (item) + '%s WHERE code=%s'

                cur.execute(query, (val, self.idcode))
 
        conn.commit() 
        cur.close()
        conn.close()
        
        msg_type = fields["type"]
        if msg_type:
            print("the message type listed here is " + msg_type)
            self.change_msg_type(msg_type)

    def replace_file(self, filename_old, filepath_new):
        '''
        archive the old audio file and copy over the new one.
        '''
        dt = datetime.datetime.now()
        dir_date = datetime.datetime.strftime(dt, "%Y%m")
        
        # the folder where the old audio file will be moved
        path_backup = os.path.join(dir_backup, dir_date)
        
        type_12 = self.msg_type[0:12]
        type_12 = type_12.lower()

        # the folder in which the audio file is kept
        audio_location = os.path.join(dir_msg, type_12)
        
        # full path of the old audio file
        audiofile_old = os.path.join(audio_location, filename_old)

        # name of the new audio file
        filename_new = os.path.basename(filepath_new)

        # destination path for new audio file including name of the file
        path_dest = os.path.join(dir_msg, type_12, filename_new)

        # full destination path for the old audio file including name of the file
        backed_up = os.path.join(path_backup, filename_old)

        # does the backup folder exist? If not, create
        if not os.path.isdir(path_backup):
            os.mkdir(path_backup)
        
        # is there already a backup of the old audio file name?
        # if so, add timestamp to old filename
        if os.path.exists(backed_up):
            now = datetime.datetime.strftime(dt, "%y%m%d%H%M")
            filenow = filename_old + now
            backed_up = os.path.join(path_backup, filenow)
        
        # move the old file if it exists
        if os.path.exists(audiofile_old):
            shutil.move(audiofile_old, backed_up)
            
        # copy the new file over
        shutil.copyfile(filepath_new, path_dest)
        
    
    def change_msg_type(self, msg_type):
        # create the new path from the msg_type
        # obtain the existing path from either 
        #      self.filepath_new (if file was changed)
        # or
        #      adding self.msg_type and self.filename
 
        type_12 = self.msg_type[0:12]
        type_12 = type_12.lower()
        
        new_type_12 = msg_type[0:12]
        new_type_12 = new_type_12.lower()
        
        if self.filepath_new:
            filename_move = os.path.basename(self.filepath_new)
        else:
            filename_move = self.filename
            
        path_src = os.path.join(dir_msg, type_12, filename_move)
        path_dest = os.path.join(dir_msg, new_type_12, filename_move)
        print("moving file from " + path_src + " to " + path_dest)
        
                #check that expiry date is valid 
        try:
            shutil.copyfile(path_src, path_dest)
        except IOError:
            str_error = "There was a problem relocating the file to the new folder, please see a station Tech."
            self.messager.error_dialog(str_error)
            return
            
    def dialog_added(self):
        str_info = "Message Changed"
        self.messager.info_dialog(str_info)
        
class NewMessage:
    def __init__(self):
        dialog = gtk.Dialog("New Message", None, 0, (
            gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE, gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        
        self.messager = Messager()
        self.filepath_new = False
        # table for buttons and drop-down list
        table_msg = gtk.Table(8, 2, False)
        
        hbox_filename = gtk.HBox(False, 0)
        
        #labels 
        label_add = gtk.Label("Add New Message")
        #label_add.modify_font(subheader_font)
        label_type = gtk.Label("Message Type")
        
        self.cb_msg = gtk.combo_box_new_text()
        self.make_type_cb()
        
        label_title = gtk.Label("Message Title")
        self.entry_title=gtk.Entry(30)
 
        label_code = gtk.Label("Message Code")
        self.entry_code = gtk.Entry(6)
        
        label_nq = gtk.Label("End Cue")
        self.entry_nq = gtk.Entry(30)
        
        label_expiry = gtk.Label("Expiry Date")
        self.entry_expiry = gtk.Entry(10)
        next_month = self.get_next_month()
        self.entry_expiry.set_text(next_month)
        
        self.label_filename = gtk.Label("Audio File")
        self.label_dur_blank0 = gtk.Label("    ")
        self.label_dur_blank1 = gtk.Label("    ")
        self.label_dur = gtk.Label("")
        self.label_dur_sec= gtk.Label("")
        btn_filename = gtk.Button("Select")
        btn_filename.connect("clicked", self.select_file)
        
        label_prod = gtk.Label("Producer")
        self.entry_prod = gtk.Entry(50)   
        
        btn_add = gtk.Button("Add")
        btn_add.connect("clicked", self.add_message)
        
        hbox_filename.pack_start(btn_filename, False)
        hbox_filename.pack_start(self.label_dur_blank0, True)
        hbox_filename.pack_start(self.label_filename, True)
        hbox_filename.pack_end(self.label_dur_sec, True)
        hbox_filename.pack_end(self.label_dur, True)
        hbox_filename.pack_end(self.label_dur_blank1, True)
                
        table_msg.attach(label_add, 0, 2, 0, 1, False, False, 0, 5)
        table_msg.attach(label_type, 0, 1, 1, 2, False, False, 0, 0)
        table_msg.attach(self.cb_msg, 1, 2, 1, 2, True, True, 5, 0)
        table_msg.attach(label_code, 0, 1, 2, 3, False, False, 0, 0)
        table_msg.attach(self.entry_code, 1, 2, 2, 3, True, True, 0, 0)
        table_msg.attach(label_title, 0, 1, 3, 4, False, False, 0, 0)
        table_msg.attach(self.entry_title, 1, 2, 3, 4, True, True, 0, 0)
        table_msg.attach(label_nq, 0, 1, 4, 5, False, False, 0, 0)
        table_msg.attach(self.entry_nq, 1, 2, 4, 5, True, True, 0, 0)
        table_msg.attach(label_expiry, 0, 1, 5, 6, False, False, 0, 0)
        table_msg.attach(self.entry_expiry, 1, 2, 5, 6,  True, True, 0, 0)
        table_msg.attach(hbox_filename, 0, 2, 6, 7, True, True, 0, 0)
        table_msg.attach(label_prod, 0, 1, 7, 8, False, False, 0, 0)
        table_msg.attach(self.entry_prod, 1, 2, 7, 8,  True, True, 0, 0)
        
        
        
        dialog.vbox.pack_start(table_msg, True, True, 0)
        dialog.vbox.pack_start(btn_add, False, False, 0)
        dialog.show_all()
        dialog.run()    
        dialog.destroy()

    def make_type_cb(self):
        type_rows = self.messager.get_types()
        for item in type_rows:
            self.cb_msg.append_text(item[0])

    def select_file(self, widget):
        self.filepath_new = self.messager.getfile()
        split_filename = os.path.split(self.filepath_new)
        filename = split_filename[-1]
        if len(filename) > 32:
            str_error = "The name of your file is too long. It must be 32 characters or less"
            self.messager.error_dialog(str_error)

        
        #calculate duration
        ex = "/opt/local/bin/soxi"
        arg1 = "-D"
        filepath = self.filepath_new
        print(filepath)
        process = subprocess.Popen([ex,  arg1, filepath], shell=False, stdout=subprocess.PIPE)
        dur = process.communicate()[0]
        try:
            dur_seconds = int(round(float(dur)))
            dur_seconds = str(dur_seconds)
            self.label_dur.set_text(dur_seconds)
            self.label_dur_sec.set_text("  sec  ")
            self.label_filename.set_text(filename)
        except ValueError:
            self.label_dur.set_text("")
            str_error = "This does not appear to be a valid audio file"
            self.messager.error_dialog(str_error)

    def get_next_month(self):
        ''''
        thanks Dave Webb on Stack Overflow site
        http://stackoverflow.com/questions/4130922/how-to-increment-datetime-month-in-python
        '''
        sourcedate = datetime.datetime.today()
        months = 1
        month = sourcedate.month - 1 + months
        year = sourcedate.year + month / 12
        month = month % 12 + 1
        day = min(sourcedate.day,calendar.monthrange(year,month)[1])
        next_month = "{0}/{1}/{2}".format(day, month, year)
        return next_month
            
    def add_message(self, widget):
        msg_type = self.cb_msg.get_active_text()
        title = self.entry_title.get_text()
        code = self.entry_code.get_text()        
        nq = self.entry_nq.get_text()
        expiry_date = self.entry_expiry.get_text()
        filepath = self.filepath_new
        producer = self.entry_prod.get_text()
        dur = int(self.label_dur.get_text())
        created = datetime.datetime.now()
        
        #check the type 
        if not msg_type:
            str_error = "Message not added. You need to select a message type"
            self.messager.error_dialog(str_error)
            return   
        #chack if the title is blank
        if not title:
            str_error = "Message not added. You need enter a title"
            self.messager.error_dialog(str_error)
            return            
        #check if code is in use or blank
        if code:
            code = code.upper()
            check_code = self.check_code(code)
            if check_code:
                str_error = "Message not added. The ID code is in use. Enter a unique ID code"
                self.messager.error_dialog(str_error)
                return
        else:
            str_error = "Message not added. You need enter a unique ID code for the message"
            self.messager.error_dialog(str_error)
            return                   
        
        #check that the nq is not blank
        if not nq:
            str_error = "Message not added. You need enter an end cue for the message"
            self.messager.error_dialog(str_error)
            return
        #check that expiry date is valid 
        try:
            dt_expiry = datetime.datetime.strptime(expiry_date, "%d/%m/%Y")
        except ValueError:
            str_error = "Message not added - invalid expiry date. Please enter a valid date dd/mm/yyyy"
            self.messager.error_dialog(str_error)
            return
                
        #check if the filepath exists and the name is not duplicate
        if not filepath:
            str_error = "Message not added - you need to select where the file is located"
            self.messager.error_dialog(str_error)
            return
        else:
            filename = self.label_filename.get_text() 
            if filename == "Audio File":
                str_error = "Message not added - you need to select where the file is located"
            else:
                type_12 = msg_type[0:12]
                type_12 = type_12.lower()
                destination_filepath = dir_msg + type_12 + "/" + filename
                if os.path.isfile(destination_filepath) and not filepath == destination_filepath:
                    str_error = "Message not added - the file '{0}' exists in the '{1}' folder".format(
                        filename, type_12)
                    self.messager.error_dialog(str_error)
                    return
        
        #check that the producer is not blank
        if not producer:
            str_error = "Message not added. Please enter your name as producer"
            self.messager.error_dialog(str_error)
            return        
        
        #check that the duration is correct
        if not dur:
            str_error = "You need to select a valid audio file"
            self.messager.error_dialog(str_error) 
            return          

        if not filepath == destination_filepath:
            self.copy_file(filepath, type_12)

        self.add_to_db(msg_type, title, code, nq, expiry_date, filename, producer, dur, created)
        self.dialog_added()
        self.clear_fields()
        
    def check_msg_type(self, msg_type):
        query = "select * from typelist where type='{0}'".format(msg_type)
        conn = self.messager.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        if result:
            return True
        else:
            return False

    def check_code(self, code):
        query = "select * from messagelist where code='{0}'".format(code)
        conn = self.messager.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        if result:
            return True
        else:
            return False
            
    def copy_file(self, filepath, type_12):
        filename = os.path.basename(filepath)
        path_dest = os.path.join(dir_msg, type_12, filename)
        print("Destination path is")
        print(path_dest)
        shutil.copyfile(filepath, path_dest)
    
    def add_to_db(self, msg_type, title, code, nq, expiry_date, filename, producer, dur, created):
        expiry_date = datetime.datetime.strptime(expiry_date, "%d/%m/%Y")
        col_items = '(code, title, type, nq, expirydate, filename, fldproducer, duration, created)'
        
        
        #query = "INSERT INTO messagelist (code, title, type, nq, expirydate, filename, fldproducer, duration) VALUES ('{0}', '{1}', '{2}', '{3}', '{4}', '{5}', '{6}', '{7}')".format(
        #    code, title, msg_type, nq, expiry_date, filename, producer, dur)
        
        val_items = (code, title, msg_type, nq, expiry_date, filename, producer, dur, created)

        SQL = "INSERT INTO messagelist" + col_items + \
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)" 

        conn = self.messager.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(SQL, val_items)
        conn.commit()
        cur.close()
        conn.close()            
    
    def clear_fields(self):
        self.entry_title.set_text("")
        self.entry_code.set_text("")
        self.entry_nq.set_text("")
        next_month = self.get_next_month()
        self.entry_expiry.set_text(next_month)
        self.label_filename.set_text("Audio File")
        self.label_dur.set_text("")
        self.label_dur_sec.set_text("")
        self.entry_prod.set_text("")

        type_12 = ""
        msg_type = ""
        title = ""
        code = ""
        nq = ""
        expiry_date = ""
        producer = "" 
        dur = 0
        filename = ""
        filepath = ""
        
    def dialog_added(self):
        str_info =  "Message Added"
        self.messager.info_dialog(str_info)

class NewType():
    def __init__(self):
        dialog = gtk.Dialog("New Message Type", None, 10, (
            gtk.STOCK_CLOSE, gtk.RESPONSE_CANCEL, 
            gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        self.messager = Messager()
        
        label_type = gtk.Label("Name of the new message type")
        self.entry_type = gtk.Entry(max=20)
        self.entry_type.connect("activate", self.add_type)
        label_desc = gtk.Label("Description of new message type")
        self.entry_desc = gtk.Entry(max=70)
        self.entry_desc.connect("activate", self.add_type)
        btn_new = gtk.Button("Add")
        btn_new.connect("clicked", self.add_type)
        
        dialog.vbox.pack_start(label_type, False, False, 5)
        dialog.vbox.pack_start(self.entry_type, False, False, 5)
        dialog.vbox.pack_start(label_desc, False, False, 5)
        dialog.vbox.pack_start(self.entry_desc, False, False, 5)
        dialog.vbox.pack_start(btn_new, False, False, 5)
        
        dialog.show_all()
        dialog.run()    
        dialog.destroy()
    
    def add_type(self, widget):
        msg_type = self.entry_type.get_text()
        desc = self.entry_desc.get_text()
        if not msg_type:
            str_error = "You need to enter the name of the new message type"
            self.messager.error_dialog(str_error)
            return
            
        if not desc:
            str_error = "You need to enter a description of the new message type"
            self.messager.error_dialog(str_error)        
            return
            
        if not self.check_type(msg_type):           
            return
            
        self.make_dir(msg_type)
        self.update_db(msg_type, desc)
        self.entry_type.set_text("")
        self.entry_desc.set_text("")
        str_info = "Message Type '{0}' added successfully".format(msg_type)
        self.messager.info_dialog(str_info)
        
    def check_type(self, msg_type):
        #check no whitespace
        if (' ' in msg_type):
            str_error = "Please use a name with no spaces"
            self.messager.error_dialog(str_error) 
            return False
             
        #check type not existing
        query = "SELECT * FROM typelist WHERE type ILIKE '{0}'".format(msg_type)
        conn = self.messager.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        
        if result:
            str_error = "This type exists. Please choose a different type"
            self.messager.error_dialog(str_error)
            cur.close()
            conn.close()            
            return False
        else:
            return True
         
    def make_dir(self, msg_type):
        type_12 = msg_type[0:12]
        type_12 = type_12.lower()
        filepath = dir_msg + type_12
        if os.path.isdir(filepath):
            return 
        else:
            os.mkdir(filepath)
        
    def update_db(self, msg_type, desc):
        query = "INSERT INTO typelist (type, description) VALUES ('{0}', '{1}')".format(
                msg_type, desc)
    
        conn = self.messager.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        conn.commit()
        cur.close()
        conn.close()

class DeleteType():
    def __init__(self):
        dialog = gtk.Dialog("Delete Message Type", None, 10, (
            gtk.STOCK_CLOSE, gtk.RESPONSE_CANCEL, 
            gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        self.messager = Messager()
        
        label_del = gtk.Label("Select the message type that you wish to remove")
        self.cb_del = gtk.combo_box_new_text()
        self.make_type_cb()
        btn_del = gtk.Button("Delete")
        btn_del.connect("clicked", self.del_type)
        
        dialog.vbox.pack_start(label_del, False, False, 5)
        dialog.vbox.pack_start(self.cb_del, False, False, 5)
        dialog.vbox.pack_start(btn_del, False, False, 5)
        
        dialog.show_all()
        dialog.run()    
        dialog.destroy()

    def del_type(self, widget):
        msg_type = self.cb_del.get_active_text()
        msg_pos =  self.cb_del.get_active()

        if msg_type:
            result = self.query_del(msg_type)
            if result:
                self.remove_dir(msg_type)
                self.cb_del.remove_text(msg_pos)
                
        else:
            str_error = "Select a Message Type from the drop down list"
            self.messager.error_dialog(str_error)

    def query_del(self, msg_type):
        conn = self.messager.pg_connect_msg()
        cur = conn.cursor()
        query_check = "SELECT type from messagelist WHERE type = '{0}'".format(msg_type)
        query_del = "DELETE from typelist WHERE type = '{0}'".format(msg_type)
        cur.execute(query_check)
        result = cur.fetchall()
        
        if result:
            cur.close()
            conn.close()             
            str_error = "You can not delete a message type which contains messages"
            self.messager.error_dialog(str_error)
           
            return False
        else:
            cur.execute(query_del)
            conn.commit()
            cur.close()
            conn.close()             
            str_info = "Message Type {0} deleted"
            self.messager.info_dialog(str_info)
            
            return (True)

    
    def make_type_cb(self):
        type_rows = self.messager.get_types()
        for item in type_rows:
            self.cb_del.append_text(item[0])
            
    def remove_dir(self, msg_type):
        type_12 = msg_type[0:12]
        type_12 = type_12.lower()
        dirpath = "{0}/{1}/".format (dir_msg, type_12)
        contents = os.listdir(dirpath)
        if contents:
            dt = datetime.datetime.now()
            dir_date = datetime.datetime.strftime(dt, "%Y%m")
            path_backup = dir_backup + dir_date
            
            if not os.path.isdir(path_backup):
                os.mkdir(path_backup)
            
            for item in contents:    
                filepath = dirpath + item
                shutil.move(filepath, path_backup)
                
        os.rmdir(dirpath)
               
class Preview_Player:
    '''
    adapted from Benny Malev's DamnSimplePlayer
    '''
    def __init__(self, time_label, hscale, reset_playbutton):
        self.player = gst.element_factory_make("playbin", "player")
        fakesink = gst.element_factory_make("fakesink", "fakesink")
        #sink_pre = gst.element_factory_make("alsasink", "preview_sink")
        #sink_pre.set_property("device", "preview")
        self.player.set_property("video-sink", fakesink)
        #self.player.set_property("audio-sink", sink_pre)
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
        time_int = time_int / 1000000000
        time_str = ""
        if time_int >= 3600:
            _hours = time_int / 3600
            time_int = time_int - (_hours * 3600)
            time_str = str(_hours) + ":"
        if time_int >= 600:
            _mins = time_int / 60
            time_int = time_int - (_mins * 60)
            time_str = time_str + str(_mins) + ":"
        elif time_int >= 60:
            _mins = time_int / 60
            time_int = time_int - (_mins * 60)
            time_str = time_str + "0" + str(_mins) + ":"
        else:
            time_str = time_str + "00:"
        if time_int > 9:
            time_str = time_str + str(time_int)
        else:
            time_str = time_str + "0" + str(time_int)
            
        return time_str
        
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

class Messager():
    
    def delete_event(self, widget, event, data=None):
        return False

    def destroy(self, widget, data=None):
        gtk.main_quit()

    def main(self):
        window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window = window
        window.set_title("Messager")
        filepath_logo = dir_img + logo
        window.set_icon_from_file(filepath_logo)
        window.connect("delete_event", self.delete_event)
        window.connect("destroy", self.destroy) 
        window.set_position(gtk.WIN_POS_CENTER)
        
        
        #variable to hold the filepath of the file to add
        self.filepath_new = False
 
        ###   create containers - boxes and scrolled windows  ###
        #hbox for message buttons and list
        hbox_msg = gtk.HBox(False, 0)
        #hbox for action buttons
        hbox_action = gtk.HBox(False, 0)
        #As above with buttons for message types
        hbox_type_action = gtk.HBox(False, 0)
        #vbox for label and message buttons
        vbox_msg_btn = gtk.VBox(False, 0)
        vbox_msg_btn.set_size_request(240, 640)
        
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
        sw_msg_lst.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)        


        # hbox for preview player buttons
        hbox_pre_btn = gtk.HBox(False, 0)

        
        ###  ------------ Message List Section  ------------ ###
        
        #make the buttons
        self.make_buttons()
        self.message_type = None
  
        #make the list
        self.msg_store = gtk.ListStore(str ,str ,str ,str ,str ,str ,str, str, str, str)
        self.treeview_msg = gtk.TreeView(self.msg_store)
        self.treeview_msg.set_rules_hint(True)
        msg_treeselection = self.treeview_msg.get_selection()
        #msg_treeselection.connect('changed', self.msg_selection_changed)
        self.add_msg_columns(self.treeview_msg)

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
        self.btn_pre_play_pause.connect("clicked", self.play_pause_clicked)
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
        self.hscale_pre.connect("button-release-event", self.on_seek_changed)
        self.hscale_pre.connect("button-press-event", self.progress_pressed)

        # the preview player
        self.player_pre = Preview_Player(
            self.label_pre_time, self.hscale_pre, self.reset_playbutton)
        
        ###  ------------ Action Buttons ------------  ###
        btn_info = gtk.Button("Message Info")
        btn_info.connect("clicked", self.show_info)
        btn_new = gtk.Button("New Message")
        btn_new.connect("clicked", self.new_message)
        btn_change = gtk.Button("Change Selected Message")
        btn_change.connect("clicked", self.change_message)
        btn_del = gtk.Button("Delete Selected Message")
        btn_del.connect("clicked", self.delete_message)
        btn_new_type = gtk.Button("New Message Type")
        btn_new_type.set_sensitive(False)
        btn_new_type.connect("clicked", self.new_type)        
        btn_del_type = gtk.Button("Delete Message Type")
        btn_del_type.set_sensitive(False)
        btn_del_type.connect("clicked", self.del_type)
        
        ###  ------------ do the packing ------------  ###
        sw_msg_lst.add(self.treeview_msg)
        vbox_msg_btn.pack_end(sw_msg_btn, True)
        sw_msg_btn.add_with_viewport(self.vbox_sw_msg_btn)
        hbox_msg.pack_start(vbox_msg_btn, False)
        hbox_pre_btn.pack_start(self.btn_pre_play_pause, False)
        hbox_pre_btn.pack_start(btn_pre_stop, False)
        hbox_pre_btn.pack_start(self.hscale_pre, True)
        hbox_pre_btn.pack_start(self.label_pre_time, True)     
        vbox_msg_lst.pack_start(hbox_pre_btn, False)
        vbox_msg_lst.add(sw_msg_lst)
        vbox_msg_lst.pack_end(hbox_type_action, False)
        vbox_msg_lst.pack_end(hbox_action, False) 
        hbox_msg.add(vbox_msg_lst)
        hbox_action.pack_start(btn_info, False)
        hbox_action.pack_start(btn_new, False)
        hbox_action.pack_start(btn_change, False)
        hbox_action.pack_start(btn_del, False)
        
        hbox_type_action.pack_start(btn_new_type, False)
        hbox_type_action.pack_start(btn_del_type, False)
        
        window.add(hbox_msg)
        window.show_all()
        
        gtk.gdk.threads_init()

        gtk.main()
        
    def pg_connect_msg(self):      
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            pg_msg_database, pg_user, pg_server, pg_password)
        conn = psycopg2.connect(conn_string)
        #cur = conn.cursor()
        return conn
    
    def get_types(self):
        query = "SELECT type,description FROM typelist ORDER BY type"
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        type_rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return type_rows
    
    def make_buttons(self):
        ls_btn = self.vbox_sw_msg_btn.get_children()
        if ls_btn:
            for item in ls_btn:
                self.vbox_sw_msg_btn.remove(item)
                
        print("making the all button")        

        all_button = gtk.Button("All")
        #all_button.set_size_request(215, 24)
        tooltip = "Show all messages"
        all_button.set_tooltip_text(tooltip)
        all_button.connect("clicked", self.new_msg_list, "ALL")
        self.vbox_sw_msg_btn.pack_start(all_button, False)
                
        type_rows = self.get_types()

        for msg_type in type_rows:
            button_id = msg_type[0]
            button = gtk.Button(button_id, None, False)
            button.set_size_request(215, 24)
            tooltip = msg_type[1]
            button.set_tooltip_text(tooltip)
            button.connect("clicked", self.new_msg_list, button_id)
            self.vbox_sw_msg_btn.pack_start(button, False)

    # columns for the lists
    def add_msg_columns(self, treeview):
        # column ONE
        column = gtk.TreeViewColumn('Code', gtk.CellRendererText(),
                                     text=0)
        column.set_sort_column_id(0)
        #column.set_visible(False)
        treeview.append_column(column)

        # column TWO
        column = gtk.TreeViewColumn('Title', gtk.CellRendererText(),
                                    text=1)
        column.set_sort_column_id(1)
        
        treeview.append_column(column)

        # column THREE
        column = gtk.TreeViewColumn('Type', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_visible(False)
        treeview.append_column(column)

        #Column FOUR
        column = gtk.TreeViewColumn('Ending', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        treeview.append_column(column)
        
        #Column FIVE
        column = gtk.TreeViewColumn('Expiry Date', gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_visible(False)
        treeview.append_column(column)
        
        #Column SIX
        column = gtk.TreeViewColumn('Filename', gtk.CellRendererText(),
                                    text=5)
        column.set_sort_column_id(5)
        column.set_visible(False)
        treeview.append_column(column)
        
        #Column SEVEN
        column = gtk.TreeViewColumn('Producer', gtk.CellRendererText(),
                                    text=6)
        column.set_sort_column_id(6)
        column.set_visible(False)
        treeview.append_column(column)
        
        #Column EIGHT  
        column = gtk.TreeViewColumn('Duration', gtk.CellRendererText(),
                                    text=7)
        column.set_sort_column_id(7)
        column.set_visible(False)
        treeview.append_column(column)
        
        #Column EIGHT  
        column = gtk.TreeViewColumn('Created', gtk.CellRendererText(),
                                    text=8)
        column.set_sort_column_id(8)
        column.set_visible(False)
        treeview.append_column(column)        
        
    def new_msg_list(self, widget, msg_type):
        """
        When a button is clicked get messages of that type and 
        display them in the list
        """
        self.message_type = msg_type
        if msg_type == "ALL":
            get_message_string = "SELECT * FROM messagelist"
        else:
            get_message_string = "SELECT * FROM messagelist WHERE type='{0}'".format (msg_type)
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(get_message_string)
        messages = cur.fetchall()  
        cur.close()
        conn.close()      
        #delete existing data
        self.msg_store.clear()
        #add rows of new data
        for item in messages:
            iter = self.msg_store.append()
            self.msg_store.set(iter,
                0, item[0],
                1, item[1], 
                2, item[2],
                3, item[3],
                4, item[4],
                5, item[5],
                6, item[6],
                7, item[7],
                8, item[8]
                )
   
    # preview section  
    def get_filepath(self):
        treeselection = self.treeview_msg.get_selection()
        model, iter = treeselection.get_selected()
        tup_path = model.get(iter, 2, 5)
        type_12 = tup_path[0][0:12]
        type_12 = type_12.lower()
        filepath = "{0}/{1}/{2}".format (dir_msg, type_12, tup_path[1])
        return filepath

    def play_pause_clicked(self, widget):
        filepath = self.get_filepath()
        if not os.path.isfile(filepath):
            str_error = "Unable to play, file does not exist."
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
        if (playstatus == gst.STATE_PLAYING) or (playstatus == gst.STATE_PAUSED):
            self.on_stop_clicked(True)
            
    def on_seek_changed(self, widget, param):
        self.player_pre.set_updateable_progress(True)
        self.player_pre.set_place_in_file(self.hscale_pre.get_value())
    
    def error_dialog(self, str_error):
        messagedialog = gtk.MessageDialog(None, 0, 
                    gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, 
                    str_error)
        messagedialog.run()
        messagedialog.destroy()  

    def info_dialog(self, str_info):
        messagedialog = gtk.MessageDialog(None, 0, 
                    gtk.MESSAGE_INFO, gtk.BUTTONS_OK, 
                    str_info)
        messagedialog.run()
        messagedialog.destroy() 
        
        
        
    def getfile(self):
        '''
        open a file chooser window to select an audio file
        '''
        dialog = gtk.FileChooserDialog("Select the Message to Add",
                                       None,
                                       gtk.FILE_CHOOSER_ACTION_OPEN,
                                       (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                        gtk.STOCK_OPEN, gtk.RESPONSE_OK))

        dialog.set_default_response(gtk.RESPONSE_OK)

        filter = gtk.FileFilter()
        filter.set_name("Audio files")
        filter.add_pattern("*.mp3")
        filter.add_pattern("*.wav")
        filter.add_pattern("*.ogg")
        filter.add_pattern("*.flac")
        filter.add_pattern("*.aiff")
        dialog.add_filter(filter)
        
        filter = gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*") 
        dialog.add_filter(filter)

        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filename()
        dialog.destroy()
        return filename

    #add message section
    def show_info(self, widget):
        msg_info = self.get_selection()
        showinfo = ShowInfo(msg_info)
        showinfo          
        
    def new_message(self, widget):
        NewMessage()
        self.new_msg_list(None, self.message_type)

    def change_message(self, widget):        
        try:
            msg_info = self.get_selection()
            change_message = ChangeMessage(msg_info)
            change_message
            self.new_msg_list(None, self.message_type)
        except TypeError:
            str_error = "You must select a message"
            self.error_dialog(str_error)
            
        
    def delete_message(self, widget):
        try:
            msg_info = self.get_selection()
            
        except TypeError:
            str_error = "You must select a message"
            self.error_dialog(str_error)                        
            
        code = msg_info[0]
        msg_type = msg_info[2]
        filename = msg_info[5]
        
        query = "DELETE FROM messagelist WHERE code = '{}'".format(code)
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        conn.commit()
        cur.close()
        conn.close()
        
        #move audio file to time-stamped backup directory        
        dt = datetime.datetime.now()
        dir_date = datetime.datetime.strftime(dt, "%Y%m")
        path_backup = dir_backup + dir_date
        type_12 = msg_type[0:12]
        type_12 = type_12.lower()
        filepath = dir_msg + type_12 + "/" + filename
        if not os.path.isdir(path_backup):
            os.mkdir(path_backup)
        try:
            shutil.move(filepath, path_backup)
        except OSError:
            os.remove(filepath)
        self.new_msg_list(None, self.message_type)

    #manage types section
    def new_type(self, widget):
        nt = NewType()
        nt
        self.make_buttons()
        self.window.show_all()

    def del_type(self, widget):
        dt = DeleteType()
        dt
        self.make_buttons()
        self.window.show_all()        

    #called by dialog windows
    def get_selection(self):
        treeselection = self.treeview_msg.get_selection()
        model, iter = treeselection.get_selected()
        msg_info = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7, 8)
        return msg_info
        
mp = Messager()
mp.main()
