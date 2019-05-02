#!/usr/bin/env python3

import datetime

import psycopg2
import psycopg2.extras
import configparser


config = configparser.ConfigParser()
config.read('/usr/local/etc/threedradio.conf')

pg_server = config['Common']['pg_server']

query_limit = config['ThreeDPlayer']['query_limit']

pg_server = config['Common']['pg_server']
pg_cat_user = config['ThreeDPlayer']['pg_cat_user']
pg_cat_password = config['ThreeDPlayer']['pg_cat_password']
pg_cat_database = config['Common']['pg_cat_database']
pg_msg_user = config['ThreeDPlayer']['pg_msg_user']
pg_msg_password = config['ThreeDPlayer']['pg_msg_password']
pg_msg_database = config['Common']['pg_msg_database']

class Queries():
    # message section
    def pg_connect(self, db):
        '''
        connect to the message database
        '''
        
        #connection variables
        if db == "cat":
            dbname = pg_cat_database
            user = pg_cat_user
            password = pg_cat_password
            
        elif db == "msg":
            dbname = pg_msg_database
            user = pg_msg_user
            password = pg_msg_password
            
        else:
            print("Error - db not specified (cat or msg)")
        
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            dbname, user, pg_server, password)
        
        conn = psycopg2.connect(conn_string)
        #cur = conn.cursor()
        return conn

    def select_query (self, db, query):
        conn = self.pg_connect(db)
        dict_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        dict_cur.execute(query)
        result = dict_cur.fetchall()
        dict_cur.close()
        conn.close()
        return result

    def get_types(self):
        '''
        query the database for the different types of messages
        '''
        query = "SELECT type,description FROM typelist ORDER BY type"
        db = "msg"
        type_rows = self.select_query(db, query)
        
        return type_rows
        
    def get_messages(self, msg_type):
        db = "msg"
        query = "SELECT * FROM messagelist WHERE type='{}'".format(msg_type)
        messages = self.select_query(db, query)
        return messages
        

        


