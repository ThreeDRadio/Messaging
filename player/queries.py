#!/usr/bin/env python3

import datetime

import psycopg2
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
    def pg_connect_msg(self):
        '''
        connect to the message database
        '''
        #connection variables
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            pg_msg_database, pg_msg_user, pg_server, pg_msg_password)
        conn = psycopg2.connect(conn_string)
        #cur = conn.cursor()
        return conn

    def get_types(self):
        '''
        query the database for the different types of messages
        '''
        query = "SELECT type,description FROM typelist ORDER BY type"
        conn = self.pg_connect_msg()
        cur = conn.cursor()
        cur.execute(query)
        type_rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return type_rows

