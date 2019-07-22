#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# File: taubenschlag.py
#
# Part of ‘Taubenschlag'
# GitHub: https://github.com/bithon/Taubenschlag
#
# Author: Oliver Zehentleitner
#         https://about.me/oliver_zehentleitner/
#
# Copy Editor: Jason Schmitz
#
# Copyright (c) 2019, Oliver Zehentleitner
# All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish, dis-
# tribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the fol-
# lowing conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
# ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
# SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

from __future__ import print_function
from argparse import ArgumentParser
from cheroot import wsgi
from copy import deepcopy
from flask import Flask, redirect, request
from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient
from shutil import copyfile
import argparse
import configparser
import datetime
import logging
import json
import os
import textwrap
import threading
import time
import tweepy

abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

logging.basicConfig(format="{asctime} [{levelname:8}] {process} {thread} {module} {pathname} {lineno}: {message}",
                    filename='taubenschlag.log',
                    style="{")
logging.getLogger('taubenschlag').addHandler(logging.StreamHandler())
logging.getLogger('taubenschlag').setLevel(logging.INFO)


class Taubenschlag(object):
    def __init__(self):
        self.app_version = "0.9.1"
        self.config = self._load_config()
        self.app_name = self.config['SYSTEM']['app_name']
        self.dm_sender_name = self.config['SYSTEM']['dm_sender_name']
        print("Starting " + str(self.app_name) + " Bot (Taubenschlag " + str(self.app_version) + ")")
        self.base_url = self.config['SYSTEM']['base_url']
        self.bot_topic = self.config['SYSTEM']['bot_topic']
        self.bot_twitter_account = self.config['SYSTEM']['bot_twitter_account']
        self.default_retweet_level = self.config['SYSTEM']['default_retweet_level']
        self.issues_report_to = self.config['SYSTEM']['issues_report_to']
        self.retweet_sources_description = self.config['SYSTEM']['retweet_sources_description']
        self.consumer_key = self.config['SECRETS']['consumer_key']
        self.consumer_secret = self.config['SECRETS']['consumer_secret']
        self.access_token = self.config['SECRETS']['access_token']
        self.access_token_secret = self.config['SECRETS']['access_token_secret']
        self.consumer_key_dm = self.config['SECRETS']['consumer_key_dm']
        self.consumer_secret_dm = self.config['SECRETS']['consumer_secret_dm']
        self.access_token_dm = self.config['SECRETS']['access_token_dm']
        self.access_token_secret_dm = self.config['SECRETS']['access_token_secret_dm']
        parser = ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                description=textwrap.dedent(self.app_name + " Bot " + self.app_version+ " by "
                                                            "\r\n - Oliver Zehentleitner (2019 - 2019)\r\n\r\n"
                                                            "description: this bot manages retweets for the " +
                                                            self.app_name + " Twitter campaign of multiple accounts!"),
                                epilog=textwrap.dedent("GitHub: " + self.config['SYSTEM']['github_rep_url']))
        parser.add_argument('-a', '--account-list', dest='account_list',
                            help='show saved account list', action="store_true")
        self.parsed_args = parser.parse_args()
        self.api_self = False
        self.refresh_api_self()
        self.api_dm = False
        self.refresh_api_dm()
        self.data = False
        self.data_layout = {"tweets": [],
                            "accounts": {},
                            "statistic": {"tweets": 0,
                                          "retweets": 0,
                                          "sent_help_dm": 0,
                                          "received_botcmds": 0}}
        self.leaderboard_table = {}
        self.leaderboard_table_string = ""
        self.leaderboard_last_generation = "?"
        self.bot_user_id = self.api_self.get_user(self.bot_twitter_account).id
        self.sys_admin_list = self.config['SYSTEM']['sys_admin_list'].split(",")
        self.load_db()

    def _fill_up_space(self, demand_of_chars, string):
        blanks_pre = ""
        blanks_post = ""
        demand_of_blanks = demand_of_chars - len(str(string)) - 1
        while len(blanks_post) < demand_of_blanks:
            blanks_pre = " "
            blanks_post += " "
        return blanks_pre + str(string) + blanks_post

    def _load_config(self):
        config_path = "./conf.d"
        config = configparser.ConfigParser()
        if os.path.isdir(config_path) is False:
            logging.critical("can not access " + config_path)
            return False
        raw_file_list = os.listdir(config_path)
        for file_name in raw_file_list:
            if os.path.splitext(file_name)[1] == ".cfg":
                try:
                    config.read_file(open(config_path + "/" + file_name))
                except ValueError as error_msg:
                    logging.error(str(error_msg))
                    return False
        return config

    def _webserver_thread(self):
        logging.info("starting webserver ...")
        app = Flask(__name__)

        @app.route('/oAuthTwitter/start')
        def oauth_twitter_start(consumer_key=self.consumer_key, consumer_secret=self.consumer_secret):
            auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
            try:
                return redirect(auth.get_authorization_url(), code=302)
            except tweepy.TweepError as error_msg:
                logging.error('failed to get request token. ' + str(error_msg))

        @app.route('/oAuthTwitter/verify')
        def oauth_twitter_verify():
            try:
                if request.args["denied"]:
                    return redirect(self.config['SYSTEM']['redirect_canceled'], code=302)
            except KeyError:
                pass
            auth = tweepy.OAuthHandler(self.consumer_key, self.consumer_secret)
            auth.request_token = {'oauth_token': request.args["oauth_token"],
                                  'oauth_token_secret': request.args["oauth_verifier"]}
            try:
                auth.get_access_token(request.args["oauth_verifier"])
            except tweepy.TweepError as error_msg:
                logging.error('failed to get access token. ' + str(error_msg))
                return self.error_text

            if auth.access_token_secret is not None and auth.access_token is not None:
                status = False
                user = self.api_self.get_user(screen_name=auth.get_username())
                try:
                    if len(self.data['accounts']) > 0:
                        status = True
                except TypeError:
                    pass
                if status is False:
                    self.data['accounts'] = {str(user.id): {}}
                try:
                    retweets_value = self.data['accounts'][str(user.id)]['retweets']
                except KeyError:
                    retweets_value = 0
                self.data['accounts'][str(user.id)] = {'access_token': str(auth.access_token),
                                                       'access_token_secret': str(auth.access_token_secret),
                                                       'retweet_level': self.default_retweet_level,
                                                       'retweets': retweets_value}
                logging.info("Saved new oAuth access of Twitter user " + str(user.name) + "!")
                print("Saved new oAuth token of @" + str(user.screen_name) + " (" + str(user.name) + ")!")
                self.save_db(new_account=True)
                retweet_level = self.data['accounts'][str(user.id)]['retweet_level']
                api = self.get_api_user(user.id)
                try:
                    api.create_friendship(id=self.bot_user_id)
                except tweepy.error.TweepError as error_msg:
                    if "You can't follow yourself" in str(error_msg):
                        pass
                    else:
                        logging.error(str(error_msg))
                try:
                    self.api_self.create_friendship(id=user.id)
                except tweepy.error.TweepError as error_msg:
                    if "You can't follow yourself" in str(error_msg):
                        pass
                    else:
                        logging.error(str(error_msg))
                try:
                    retweets = self.data['accounts'][str(user.id)]['retweets']
                    self.api_self.send_direct_message(user.id, "Hello " + str(user.name) +
                                                      "!\r\n\r\nThank you for joining " + self.app_name + "!\r\n\r\n"
                                                      + self.retweet_sources_description +
                                                      "\r\n\r\nTo set a retweet level, send a DM to @" +
                                                      self.bot_twitter_account + " with the following text:\r\n"
                                                      "* 'set-rt-level:1' to retweet only first class posts\r\n"
                                                      "* 'set-rt-level:2' to be informative\r\n"
                                                      "* 'set-rt-level:3' to retweet everything " + self.bot_topic +
                                                      " related that "
                                                      "this app finds for you!\r\n \r\nYour current retweet-level "
                                                      "is " + str(retweet_level) + "\r\n\r\nYou have made " +
                                                      str(retweets) + " retweets for " + self.bot_topic + "!\r\n" +
                                                      "\r\n\r\nThis application is "
                                                      "now connected to your Twitter Account. If you wish to "
                                                      "revoke its access, you can do so via Twitter’s "
                                                      "'Settings and Privacy' page "
                                                      "(https://twitter.com/settings/sessions) by clicking on the "
                                                      "'Revoke Access' button. However, once access is revoked, it "
                                                      "cannot be undone via Twitter. You must reauthorize it at "
                                                      + self.base_url + "\r\n"
                                                      "\r\nAuthorizing " + self.app_name + " permits it to:"
                                                      "\r\n* Read Tweets from your timeline\r\n"
                                                      "* See who you follow, and follow new people\r\n"
                                                      "* Update your profile\r\n"
                                                      "* Post Tweets for you\r\n"
                                                      "\r\n**HOWEVER, " + self.app_name + " WILL DO NONE OF THESE "
                                                      "THINGS. " + self.app_name + " WILL ONLY RETWEET RELEVENT " +
                                                      self.bot_topic +
                                                      " TWEETS**\r\n\r\nAuthorizing " + self.app_name + " does not "
                                                      "permit it to:\r\n* Access or otherwise view your Direct Messages"
                                                      " (DMs)\r\n* Access or otherwise view your email address\r\n"
                                                      "* Access or otherwise view your Twitter password\r\n"
                                                      "\r\nBy authorizing any application, including the " +
                                                      self.app_name +
                                                      "Retweets, you continue to operate under Twitter's Terms of "
                                                      "Service. Some usage data will be "
                                                      "shared with Twitter. For more information, see Twitter’s "
                                                      'Privacy Policy.'"\r\n"
                                                      "\r\nFor questions or additional information, send a direct "
                                                      "message with the text 'help' to me or 'get-cmd-list' to see "
                                                      "a list of all available commands!\r\n\r\nPlease report issues to "
                                                      + self.issues_report_to +
                                                      " - Thank you!\r\n"
                                                      "\r\nBest regards,\r\n" + self.dm_sender_name + "!")
                    # send status message to bot account
                    self.send_status_message_new_user(self.bot_user_id, user.id)
                    # send status message to sys_admins
                    for admin_name in self.sys_admin_list:
                        self.send_status_message_new_user(self.api_self.get_user(screen_name=admin_name).id, user.id)
                except tweepy.error.TweepError:
                    pass
                return redirect(self.config['SYSTEM']['redirect_successfull_participation'], code=302)
            else:
                return redirect(self.config['SYSTEM']['redirect_canceled'], code=302)
        try:
            dispatcher = wsgi.PathInfoDispatcher({'/': app})
            webserver = wsgi.WSGIServer((self.config['SYSTEM']['api_listener_ip'],
                                         int(self.config['SYSTEM']['api_listener_port'])),
                                        dispatcher)
            webserver.start()
            logging.info("webserver started!")
        except RuntimeError as error_msg:
            logging.critical("webserver is going down! " + str(error_msg))

    def send_status_message_new_user(self, recipient_id, new_user_id):
        logging.debug("sending DM with 'new user' alert to " + str(recipient_id))
        self.api_self.send_direct_message(recipient_id,
                                          "Hello " + str(self.api_self.get_user(recipient_id).name) + "!\r\n\r\n"
                                          "A new user subscribed to " + self.app_name + ": " + str(new_user_id) +
                                          " - " + str(self.api_self.get_user(new_user_id).screen_name) +
                                          "\r\n\r\nBest regards,\r\n" + self.dm_sender_name + "!")

    def check_direct_messages(self):
        time.sleep(2)
        while True:
            try:
                dm_list = self.api_dm.list_direct_messages()
                for dm in reversed(dm_list):
                    try:
                        if self.data['accounts'][str(dm.message_create['sender_id'])]:
                            pass
                    except KeyError as error_msg:
                        logging.info("The unauthorized Twitter user @" +
                                     self.api_self.get_user(dm.message_create['sender_id']).screen_name +
                                     " wrote a command to the bot! (error_msg: " + str(error_msg) + ")")
                        self.api_dm.destroy_direct_message(dm.id)
                        continue
                    if "".join(str(dm.message_create['message_data']['text']).split()).lower() == "help":
                        print("Send help DM to " + str(dm.message_create['sender_id']) + "!")
                        user = self.api_self.get_user(dm.message_create['sender_id'])
                        user_id = dm.message_create['sender_id']
                        try:
                            retweet_level = self.data['accounts'][str(user_id)]['retweet_level']
                        except KeyError:
                            self.data['accounts'][str(user_id)]['retweet_level'] = 2
                            self.save_db()
                            retweet_level = self.data['accounts'][str(user_id)]['retweet_level']
                        try:
                            retweets = self.data['accounts'][str(user_id)]['retweets']
                        except KeyError:
                            self.data['accounts'][str(user_id)]['retweets'] = 0
                            self.save_db()
                            retweets = self.data['accounts'][str(user_id)]['retweets']
                        self.api_self.send_direct_message(dm.message_create['sender_id'], "Hello " + str(user.name) +
                                                          "!\r\n\r\n" + self.retweet_sources_description + "\r\n"
                                                          "\r\nTo set a retweet level, send a DM to @" +
                                                          self.bot_twitter_account + " with the following text:\r\n"
                                                          "* 'set-rt-level:1' to retweet only first class posts\r\n"
                                                          "* 'set-rt-level:2' to be informative\r\n"
                                                          "* 'set-rt-level:3' to retweet everything " + self.bot_topic +
                                                          " related that "
                                                          "this app finds for you!\r\n \r\nYour current retweet-level "
                                                          "is " + str(retweet_level) + "\r\n\r\nYou have made " +
                                                          str(retweets) + " retweets for " + self.bot_topic + "!\r\n"
                                                          "\r\nThis application "
                                                          "is now connected to your Twitter Account. If you wish to "
                                                          "revoke its access, you can do so via Twitter’s "
                                                          "'Settings and Privacy' page "
                                                          "(https://twitter.com/settings/sessions) by clicking on the "
                                                          "'Revoke Access' button. However, once access is revoked, it "
                                                          "cannot be undone via Twitter. You must reauthorize it at "
                                                          + self.base_url + "\r\n"
                                                          "\r\n\r\nAuthorizing " + self.app_name + " permits it to:"
                                                          "\r\n* Read Tweets from your timeline\r\n"
                                                          "* See who you follow, and follow new people\r\n"
                                                          "* Update your profile\r\n"
                                                          "* Post Tweets for you\r\n"
                                                          "\r\n**HOWEVER, " + self.app_name + " WILL DO NONE OF THESE "
                                                          "THINGS. " + self.app_name + " WILL ONLY RETWEET RELEVENT " +
                                                          self.bot_topic + " TWEETS**\r\n"
                                                          "\r\nAuthorizing " + self.app_name + " does not permit it to:"
                                                          "\r\n* Access or otherwise view your Direct Messages (DMs)"
                                                          "\r\n* Access or otherwise view your email address\r\n"
                                                          "* Access or otherwise view your Twitter password\r\n\r\nBy a"
                                                          "uthorizing any application, including the " + self.app_name +
                                                          ", you continue to operate under Twitter's Terms of "
                                                          "Service. Some usage data will be "
                                                          "shared with Twitter. For more information, see Twitter’s "
                                                          'Privacy Policy.'"\r\n"
                                                          "\r\nFor questions or additional information, send a direct "
                                                          "message with the text 'help' to me or 'get-cmd-list' to see "
                                                          "a list of all available commands!\r\n\r\n"
                                                          "Please report issues to "
                                                          + self.issues_report_to + " - Thank you!\r\n"
                                                          "\r\nBest regards,\r\n" + self.dm_sender_name + "!")
                        self.api_dm.destroy_direct_message(dm.id)
                        self.data['statistic']['sent_help_dm'] += 1
                        self.save_db()
                    elif "".join(str(dm.message_create['message_data']['text']).split()).lower() == "set-rt-level:1":
                        print("Set retweet_level for user " + str(dm.message_create['sender_id'] + " to 1!"))
                        user = self.api_self.get_user(dm.message_create['sender_id'])
                        user_id = dm.message_create['sender_id']
                        try:
                            self.data['accounts'][str(user_id)]['retweet_level'] = 1
                        except KeyError as error_msg:
                            logging.error("cant execute set-rt-level, because the user.id (" + str(user_id) + ") is "
                                          "not saved in our DB! - " + str(error_msg))
                            self.api_dm.destroy_direct_message(dm.id)
                            continue
                        retweet_level = self.data['accounts'][str(user_id)]['retweet_level']
                        self.api_self.send_direct_message(dm.message_create['sender_id'],
                                                          "Hello " + str(user.name) +
                                                          "!\r\n\r\nYour new retweet-level is " + str(retweet_level) +
                                                          "\r\n\r\nFor questions or additional information, send a "
                                                          "direct message with the text 'help' to me or 'get-cmd-list'"
                                                          " to see a list of all available commands!"
                                                          "\r\n\r\nBest regards,\r\n" + self.dm_sender_name + "!")
                        self.api_dm.destroy_direct_message(dm.id)
                        self.data['statistic']['received_botcmds'] += 1
                        self.save_db()
                    elif "".join(str(dm.message_create['message_data']['text']).split()).lower() == "set-rt-level:2":
                        print("Set retweet_level for user " + str(dm.message_create['sender_id'] + " to 2!"))
                        user = self.api_self.get_user(dm.message_create['sender_id'])
                        user_id = dm.message_create['sender_id']
                        try:
                            self.data['accounts'][str(user_id)]['retweet_level'] = 2
                        except KeyError as error_msg:
                            logging.error("cant execute set-rt-level, because the user.id (" + str(user_id) + ") is "
                                          "not saved in our DB! - " + str(error_msg))
                            self.api_dm.destroy_direct_message(dm.id)
                            continue
                        retweet_level = self.data['accounts'][str(user_id)]['retweet_level']
                        self.api_self.send_direct_message(dm.message_create['sender_id'],
                                                          "Hello " + str(user.name) +
                                                          "!\r\n\r\nYour new retweet-level is " + str(retweet_level) +
                                                          "\r\n\r\nFor questions or additional information, send a "
                                                          "direct message with the text 'help' to me or 'get-cmd-list'"
                                                          " to see a list of all available commands!"
                                                          "\r\n\r\nBest regards,\r\n" + self.dm_sender_name + "!")
                        self.api_dm.destroy_direct_message(dm.id)
                        self.data['statistic']['received_botcmds'] += 1
                        self.save_db()
                    elif "".join(str(dm.message_create['message_data']['text']).split()).lower() == "set-rt-level:3":
                        print("Set retweet_level for user " + str(dm.message_create['sender_id'] + " to 3!"))
                        user = self.api_self.get_user(dm.message_create['sender_id'])
                        user_id = dm.message_create['sender_id']
                        try:
                            self.data['accounts'][str(user_id)]['retweet_level'] = 3
                        except KeyError as error_msg:
                            logging.error("cant execute set-rt-level, because the user.id (" + str(user_id) + ") is "
                                          "not saved in our DB! - " + str(error_msg))
                            self.api_dm.destroy_direct_message(dm.id)
                            continue
                        retweet_level = self.data['accounts'][str(user_id)]['retweet_level']
                        self.api_self.send_direct_message(dm.message_create['sender_id'],
                                                          "Hello " + str(user.name) +
                                                          "!\r\n\r\nYour new retweet-level is " + str(retweet_level) +
                                                          "\r\n\r\nFor questions or additional information, send a "
                                                          "direct message with the text 'help' to me or 'get-cmd-list'"
                                                          " to see a list of all available commands!"
                                                          "\r\n\r\nBest regards,\r\n" + self.dm_sender_name + "!")
                        self.api_dm.destroy_direct_message(dm.id)
                        self.data['statistic']['received_botcmds'] += 1
                        self.save_db()
                    elif "".join(str(dm.message_create['message_data']['text']).split()).lower() == "get-cmd-list":
                        user = self.api_self.get_user(dm.message_create['sender_id'])
                        print("Send command list to " + str(user.id) + " - " + str(user.screen_name))
                        msg = ""
                        msg += "List of available bot commands:\r\n"
                        msg += "* 'get-cmd-list'\r\n"
                        msg += "* 'get-info'\r\n"
                        msg += "* 'help'\r\n"
                        msg += "* 'set-rt-level:1'\r\n"
                        msg += "* 'set-rt-level:2'\r\n"
                        msg += "* 'set-rt-level:3'\r\n"
                        msg += "* '\r\nget-bot-info (admins only)\r\n"
                        self.api_self.send_direct_message(dm.message_create['sender_id'],
                                                          "Hello " +
                                                          str(self.api_self.get_user(
                                                              dm.message_create['sender_id']).name) +
                                                          "!\r\n\r\n" + str(msg) + "\r\n"
                                                          "\r\n\r\nFor questions or additional information, send a "
                                                          "direct message with the text 'help' to me or 'get-cmd-list'"
                                                          " to see a list of all available commands!\r\n\r\n"
                                                          "Best regards,\r\n" + self.dm_sender_name + "!")
                        self.api_dm.destroy_direct_message(dm.id)
                        self.data['statistic']['received_botcmds'] += 1
                        self.save_db()
                    elif "".join(str(dm.message_create['message_data']['text']).split()).lower() == "get-info":
                        user = self.api_self.get_user(dm.message_create['sender_id'])
                        print("Send account infos to " + str(user.id) + " - " + str(user.screen_name))
                        msg = ""
                        msg += "Your leaderboard rank: " + str(self.leaderboard_table[str(user.id)]['rank']) + "\r\n"
                        msg += "Your retweet-level: " + str(self.data['accounts'][str(user.id)]['retweet_level'])
                        msg += "\r\nYour retweets: " + str(self.data['accounts'][str(user.id)]['retweets']) + "\r\n"
                        self.api_self.send_direct_message(dm.message_create['sender_id'],
                                                          "Hello " +
                                                          str(self.api_self.get_user(
                                                              dm.message_create['sender_id']).name) +
                                                          "!\r\n\r\n" + str(msg) + "\r\n\r\nTOP 10 LEADERBOARD\r\n"
                                                          "===================\r\n"
                                                          + self.leaderboard_table_string +
                                                          "\r\n\r\nFor questions or additional information, send a "
                                                          "direct message with the text 'help' to me or 'get-cmd-list' "
                                                          "to see a list of all available commands!\r\n\r\n"
                                                          "Best regards,\r\n" + self.dm_sender_name + "!")
                        self.api_dm.destroy_direct_message(dm.id)
                        self.data['statistic']['received_botcmds'] += 1
                        self.save_db()
                    elif "".join(str(dm.message_create['message_data']['text']).split()).lower() == "get-bot-info":
                        user = self.api_self.get_user(dm.message_create['sender_id'])
                        admin_status = False
                        for admin_name in self.sys_admin_list:
                            if str(user.id) == str(self.api_self.get_user(screen_name=admin_name).id):
                                admin_status = True
                        if str(user.id) == str(self.bot_user_id) or admin_status is True:
                            subscriptions_rt_level_1 = 0
                            subscriptions_rt_level_2 = 0
                            subscriptions_rt_level_3 = 0
                            print("Send bot infos to " + str(user.id) + " - " + str(user.screen_name))
                            msg = ""
                            msg += "Bot: " + self.app_name + " Bot " + self.app_version + "\r\n\r\n"
                            msg += "Accounts: " + str(len(self.data['accounts'])) + "\r\n"
                            for user_id in self.data['accounts']:
                                if int(self.data['accounts'][user_id]['retweet_level']) == 1:
                                    subscriptions_rt_level_1 += 1
                                elif int(self.data['accounts'][user_id]['retweet_level']) == 2:
                                    subscriptions_rt_level_1 += 1
                                    subscriptions_rt_level_2 += 1
                                elif int(self.data['accounts'][user_id]['retweet_level']) == 3:
                                    subscriptions_rt_level_1 += 1
                                    subscriptions_rt_level_2 += 1
                                    subscriptions_rt_level_3 += 1
                                user = self.api_self.get_user(user_id)
                                msg += "@" + user.screen_name + " - level : " + \
                                       str(self.data['accounts'][user_id]['retweet_level']) + " - rt: " + \
                                       str(self.data['accounts'][user_id]['retweets']) + "\r\n"
                            msg += "\r\nAvailable accounts per RT level:\r\n"
                            msg += "* 1: " + str(subscriptions_rt_level_1) + "\r\n"
                            msg += "* 2: " + str(subscriptions_rt_level_2) + "\r\n"
                            msg += "* 3: " + str(subscriptions_rt_level_3) + "\r\n\r\n"
                            msg += "Tweets: " + str(self.data['statistic']['tweets']) + "\r\n\r\n"
                            msg += "Retweets: " + str(self.data['statistic']['retweets']) + "\r\n\r\n"
                            msg += "Sent help DMs: " + str(self.data['statistic']['sent_help_dm']) + "\r\n\r\n"
                            msg += "Executed bot commands: " + str(self.data['statistic']['received_botcmds'])
                            self.api_self.send_direct_message(dm.message_create['sender_id'],
                                                              "Hello " +
                                                              str(self.api_self.get_user(
                                                                  dm.message_create['sender_id']).name) +
                                                              "!\r\n\r\n" +
                                                              str(msg) + "\r\n\r\nBest regards,\r\n" +
                                                              self.dm_sender_name + "!")
                            self.data['statistic']['received_botcmds'] += 1
                            self.save_db()
                        else:
                            logging.info("Received 'get-bot-info' from unauthorized account: " + str(user.id) + " - " +
                                         str(user.screen_name))
                            print("Received 'get-bot-info' from unauthorized account: " + str(user.id) + " - " +
                                  str(user.screen_name))
                        self.api_dm.destroy_direct_message(dm.id)
            except tweepy.error.RateLimitError as error_msg:
                logging.error(str(error_msg))
                time.sleep(300)
            except tweepy.error.TweepError as error_msg:
                logging.critical(str(error_msg))
            time.sleep(60)

    def get_api_user(self, user_id):
        auth = tweepy.OAuthHandler(self.consumer_key, self.consumer_secret)
        auth.set_access_token(self.data['accounts'][str(user_id)]['access_token'],
                              self.data['accounts'][str(user_id)]['access_token_secret'])
        api = tweepy.API(auth)
        return api

    def leaderboard(self):
        while True:
            time_start = time.time()
            temp_leaderboard_table = {}
            self.leaderboard_table_string = ""
            print("Generating leaderboard ...")
            logging.debug("Generating leaderboard ...")
            for user_id in self.data['accounts']:
                try:
                    temp_leaderboard_table[user_id] = self.data['accounts'][user_id]['retweets']
                except KeyError:
                    time.sleep(60*1)
                    continue
            rank = 1
            self.leaderboard_table = {}
            for key, value in reversed(sorted(temp_leaderboard_table.items(), key=lambda item: (item[1], item[0]))):
                if rank <= 10:
                    self.leaderboard_table_string += "#" + str(rank) + " " + \
                                                     str(self.api_self.get_user(key).screen_name) + \
                                                     " - " + str(value) + " retweets\r\n"
                self.leaderboard_table[key] = {'retweets': value,
                                               'rank': rank}
                rank += 1
            time_end = time.time()
            run_time = time_end - time_start
            print("Leaderboard generation runtime: " + str(run_time) + " seconds")
            time.sleep(60*20)

    def load_db(self):
        try:
            with open("./db/" + self.config['DATABASE']['db_file'], 'r') as f:
                try:
                    self.data = json.load(f)
                except json.decoder.JSONDecodeError as error_msg:
                    logging.error(str(error_msg) + " - creating new db!")
                    self.data = self.data_layout
        except FileNotFoundError as error_msg:
            logging.error("create new db!" + str(error_msg))
            self.data = self.data_layout

    def refresh_api_self(self):
        auth = tweepy.OAuthHandler(self.consumer_key, self.consumer_secret)
        auth.set_access_token(self.access_token, self.access_token_secret)
        self.api_self = tweepy.API(auth)

    def refresh_api_dm(self):
        auth = tweepy.OAuthHandler(self.consumer_key_dm, self.consumer_secret_dm)
        auth.set_access_token(self.access_token_dm, self.access_token_secret_dm)
        self.api_dm = tweepy.API(auth)

    def save_db(self, new_account=False):
        try:
            os.remove("./db/" + self.config['DATABASE']['db_file'] + "_backup")
        except FileNotFoundError:
            pass
        try:
            copyfile("./db/" + self.config['DATABASE']['db_file'],
                     "./db/" + self.config['DATABASE']['db_file'] + "_backup")
        except FileNotFoundError:
            pass
        try:
            with open("./db/" + self.config['DATABASE']['db_file'], 'w+') as f:
                json.dump(self.data, f)
            if new_account:
                try:
                    os.remove("./db/" + self.config['DATABASE']['db_file'] + "_backup_new_user")
                except FileNotFoundError:
                    pass
                with open("./db/" + self.config['DATABASE']['db_file'] + "_backup_new_user", 'w+') as f:
                    json.dump(self.data, f)
                if self.config['SYSTEM']['ssh_backup_on_new_user'] == "True":
                    self.start_thread(self.ssh_remote_backup)
        except PermissionError as error_msg:
            print("ERROR!!! Can not save database file!")
            logging.critical("can not save database file! " + str(error_msg))

    def ssh_remote_backup(self):
        print("Starting DB backup to " + str(self.config['SECRETS']['ssh_backup_server']))
        logging.info("Starting DB backup to " + str(self.config['SECRETS']['ssh_backup_server']))
        ssh = SSHClient()
        ssh.set_missing_host_key_policy(AutoAddPolicy())
        ssh.load_system_host_keys()
        ssh.connect(self.config['SECRETS']['ssh_backup_server'],
                    username=self.config['SECRETS']['ssh_backup_user'],
                    password=self.config['SECRETS']['ssh_backup_pass'])
        with SCPClient(ssh.get_transport()) as scp:
            scp.put("./db/" + self.config['DATABASE']['db_file'] + "_backup_new_user",
                    self.config['SECRETS']['ssh_backup_path'] + '/taubenschlag_all_accounts.json')

    def search_and_retweet(self):
        while True:
            print("======================================================================================")
            print("Starting new round at " + str(datetime.datetime.now()))
            rt_levels = 3
            round = 1
            while rt_levels >= round:
                print("Retweeting level " + str(round) + " tweets:")
                conditions_list = self.config['RT-LEVEL-' + str(round)]['conditions'].split(",")
                source_accounts_list = self.config['RT-LEVEL-' + str(round)]['from'].split(",")
                for source_account in source_accounts_list:
                    try:
                        timeline = self.api_self.user_timeline(source_account)
                    except tweepy.error.TweepError as error_msg:
                        logging.critical(str(error_msg))
                        print("error: " + str(error_msg) + " user: " + source_account)
                    for condition in conditions_list:
                        for tweet in timeline:
                            tweet_is_retweeted = False
                            count_tweet = False
                            if condition == "any":
                                retweet_permitted = True
                            else:
                                if str(condition).lower() in str(tweet.text).lower():
                                    retweet_permitted = True
                                else:
                                    retweet_permitted = False
                            if retweet_permitted is True:
                                try:
                                    if tweet.id in self.data['tweets']:
                                        tweet_is_retweeted = True
                                except TypeError:
                                    pass
                                if tweet_is_retweeted is False:
                                    print(str(tweet.id) + " - " + str(tweet.text[0:80]).splitlines()[0] + " ...")
                                    logging.debug(str(tweet.id) + " - " + str(tweet.text[0:80]).splitlines()[0] +
                                                  " ...")
                                    accounts = deepcopy(self.data['accounts'])
                                    for user_id in accounts:
                                        if (str(user_id) != str(self.bot_user_id) or
                                            self.config['SYSTEM']['let_bot_account_retweet'] == "True") \
                                                and int(self.data['accounts'][str(user_id)]['retweet_level']) >= \
                                                round:
                                            api = self.get_api_user(user_id)
                                            try:
                                                user_tweet = api.get_status(tweet.id)
                                                if not user_tweet.retweeted:
                                                    try:
                                                        user_tweet.retweet()
                                                        count_tweet = True
                                                        print("\tRetweeted:", user_id,
                                                              str(self.api_self.get_user(user_id).screen_name))
                                                        self.data['statistic']['retweets'] += 1
                                                        try:
                                                            self.data['accounts'][str(user_id)]['retweets'] += 1
                                                        except KeyError:
                                                            self.data['accounts'][str(user_id)]['retweets'] = 1
                                                        self.save_db()
                                                        logging.debug("\tRetweeted:", user_id,
                                                                      str(self.api_self.get_user(user_id).screen_name))
                                                    except tweepy.TweepError as error_msg:
                                                        print("\tERROR: " + str(error_msg))
                                                        logging.error("can not retweet: " + str(error_msg))
                                            except tweepy.error.TweepError as error_msg:
                                                if "Invalid or expired token" in str(error_msg):
                                                    logging.info("invalid or expired token, going to remove user " +
                                                                 user_id)
                                                    print("\tERROR: Invalid or expired token, going to remove user " +
                                                          user_id)
                                                    del self.data['accounts'][user_id]
                                                    self.save_db()
                                    if count_tweet:
                                        self.data['statistic']['tweets'] += 1
                                    try:
                                        self.data['tweets'].append(tweet.id)
                                    except AttributeError:
                                        self.data["tweets"] = [tweet.id]
                                    self.save_db()
                if count_tweet is False:
                    print("\tNo new tweet found!")
                round += 1
            print("Accounts: " + str(len(self.data['accounts'])))
            subscriptions_rt_level_1 = 0
            subscriptions_rt_level_2 = 0
            subscriptions_rt_level_3 = 0
            for user_id in self.data['accounts']:
                if int(self.data['accounts'][user_id]['retweet_level']) == 1:
                    subscriptions_rt_level_1 += 1
                elif int(self.data['accounts'][user_id]['retweet_level']) == 2:
                    subscriptions_rt_level_1 += 1
                    subscriptions_rt_level_2 += 1
                elif int(self.data['accounts'][user_id]['retweet_level']) == 3:
                    subscriptions_rt_level_1 += 1
                    subscriptions_rt_level_2 += 1
                    subscriptions_rt_level_3 += 1
                if self.parsed_args.account_list:
                    try:
                        retweets = self.data['accounts'][str(user_id)]['retweets']
                    except KeyError:
                        self.data['accounts'][str(user_id)]['retweets'] = 0
                        self.save_db()
                        retweets = self.data['accounts'][str(user_id)]['retweets']
                    try:
                        user = self.api_self.get_user(user_id)
                    except tweepy.error.TweepError as error_msg:
                        logging.error(str(error_msg))
                        print("error: " + str(error_msg))
                    print("\t" + str(self._fill_up_space(25, user_id)) +
                          self._fill_up_space(20, "@" + user.screen_name) + " RT level: " +
                          str(self.data['accounts'][user_id]['retweet_level']) + "\tretweets: " +
                          str(retweets))
            print("Available accounts per RT level:")
            print("\t1: " + str(subscriptions_rt_level_1))
            print("\t2: " + str(subscriptions_rt_level_2))
            print("\t3: " + str(subscriptions_rt_level_3))
            print("Tweets: " + str(self.data['statistic']['tweets']))
            print("Retweets: " + str(self.data['statistic']['retweets']))
            print("Sent help DMs: " + str(self.data['statistic']['sent_help_dm']))
            print("Executed bot commands: " + str(self.data['statistic']['received_botcmds']))
            print("--------------------------------------------------------------------------------------")
            time.sleep(30)

    def start_bot(self):
        self.start_thread(self.leaderboard)
        # wait to finish the FIRST leaderboard generation
        time.sleep(5)
        self.start_thread(self.search_and_retweet)
        self.start_thread(self.check_direct_messages)

    def start_thread(self, function):
        thread = threading.Thread(target=function)
        thread.start()

    def start_webserver(self):
        self.start_thread(self._webserver_thread)


taubenschlag = Taubenschlag()
taubenschlag.start_webserver()
taubenschlag.start_bot()

