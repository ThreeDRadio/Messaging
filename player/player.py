from gi.repository import Gtk, GLib, GdkPixbuf


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

        
        # Messages widgets

        
        # Music Catalogue widgets

        
        # Load Playlist widgets

        self.window.show()


    # ----- Window signal handlers -----

    def on_window_destroy(self, widget):
        Gtk.main_quit()
        
    def on_button_sch_now_clicked(self, widget): 
        print("on_button_sch_now_clicked")   
        # update the schedule and display the current time slot

    def on_button_sch_add_clicked(self, widget): 
        print("on_button_sch_add_clicked")
        # add the selected message to the broadcast list

    def on_button_pre_play_clicked(self, widget): 
        print("on_button_pre_play_clicked")
        # play/pause the selected item

    def on_button_pre_stop_clicked(self, widget): 
        print("on_button_pre_stop_clicked")
        # stop playing

    def on_button_brc_skip_clicked(self, widget): 
        print("on_button_brc_skip_clicked")
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
















if __name__ == "__main__":
    gui = Player()
    Gtk.main()
