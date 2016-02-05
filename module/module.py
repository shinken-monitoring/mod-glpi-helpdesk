#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright (C) 2009-2016:
#    Frederic Mohier, frederic.mohier@gmail.com
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shinken is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Shinken.  If not, see <http://www.gnu.org/licenses/>.


# This Class is a plugin for the Shinken Broker. It is in charge
# to brok information into the glpi database. for the moment
# only Mysql is supported. This code is __imported__ from Broker.
# The managed_brok function is called by Broker for manage the broks. It calls
# the manage_*_brok functions that create queries, and then run queries.

import xmlrpclib
import time
import sys
import traceback


from shinken.basemodule import BaseModule
from shinken.log import logger

properties = {
    'daemons': ['broker', 'webui'],
    'type': 'helpdesk',
    'external': False
}


# Called by the plugin manager to get a broker
def get_instance(plugin):
    logger.info("[glpi-helpdesk] Get a Glpi helpdesk module for plugin %s" % plugin.get_name())
    instance = GlpiHelpdesk_broker(plugin)
    return instance


class GlpiTicketsError(Exception):
    pass


# Class for the glpi-helpdesk Broker
class GlpiHelpdesk_broker(BaseModule):
    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)

        self.hosts_cache = {}

        self.uri = getattr(modconf, 'uri', 'http://localhost/glpi/plugins/webservices/xmlrpc.php')
        self.login_name = getattr(modconf, 'login_name', 'shinken')
        logger.info("[glpi-helpdesk] Glpi Web Service host:login: %s:%s", self.uri, self.login_name)
        self.login_password = getattr(modconf, 'login_password', 'shinken')

        self.source = getattr(modconf, 'source', 'Shinken')
        logger.info("[glpi-helpdesk] Glpi Web Service source: %s", self.source)

        self.ws_connection = None
        self.is_connected = False

    def init(self):
        self.is_connected = False

        try:
            logger.info("[glpi-helpdesk] Connecting to %s" % self.uri)
            self.ws_connection = xmlrpclib.ServerProxy(self.uri)
            logger.info("[glpi-helpdesk] Connection opened")

            logger.info("[glpi-helpdesk] Authentication in progress...")
            res = self.ws_connection.glpi.doLogin( {'login_name': self.login_name, 'login_password': self.login_password} )
            self.session = res['session']
            logger.info("[glpi-helpdesk] Authenticated, session : %s", str(self.session))

            self.is_connected = True
        except xmlrpclib.Fault as err:
            logger.error("[glpi-helpdesk] Authentication refused, fault code: %d (%s)", err.faultCode, err.faultString)
            raise GlpiTicketsError


        try:
            self.helpdesk_configuration = self.ws_connection.glpi.getHelpdeskConfiguration( {'session': self.session } )
            self.helpdesk_configuration['session'] = self.session
            logger.info("[glpi-helpdesk] helpdesk configuration: %s", self.helpdesk_configuration)
        except xmlrpclib.Fault as err:
            logger.error("[glpi-helpdesk] error when getting helpdesk configuration, fault code: %d (%s)", err.faultCode, err.faultString)
            raise GlpiTicketsError

    # Give a link for the Web UI menu
    def get_external_ui_link(self):
        return {'label': 'Glpi', 'uri': self.uri.replace('/plugins/webservices/xmlrpc.php', '')}

    # Get a brok ...
    def manage_brok(self, b):
        # Build initial host state cache
        if b.type == 'initial_host_status':
            host_name = b.data['host_name']
            logger.debug("[glpi-helpdesk] initial host status : %s", host_name)

            try:
                logger.debug("[glpi-helpdesk] initial host status : %s : %s", host_name, b.data['customs'])
                self.hosts_cache[host_name] = {'hostsid': b.data['customs']['_HOSTID'], 'itemtype': b.data['customs']['_ITEMTYPE'], 'items_id': b.data['customs']['_ITEMSID'], 'entities_id': b.data['customs']['_ENTITIESID'] }
            except:
                self.hosts_cache[host_name] = {'items_id': None}
                logger.warning("[glpi-helpdesk] no custom _HOSTID and/or _ITEMTYPE and/or _ITEMSID and/or _ENTITIESID for %s", host_name)
            else:
                logger.info("[glpi-helpdesk] initial host status : %s is %s", host_name, self.hosts_cache[host_name])

        if b.type == 'schedule_host_downtime':
            host_name = b.data['host_name']
            logger.warning("[glpi-helpdesk] received brok for host downtime: %s", host_name)

            if host_name in self.hosts_cache and self.hosts_cache[host_name]['items_id']:
                start = time.time()
                # self.record_host_check_result(b)
                logger.debug("[glpi-helpdesk] host downtime scheduled: %s, %d seconds", host_name, time.time() - start)

        if b.type == 'schedule_service_downtime':
            host_name = b.data['host_name']
            service = b.data['service_description']
            logger.warning("[glpi-helpdesk] received brok for service downtime: %s/%s", host_name, service)

        return

    def getTicket(self, id):
        # Get a ticket ...
        args = {
            'session': self.session
            , 'ticket': id
            , 'id2name': 1
            , 'iso8859': 1
        }

        logger.debug("[glpi-helpdesk] getTicket, args: %s", args)
        ticket = None
        try:
            ticket = self.ws_connection.glpi.getTicket(args)
            logger.info("[glpi-helpdesk] getTicket, cr: %s", ticket)
        except xmlrpclib.Fault as err:
            logger.error("[glpi-helpdesk] getTicket WS error: %d (%s)" % (err.faultCode, err.faultString))
            pass

        return ticket

    def getTickets(self, host_name=None, status=None, count=50, list_only=True):
        if host_name:
            if not host_name in self.hosts_cache or self.hosts_cache[host_name]['items_id'] is None:
                logger.warning("[glpi-helpdesk] getTickets, host is not defined in Glpi : %s.", host_name)
                return

        # Glpi Web service listTickets arguments :https://forge.indepnet.net/projects/webservices/wiki/GlpilistTickets
        args = {
            'session': self.session
            , 'id2name': 1
            , 'iso8859': 1
            , 'limit': count
        }
        # Get tickets for a specific host
        # Do not specify entity, only itemtype/items_id to find all tickets relating to an host.
        if host_name:
            args['itemtype'] = self.hosts_cache[host_name]['itemtype']
            args['item'] = self.hosts_cache[host_name]['items_id']

        if status:
            # // keywords:
            # all
            # notclosed
            # notold
            # old
            # process
            # // Tickets status:
            # const INCOMING      = 1; // new
            # const ASSIGNED      = 2; // assign
            # const PLANNED       = 3; // plan
            # const WAITING       = 4; // waiting
            # const SOLVED        = 5; // solved
            # const CLOSED        = 6; // closed
            # const ACCEPTED      = 7; // accepted
            # const OBSERVED      = 8; // observe
            # const EVALUATION    = 9; // evaluation
            # const APPROVAL      = 10; // approbation
            # const TEST          = 11; // test
            # const QUALIFICATION = 12; // qualification
            args['status'] = status

        # Connect Glpi Web service to get a list of host tickets
        tickets = []
        try:
            logger.info("[glpi-helpdesk] getTickets, args: %s", args)
            try:
                records = self.ws_connection.glpi.listTickets(args)
            except xmlrpclib.Fault as err:
                logger.error("[glpi-helpdesk] listTickets WS error: %d (%s)" % (err.faultCode, err.faultString))
                return None

            logger.info("[glpi-helpdesk] getTickets, cr: %s", records)
            if list_only:
                return records
            else:
                for record in records:
                    ticket = self.getTicket(record['id'])
                    if ticket:
                        tickets.append(ticket)
        except Exception:
            logger.error("[glpi-helpdesk] error when fetching tickets list : %s" % traceback.format_exc())

        return tickets

