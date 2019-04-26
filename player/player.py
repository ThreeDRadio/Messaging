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

    def on_window_destroy(self, widget):
        Gtk.main_quit()

if __name__ == "__main__":
    gui = Player()
    Gtk.main()
