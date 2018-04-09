# encoding: utf-8

# Nagstamon - Nagios status monitor for your desktop
# Copyright (C) 2008-2014 Henri Wahl <h.wahl@ifw-dresden.de> et al.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA

# This Nagstamon plugin is based on the IcingaWeb2 plugin
# Initial implementation by Marcus Mönnig
#
# Changelog:
# studo, 2018_03_27, adopted initial implementation for Monitos4
#
# TODOs:
# a lot i'm sure
# 
from Nagstamon.Objects import Result
from Nagstamon.Objects import GenericHost
from Nagstamon.Objects import GenericService
from Nagstamon.Servers.Generic import GenericServer
from Nagstamon.Config import conf
from Nagstamon.Helpers import webbrowser_open

#monitos = 'monitos4'
#import logging
#logging.basicConfig( level=logging.INFO )
## logging.basicConfig(filename='nagstamon.log',level=logging.INFO)
#log = logging.getLogger(monitos)

import requests
from bs4 import BeautifulSoup

import copy
import datetime
import json
import logging
import sys
import time


def strfdelta(tdelta, fmt):
    d = {'days': tdelta.days}
    d['hours'], rem = divmod(tdelta.seconds, 3600)
    d['minutes'], d['seconds'] = divmod(rem, 60)
    return fmt.format(**d)


