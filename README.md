
=========================================
Shinken GLPI integration - Glpi-helpdesk
=========================================

Shinken module for using Glpi helpdesk in the WebUI.

For people not familiar with GLPI, it is an Open-Source CMDB. Applicable to servers, routers, printers or anything you want for that matter. It is also a help-desk tool. GLPI also integrates with tools like FusionInventory for IT inventory management.

This version works with plugin Webservices for GLPI from version 0.84.

When this module is installed and configured properly, the Shinken WebUI adds a tab in the element view that allows to:

- list the Glpi tickets associated with a monitored host

- create a ticket for the current host


Requirements 
=============

  - Compatible version of GLPI Shinken module and GLPI version

      The current version needs: 
       - plugin WebServices for GLPI

       See https://forge.indepnet.net to get the plugins.


      

Enabling glpi-helpdesk Shinken module 
======================================

To use the glpi-helpdesk module you must declare it in your WebUI configuration.

```

  define module {
      ... 

      modules    	 ..., glpi-helpdesk

  }
```

The module configuration is defined in the file: glpi-helpdesk.cfg.

Default configuration needs to be tuned up to your Glpi configuration. 

At first, you need to activate and configure the GLPI WebServices to allow 
connection from your Shinken server.
Then you set the WS URI (uri) and the login information (login_name / login_password) 
parameters in the configuration file.


Default configuration file is as is :
```
   ## Module:      glpi-helpdesk
   ## Loaded by:   WebUI

   # GLPI needs Webservices plugin to be installed and enabled.
   define module {
       module_name     glpi-helpdesk
       module_type     glpi-helpdesk

       # Glpi Web service URI
       uri             http://localhost/plugins/webservices/xmlrpc.php
       # Default : shinken
       login_name      shinken
       # Default : shinken
       login_password  shinken
   }
```
