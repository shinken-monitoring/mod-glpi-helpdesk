#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright (C) 2009-2012:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel@goebel-consult.de
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


from shinken.basemodule import BaseModule
from shinken.log import logger

properties = {
    'daemons': ['broker', 'webui'],
    'type': 'glpi-helpdesk',
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
        
        self.ws_connection = None
        self.is_connected = False
        
    def init(self):
        logger.info("[glpi-helpdesk] Connecting to %s" % self.uri)
        self.ws_connection = xmlrpclib.ServerProxy(self.uri)
        logger.info("[glpi-helpdesk] Connection opened")
        logger.info("[glpi-helpdesk] Authentication in progress...")
        
        self.is_connected = False
        
        try:
            res = self.ws_connection.glpi.doLogin( {'login_name': self.login_name, 'login_password': self.login_password} )
            self.session = res['session']
            logger.info("[glpi-helpdesk] Authenticated, session : %s", str(self.session))
            
            self.is_connected = True
            
            self.helpdesk_configuration = self.ws_connection.kiosks.getHelpdeskConfiguration( {'session': self.session } )
            self.helpdesk_configuration['session'] = self.session
            logger.info("[glpi-helpdesk] helpdesk configuration: %s", self.helpdesk_configuration)
        except xmlrpclib.Fault as err:
            logger.error("[glpi-helpdesk] Authentication refused, fault code: %d (%s)", err.faultCode, err.faultString)
            raise GlpiTicketsError

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

    def getTickets(self, host_name):
        if not host_name in self.hosts_cache or self.hosts_cache[host_name]['items_id'] is None:
            logger.warning("[glpi-helpdesk] getTickets, host is not defined in Glpi : %s.", host_name)
            return
            
        # Glpi Web service listTickets arguments :https://forge.indepnet.net/projects/webservices/wiki/GlpilistTickets
        # Get all tickets for the current host ...
        arg = {'session': self.session
               , 'entity': self.hosts_cache[host_name]['entities_id']
               , 'itemtype': self.hosts_cache[host_name]['itemtype']
               , 'item': self.hosts_cache[host_name]['items_id']
               , 'id2name': 1
        }
               
        # Connect Glpi Web service to get a list of host tickets
        tickets = []
        try:
            logger.info("[glpi-helpdesk] getTickets, arg: %s", arg)
            records = self.ws_connection.glpi.listTickets(arg)
            logger.debug("[glpi-helpdesk] getTickets, cr: %s", records)
            for ticket in records:
                # Get all ticket information ...
                arg = {'session': self.session
                       , 'ticket': ticket['id']
                       , 'id2name': 1
                }
                
                logger.info("[glpi-helpdesk] getTicket, arg: %s", arg)
                ticket = self.ws_connection.glpi.getTicket(arg)
                logger.debug("[glpi-helpdesk] getTicket, cr: %s", ticket)
                tickets.append(ticket)
            
        except Exception as e:
            logger.error("[glpi-helpdesk] error when fetching tickets list : %s" % str(e))
            
        return tickets
    
    def createTicketFollowUp(self):
        # Glpi Web service listTickets arguments :https://forge.indepnet.net/projects/webservices/wiki/GlpilistTickets
        # Get all not closed tickets for the current host ...
        arg = {'session': self.session
               , 'entity': data['customs']['_ENTITIESID']
               , 'itemtype': data['customs']['_ITEMTYPE']
               , 'item': data['customs']['_ITEMSID']
               , 'id2name': 1
               , 'status': 'notclosed'
        }
               
        # Connect Glpi Web service to get a list of host tickets
        try:
            ws_report = self.ws_connection.glpi.listTickets(arg)
            
            for ticket in ws_report:
                logger.debug("[glpi-helpdesk] ticket : %s" % ticket['name'])
                
                # If the ticket is a DOWN or UNREACHABLE status notification ...
                if ticket['name'] == 'Host status : %s is DOWN' % data['host_name'] or ticket['name'] == 'Host status : %s is UNREACHABLE' % data['host_name']:
                    logger.debug("[glpi-helpdesk] found interesting ticket: %s" % ticket['id'])
                    
                    # Glpi Web service addTicketFollowup arguments : https://forge.indepnet.net/projects/webservices/wiki/GlpicreateTicket
                    arg = {'session': self.session
                           , 'ticket': ticket['id']
                           , 'content': 'Host %s is still %s\n%s' % (data['host_name'], data['state'], data['output'])
                    }
                           
                    # Connect Glpi Web service to add a follow-up to the ticket
                    try:
                        ws_report = self.ws_connection.glpi.addTicketFollowup(arg)
                        logger.info("[glpi-helpdesk] add ticket follow-up to %s" % ticket['id'])
                    except:
                        logger.error("[glpi-helpdesk] error when creating follow-up for the ticket %s" % ticket['id'])
        except Exception as e:
            logger.error("[glpi-helpdesk] error when fetching tickets list : %s" % str(e))

######################## WebUI part ############################

    # Get the helpdesk configuration ...
    def get_ui_helpdesk_configuration(self):
        logger.debug("[glpi-helpdesk] get_ui_helpdesk_configuration")

        return self.helpdesk_configuration

    # Get the helpdesk tickets ...
    def get_ui_tickets(self, name):
        logger.debug("[glpi-helpdesk] get_ui_tickets, name: %s", name)
        hostname = None
        service = None
        if name is not None:
            hostname = name
            if '/' in name:
                service = name.split('/')[1]
                hostname = name.split('/')[0]
        logger.debug("[glpi-helpdesk] get_ui_tickets, host/service: %s/%s", hostname, service)

        records = None
        try:
            logger.debug("[glpi-helpdesk] Fetching tickets from Glpi for host/service: '%s/%s'", hostname, service)

            records = self.getTickets(hostname)
        except Exception, exp:
            logger.error("[glpi-helpdesk] Exception when querying database: %s", str(exp))

        return records

    # Request for a ticket creation
    def set_ui_ticket(self, parameters):
        logger.info("[glpi-helpdesk] request to create a ticket with %s", parameters)
        
        # Glpi WS interface
            
        # Connect Glpi Web service to create a ticket
        try:
            parameters['session'] = self.session
            ws_report = self.ws_connection.glpi.createTicket(parameters)
            logger.info("[glpi-helpdesk] created a new ticket: %s" % ws_report['id'])
            return ws_report
        except Exception as e:
            logger.error("[glpi-helpdesk] error when creating a new ticket : %s" % str(e))
            
        return None