class Monitos4Server( GenericServer ):
    """A server running Monitos4 from Freicon GmbH & Co. KG
       http://www.monitos.de
       Tested with monitos 4.1
    """
    TYPE = 'Monitos4'
    
    MENU_ACTIONS = ['Monitor', 'Recheck', 'Acknowledge', 'Submit check result', 'Downtime']
    STATES_MAPPING = {'hosts' : {0 : 'UP', 1 : 'DOWN', 2 : 'UNREACHABLE', 4 : 'PENDING' },
                      'services' : {0 : 'OK', 1 : 'WARNING', 2 : 'CRITICAL', 3 : 'UNKNOWN', 4 : 'PENDING' }}
    STATES_MAPPING_REV = {'hosts' : { 'UP': 0, 'DOWN': 1, 'UNREACHABLE': 2, 'PENDING' : 4},
                          'services' : {'OK': 0, 'WARNING': 1, 'CRITICAL': 2, 'UNKNOWN': 3, 'PENDING' : 4}}
    BROWSER_URLS = { 'monitor': '$MONITOR$',
                    'hosts': '$MONITOR$', 
                    'services': '$MONITOR$',
                    'history': '$MONITOR$/#/alert/ticker'}

    def init_config(self):
        """
            Set URLs for CGI - they are static and there is no need to set them with every cycle
        """
        # log.info( 'Init monitos4 config at'+time.strftime( '%a %H:%M:%S' ) )
        # log.info( 'monitor_url is: '+self.monitor_url)
        # dummy default empty cgi urls - get filled later when server version is known
        self.cgiurl_services = None
        self.cgiurl_hosts = None

    def init_HTTP(self):
        """
            Initializing of session object
        """
        GenericServer.init_HTTP(self)

        self.session.auth = NoAuth()

        if len(self.session.cookies) == 0:
            form_inputs = dict()
            if '@' in self.username:
                user = self.username.split('@')
                form_inputs['module'] = 'ldap'
                form_inputs['_username'] = user[0]
            #if self.username.startswith('ldap:'):
            #    form_inputs['module'] = 'ldap'
            #    form_inputs['_username'] = self.username[5:]
            else:
                form_inputs['module'] = 'sv'
                form_inputs['_username'] = self.username

            form_inputs['urm:login:client'] = ''
            form_inputs['_password'] = self.password

            # call login page to get temporary cookie
            self.FetchURL('{0}/security/login'.format(self.monitor_url))
            # submit login form to retrieve authentication cookie
            self.FetchURL(
                '{0}/security/login_check'.format(self.monitor_url),
                cgi_data=form_inputs,
                multipart=True
            )

    def _get_status(self):
        """
            Get status from monitos4 Server - only JSON
        """
        # define CGI URLs for hosts and services
        if self.cgiurl_hosts == None:
            # hosts (up, down, unreachable or pending)
            # https://locmos41xsupport/rest/private/nagios/host 
            if self.use_autologin == True:
                self.cgiurl_hosts = self.monitor_cgi_url + '/rest/private/nagios/host' + '?authtoken=' + self.autologin_key
            else:
                self.cgiurl_hosts = self.monitor_cgi_url + '/rest/private/nagios/host'

            if conf.debug_mode == True:
                self.Debug(server=self.get_name(), debug='cgiurl_hosts is: ' + self.cgiurl_hosts)

        if self.cgiurl_services == None:
            # services (warning, critical, unknown or pending)
            # https://locmos41xsupport/rest/private/nagios/service_status/browser 
            if self.use_autologin == True:
                self.cgiurl_services = self.monitor_cgi_url + \
                                   '/rest/private/nagios/service_status/browser' + '?authtoken=' + self.autologin_key
            else:
                self.cgiurl_services = self.monitor_cgi_url + \
                                   '/rest/private/nagios/service_status/browser'

            if conf.debug_mode == True:
                self.Debug(server=self.get_name(), debug='cgiurl_services is: ' + self.cgiurl_services)

        self.new_hosts = dict()

        if conf.debug_mode == True:
            self.Debug(server=self.get_name(), debug='monitos4 Authtoken is: ' + self.autologin_key)

        # hosts
        try:
            form_data = dict()
            form_data['acknowledged'] = 1
            form_data['downtime'] = 1
            form_data['inactiveHosts'] = 0
            form_data['disabledNotification'] = 1
            form_data['limit_start'] = 0
            # Get all hosts
            form_data['limit_length'] = 99999
            #if self.use_autologin == True:
            #    form_data['authtoken'] = self.autologin_key

            result = self.FetchURL(
                self.cgiurl_hosts, giveback='raw', cgi_data=form_data)

            # authentication errors get a status code 200 too
            if result.status_code < 400 and \
                    result.result.startswith('<'):
                # in case of auth error reset HTTP session and try again
                self.reset_HTTP()
                result = self.FetchURL(
                    self.cgiurl_hosts, giveback='raw', cgi_data=form_data)

                if result.status_code < 400 and \
                        result.result.startswith('<'):
                    self.refresh_authentication = True
                    return Result(result=result.result,
                                  error='Authentication error',
                                  status_code=result.status_code)

            # purify JSON result
            jsonraw = copy.deepcopy(result.result.replace('\n', ''))
            error = copy.deepcopy(result.error)
            status_code = result.status_code

            if error != '' or status_code >= 400:
                return Result(result=jsonraw,
                              error=error,
                              status_code=status_code)

            self.check_for_error(jsonraw, error, status_code)
            if conf.debug_mode:
                self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 hosts are: ' + jsonraw)

            hosts = json.loads(jsonraw)

            for host in hosts['data']:
                h = dict(host)

                # Skip if Host is 'Pending'
                if type(h['sv_host__nagios_status__current_state']) is int and int(h['sv_host__nagios_status__current_state']) == 4:
                    continue

                # host
                host_name = h['sv_host__nagios__host_name']

                # If a host does not exist, create its object
                if host_name not in self.new_hosts:
                    self.new_hosts[host_name] = GenericHost()
                    self.new_hosts[host_name].name = host_name
                    self.new_hosts[host_name].svid = h['sv_host__svobjects____SVID']
                    self.new_hosts[host_name].server = self.name
                    self.new_hosts[host_name].status = self.STATES_MAPPING['hosts'][int(
                        h['sv_host__nagios_status__current_state'])]
                    self.new_hosts[host_name].last_check = datetime.datetime.fromtimestamp(
                        int(h['sv_host__nagios_status__last_check']))
                    self.new_hosts[host_name].attempt = h['sv_host__nagios__max_check_attempts']
                    self.new_hosts[host_name].status_information = h['sv_host__nagios_status__plugin_output']
                    if type(h['sv_host__nagios_status__checks_enabled']) is int:
                        self.new_hosts[host_name].passiveonly = not (int(h['sv_host__nagios_status__checks_enabled']))
                    if type(h['sv_host__nagios_status__is_flapping']) is int:
                        if int(h['sv_host__nagios_status__is_flapping']) != 0:
                            self.new_hosts[host_name].flapping = True
                    # 2017_11_06
                    if type(h['sv_host__nagios_status__problem_has_been_acknowledged']) is int:
                        if int(h['sv_host__nagios_status__problem_has_been_acknowledged']) != 0:
                            self.new_hosts[host_name].acknowledged = True
                    # 2017_11_06
                    if type(h['sv_host__nagios_status__scheduled_downtime_depth']) is int and int(h['sv_host__nagios_status__scheduled_downtime_depth']) != 0:
                        self.new_hosts[host_name].scheduled_downtime = True
                    
                    # 2017_11_06 Skip if Host has notifications disabled
                    if type(h['sv_host__nagios_status__notifications_enabled']) is int:
                        if int(h['sv_host__nagios_status__notifications_enabled']) == 0:
                            self.new_hosts[host_name].notifications_disabled = True

                    if type( h['sv_host__nagios_status__state_type']) is int:
                        self.new_hosts[host_name].status_type = 'soft' if int(
                            h['sv_host__nagios_status__state_type']) == 0 else 'hard'

                    # extra duration needed for calculation
                    duration = datetime.datetime.now(
                    ) - datetime.datetime.fromtimestamp(int(h['sv_host__nagios_status__last_state_change']))

                    self.new_hosts[host_name].duration = strfdelta(
                        duration, '{days}d {hours}h {minutes}m {seconds}s')

                del h, host_name
        except:
            import traceback
            traceback.print_exc(file=sys.stdout)

            # set checking flag back to False
            self.isChecking = False
            result, error = self.Error(sys.exc_info())
            return Result(result=result, error=error)

        # services
        # 2018_03_27
        # https://locmos41xsupport/rest/private/nagios/service_status/browser
        try:
            form_data = dict()
            form_data['acknowledged'] = 1
            form_data['downtime'] = 1
            form_data['inactiveHosts'] = 0
            form_data['disabledNotification'] = 1
            form_data['softstate'] = 1
            form_data['limit_start'] = 0
            # Get all services
            form_data['limit_length'] = 99999
            #if self.use_autologin == True:
            #    form_data['authtoken'] = self.autologin_key

            result = self.FetchURL(self.cgiurl_services,
                                   giveback='raw', cgi_data=form_data)

            # purify JSON result
            jsonraw = copy.deepcopy(result.result.replace('\n', ''))
            error = copy.deepcopy(result.error)
            status_code = result.status_code

            if error != '' or status_code >= 400:
                return Result(result=jsonraw,
                              error=error,
                              status_code=status_code)

            self.check_for_error(jsonraw, error, status_code)

            services = json.loads(jsonraw)

            for service in services['data']:
                s = dict(service)

                # Skip if Host or Service is 'Pending'
                if int(s['sv_service_status__nagios_status__current_state']) == 4 or int(
                        s['sv_host__nagios_status__current_state']) == 4:
                    continue

                # host and service
                # 2017_11_09, this is a hack
                host_name = s['sv_host__nagios__host_name']
                service_name = s['sv_service_status__nagios__service_description']
                # service_name = s['sv_service_status__svobjects__rendered_label']
                display_name = s['sv_service_status__nagios__service_description']

                # If a service does not exist, create its object
                if service_name not in self.new_hosts[host_name].services:
                    self.new_hosts[host_name].services[service_name] = GenericService(
                    )
                    self.new_hosts[host_name].services[service_name].host = host_name
                    self.new_hosts[host_name].services[service_name].svid = s['sv_service_status__svobjects____SVID']
                    self.new_hosts[host_name].services[service_name].name = display_name
                    # self.new_hosts[host_name].services[service_name].name = service_name
                    self.new_hosts[host_name].services[service_name].server = self.name
                    self.new_hosts[host_name].services[service_name].status = self.STATES_MAPPING['services'][int(
                        s['sv_service_status__nagios_status__current_state'])]
                    self.new_hosts[host_name].services[service_name].last_check = datetime.datetime.fromtimestamp(
                        int(s['sv_service_status__nagios_status__last_check']))
                    self.new_hosts[host_name].services[service_name].attempt = s[
                        'sv_service_status__nagios__max_check_attempts']
                    self.new_hosts[host_name].services[service_name].status_information = BeautifulSoup(
                        s['sv_service_status__nagios_status__plugin_output'].replace(
                            '\n', ' ').strip(),
                        'html.parser').text
                    self.new_hosts[host_name].services[service_name].passiveonly = not (
                        int(s['sv_service_status__nagios_status__checks_enabled']))
                    if int(s['sv_service_status__nagios_status__is_flapping']) != 0:
                        self.new_hosts[host_name].services[service_name].flapping = True
                    
                    # 2017_11_05
                    if int(s['sv_service_status__nagios_status__problem_has_been_acknowledged']) != 0:
                        self.new_hosts[host_name].services[service_name].acknowledged = True
                    # 2017_11_06
                    if int(s['sv_service_status__nagios_status__scheduled_downtime_depth']) != 0:
                        self.new_hosts[host_name].services[service_name].scheduled_downtime = True
                    # 2017_11_06 Skip if Host or Service has notifications disabled
                    if int(s['sv_service_status__nagios_status__notifications_enabled']) == 0 or int(s['sv_host__nagios_status__notifications_enabled']) == 0:
                        self.new_hosts[host_name].services[service_name].notifications_disabled = True
 

                    self.new_hosts[host_name].services[service_name].status_type = 'soft' if int(
                        s['sv_service_status__nagios_status__state_type']) == 0 else 'hard'

                    # acknowledge needs service_description and no display name
                    self.new_hosts[host_name].services[service_name].real_name = s[
                        'sv_service_status__nagios__service_description']

                    # extra duration needed for calculation
                    duration = datetime.datetime.now(
                    ) - datetime.datetime.fromtimestamp(
                        int(s['sv_service_status__nagios_status__last_state_change']))
                    self.new_hosts[host_name].services[service_name].duration = strfdelta(
                        duration, '{days}d {hours}h {minutes}m {seconds}s')

                del s, host_name, service_name
        except:
            import traceback
            traceback.print_exc(file=sys.stdout)

            # set checking flag back to False
            self.isChecking = False
            result, error = self.Error(sys.exc_info())
            return Result(result=result, error=error)

        del jsonraw, error, hosts

        # dummy return in case all is OK
        return Result()

    def _set_recheck(self, host, service):
        """
            Do a POST-Request to recheck the given host or service in monitos4

            :param host: String - Host name
            :param service: String - Service name
        """
        # log.info('info_dict is: %s', info_dict )
        form_data = dict()
        form_data['commandName'] = 'check-now'

        # TODO: 2018_03_27, test endpoint
        # https://locmos41xsupport/rest/private/nagios/command/execute
        try:
            if service == '':
                if conf.debug_mode:
                    self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 _set_recheck, host is: ' + self.hosts[host].svid)
                form_data['params'] = json.dumps({'__SVID': self.hosts[host].svid})
                form_data['commandType'] = 'sv_host'
            else:
                if conf.debug_mode:
                    self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 _set_recheck, service is: ' + self.hosts[host].services[service].svid)
                    self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 _set_recheck, services are: ' + repr( self.hosts[host].services ) )
                form_data['params'] = json.dumps({'__SVID': self.hosts[host].services[service].svid})
                form_data['commandType'] = 'sv_service_status'

            self.session.post(
                '{0}/rest/private/nagios/command/execute'.format(self.monitor_url), data=form_data)

        except:
            import traceback
            traceback.print_exc(file=sys.stdout)
            result, error = self.Error(sys.exc_info())
            return Result(result=result, error=error, status_code=-1)

    def _set_acknowledge(self, host, service, author, comment, sticky, notify, persistent, all_services=[]):
        """
            Do a POST-Request to set an acknowledgement for a host, service or host with all services in monitos4

            :param host: String - Host name
            :param service: String - Service name
            :param author: String - Author name (username)
            :param comment: String - Additional comment
            :param sticky: Bool - Sticky Acknowledgement
            :param notify: Bool - Send Notifications
            :param persistent: Bool - Persistent comment
            :param all_services: Array - List of all services (filled only if 'Acknowledge all services on host' is set)
        """

        # 2017_11_07
        if conf.debug_mode:
            self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 _set_acknowledge host is: ' + host)
            if service != '':  # service
                self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 _set_acknowledge service is: ' + service)

        try:
            form_data = dict()

            if len(all_services) > 0:       # Host & all Services
                form_data['commandType'] = 'sv_host'
                form_data['commandName'] = 'acknowledge-host-service-problems'
                form_data['params'] = json.dumps({'__SVID': self.hosts[host].svid, 'comment': comment, 'notify': int(notify), 'persistent': int(persistent), 'sticky': int(sticky)})
            elif service == '':             # Host
                form_data['commandType'] = 'sv_host'
                form_data['commandName'] = 'acknowledge-problem'
                form_data['params'] = json.dumps(
                    {'__SVID': self.hosts[host].svid, 'comment': comment, 'notify': int(notify), 'persistent': int(persistent),
                     'sticky': int(sticky)})
            else:  # Service
                form_data['commandType'] = 'sv_service_status'
                form_data['commandName'] = 'acknowledge-problem'
                form_data['params'] = json.dumps(
                    {'__SVID': self.hosts[host].services[service].svid, 'comment': comment, 'notify': int(notify),
                     'persistent': int(persistent), 'sticky': int(sticky)})

            # TODO: 2018_03_27, test endpoint
            # https://locmos41xsupport/rest/private/nagios/command/execute
            self.session.post(
                '{0}/rest/private/nagios/command/execute'.format(self.monitor_url), data=form_data)

        except:
            import traceback
            traceback.print_exc(file=sys.stdout)
            result, error = self.Error(sys.exc_info())
            return Result(result=result, error=error, status_code=-1)


    def _set_submit_check_result(self, host, service, state, comment, check_output, performance_data):
        """
            Do a POST-Request to submit a check result to monitos4

            :param host: String - Host name
            :param service: String - Service name
            :param state: String - Selected state
            :param comment: NOT IN USE - String - Additional comment
            :param check_output: String - Check output
            :param performance_data: String - Performance data
        """
        if conf.debug_mode:
            self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' mos3 _set_submit_check_result, host is: ' + host)
            if service != '':  # service
                self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' mos3 _set_submit_check_result, service is: ' + service)
        try:
            state = state.upper()

            form_data = dict()
            form_data['commandName'] = 'process-check-result'

            # TODO 'state' contains wrong information
            # Variable 'state' can contain any standard state
            # ('up','down','unreachable', 'ok', 'warning', 'critical' or 'unknown')
            # Selecting something else for example 'information' or 'disaster' puts 'ok' into the variable state
            # This makes it impossible to log errors for unsupported states because you can't differentiate
            # between selecting 'ok' and 'information' because in both cases the variable contains 'ok'
            # log.info('Selecting an unsupported check result submits \'UP\' for hosts and \'OK\' for services!')

            if service == '':  # Host
                form_data['commandType'] = 'sv_host'

                if state == 'OK' or state == 'UNKNOWN':
                    # log.info('Setting OK or UNKNOWN to UP')
                    state = 'UP'

                state_number = self.STATES_MAPPING_REV['hosts'][state]

                if performance_data == '':
                    form_data['params'] = json.dumps(
                        {'__SVID': self.hosts[host].svid, 'status_code': state_number, 'plugin_output': check_output})
                else:
                    form_data['params'] = json.dumps({'__SVID': self.hosts[host].svid, 'status_code': state_number,
                                                      'plugin_output': check_output + ' | ' + performance_data})
            else:  # Service
                form_data['commandType'] = 'sv_service_status'

                state_number = self.STATES_MAPPING_REV['services'][state]

                if performance_data == '':
                    form_data['params'] = json.dumps(
                        {'__SVID': self.hosts[host].services[service].svid, 'status_code': state_number,
                         'plugin_output': check_output})
                else:
                    form_data['params'] = json.dumps(
                        {'__SVID': self.hosts[host].services[service].svid, 'status_code': state_number,
                         'plugin_output': check_output + ' | ' + performance_data})

            # TODO: 2018_03_27, test endpoint
            # https://locmos41xsupport/rest/private/nagios/command/execute
            self.session.post(
                '{0}/rest/private/nagios/command/execute'.format(self.monitor_url), data=form_data)

        except:
            import traceback
            traceback.print_exc(file=sys.stdout)
            result, error = self.Error(sys.exc_info())
            return Result(result=result, error=error, status_code=-1)

    def _set_downtime(self, host, service, author, comment, fixed, start_time, end_time, hours, minutes):
        """
            Do a PUT-Request to create a downtime for a host or service in monitos4

            :param host: String - Host name
            :param service: String - Service name
            :param author: String - Author name (username)
            :param comment: String - Additional comment
            :param fixed: Bool - Fixed Downtime
            :param start_time: String - Date in Y-m-d H:M:S format - Start of Downtime
            :param end_time: String - Date in Y-m-d H:M:S format - End of Downtime
            :param hours: NOT SUPPORTED - Integer - Flexible Downtime
            :param minutes: NOT SUPPORTED - Integer - Flexible Downtime


            curl 'https://locmos41xsupport/api/downtime' -H 'Accept: application/vnd.monitos.v2+json' -H 'Referer: https://locmos41xsupport/' -H 'Origin: https://locmos41xsupport' -H 'X-Requested-With: XMLHttpRequest' -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.108 Safari/537.36' -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' --data 'type=sv_host&end=1523049540&comment=TESTUSTESTUS&includeServices=true&includeChildren=false&id=003f'
            curl 'https://locmos41xsupport/api/downtime'
            data 
            type=sv_host&
            end=1523049540&
            comment=TESTUSTESTUS&
            includeServices=true&
            includeChildren=false&
            id=003f
        """
        if conf.debug_mode:
            self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 _set_downtime host is: ' + host)
            if service != '':  # service
                self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 _set_downtime service is: ' + service)
        try:
            form_data = dict()

            if service == '':
                form_data['type'] = 'sv_host'
                form_data['includeServices'] = 'true'
                form_data['includeChildren'] = 'false'
                # form_data['host_effects'] = 'hostOnly'
                form_data['id'] = self.hosts[host].svid
                # form_data['svid'] = self.hosts[host].svid
            else:
                form_data['type'] = 'sv_service_status'
                form_data['service'] = self.hosts[host].services[service].svid
                # form_data['svid'] = self.hosts[host].services[service].svid

            # Format start_time and end_time from user-friendly format to timestamp
            start_time = time.mktime(datetime.datetime.strptime(
                start_time, "%Y-%m-%d %H:%M:%S").timetuple())
            start_time = str(start_time).split('.')[0]

            end_time = time.mktime(datetime.datetime.strptime(
                end_time, "%Y-%m-%d %H:%M:%S").timetuple())
            end_time = str(end_time).split('.')[0]

            form_data['start'] = start_time
            form_data['end'] = end_time
            form_data['comment'] = comment
            form_data['is_recurring'] = 'false'
            form_data['schedule_now'] = 'false'

            if conf.debug_mode:
                # self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 _set_downtime, form_data are: ' + repr( form_data ) )
                self.Debug(server=self.get_name(), debug=time.strftime('%a %H:%M:%S') + ' monitos4 _set_downtime url: ' + '{0}/api/downtime'.format(self.monitor_url) + repr(form_data))

            # TODO: 2018_03_27, test endpoint
            # https://locmos41xsupport/api/downtime / POST
            self.session.post('{0}/api/downtime'.format(self.monitor_url), data=form_data)
            # self.session.put('{0}/api/downtime'.format(self.monitor_url), data=form_data)

        except:
            import traceback
            traceback.print_exc(file=sys.stdout)
            result, error = self.Error(sys.exc_info())
            return Result(result=result, error=error, status_code=-1)


    def get_start_end(self, host):
        """
            Set default of start time to "now" and end time is "now + 24 hours"

            :param host: String - Host name
        """
        # log.info("Flexible Downtimes are not supported in monitos4")

        start = datetime.datetime.now()
        end = datetime.datetime.now() + datetime.timedelta(hours=24)

        return str(start.strftime("%Y-%m-%d %H:%M:%S")), str(end.strftime("%Y-%m-%d %H:%M:%S"))

    def open_monitor(self, host, service=''):
        """
            Open specific Host or Service in monitos4 browser

            :param host: String - Host name
            :param service: String - Service name
        """
        if service == '':
            url = '{0}/#/object/details/{1}'.format(
                self.monitor_url, self.hosts[host].svid)
        else:
            url = '{0}/#/object/details/{1}'.format(
                self.monitor_url, self.hosts[host].services[service].svid)

        webbrowser_open(url)


class NoAuth(requests.auth.AuthBase):
    """
        Override to avoid auth headers
        Needed for LDAP login
    """

    def __call__(self, r):
        return r