######################## WebUI part ############################

    # Get the WS session identifier ...
    def get_ui_session(self):
        logger.debug("[glpi-helpdesk] get_ui_session")

        return self.session

    def get_ui_helpdesk_configuration(self):
        """
        Get the helpdesk configuration parameters:
        - tickets types
        - tickets categories
        - tickets solutions
        - tickets templates
        """
        logger.debug("[glpi-helpdesk] get_ui_helpdesk_configuration")

        return self.helpdesk_configuration

    def get_ui_ticket(self, id):
        """
        Get a ticket ...
        """
        logger.debug("[glpi-helpdesk] get_ui_ticket, id: %s", id)

        return self.getTicket(id)

    def get_ui_tickets(self, name=None, status=None, count=50, list_only=True):
        """
        Get the helpdesk tickets for a computer ...
        """
        logger.debug("[glpi-helpdesk] get_ui_tickets, name: %s, status: %s", name, status)
        hostname = None
        service = None
        if name is not None:
            hostname = name
            if '/' in name:
                service = name.split('/')[1]
                hostname = name.split('/')[0]

        records = None
        try:
            logger.debug("[glpi-helpdesk] Fetching tickets from Glpi for host: %s, status: %s", hostname, status)

            records = self.getTickets(hostname, status, count)
        except Exception:
            logger.error("[glpi-helpdesk] error when calling getTickets: %s" % traceback.format_exc())

        return records

    def set_ui_ticket(self, parameters):
        """
        Request for a ticket creation
        """
        logger.info("[glpi-helpdesk] request to create a ticket with %s", parameters)

        # Connect Glpi Web service to create a ticket
        try:
            parameters['session'] = self.session
            parameters['source'] = self.source
            # TODO: check provided parameters

            ws_report = self.ws_connection.glpi.createTicket(parameters)
            logger.info("[glpi-helpdesk] created a new ticket: %s" % ws_report['id'])
            return ws_report
        except Exception as e:
            logger.error("[glpi-helpdesk] error when creating a new ticket: %s" % str(e))

        return None

    # Request for a ticket follow-up creation
    def set_ui_ticket_followup(self, parameters):
        logger.info("[glpi-helpdesk] request to create a ticket follow-up with %s", parameters)

        # Connect Glpi Web service to create a ticket
        try:
            parameters['session'] = self.session
            parameters['source'] = self.source
            # TODO: check provided parameters

            ws_report = self.ws_connection.glpi.addTicketFollowup(parameters)
            logger.info("[glpi-helpdesk] created a ticket follow-up: %s" % ws_report['id'])
            return ws_report
        except Exception as e:
            logger.error("[glpi-helpdesk] error when creating a new ticket follow-up: %s" % str(e))

        return None
