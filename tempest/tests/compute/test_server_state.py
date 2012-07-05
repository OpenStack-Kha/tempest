from tempest import openstack
import unittest2 as unittest
from nose.plugins.attrib import attr
import os
import subprocess
from paramiko import SSHClient
from paramiko import AutoAddPolicy
import tempest.config
from tempest.common.utils.data_utils import rand_name
from tempest import exceptions
import re


class VMstateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.os = openstack.Manager()
        cls.client = cls.os.servers_client
        cls.config = cls.os.config
        cls.image_ref = cls.config.compute.image_ref
        cls.flavor_ref = cls.config.compute.flavor_ref 
        cls.login_name = cls.config.compute.login_name
        cls.pswd = cls.config.compute.pswd
        
    def setUp(self):
        self.name = rand_name('server')
        resp, server = self.client.create_server(self.name,
                                                 self.image_ref,
                                                 self.flavor_ref)
        self.server_id = server['id'] 
        self.client.wait_for_server_status(self.server_id, 'ACTIVE')
        
    def tearDown(self):
        self.client.delete_server(self.server_id)
    
    @attr(type='positive')
    def test_suspend_resume_server(self): 
        """The server should have ACTIVE status after the suspend-resume procedure"""            
        self.client.suspend(self.server_id)
        self.client.wait_for_server_status(self.server_id, 'SUSPENDED')
        self.client.resume(self.server_id)
        self.client.wait_for_server_status(self.server_id, 'ACTIVE')
        resp, body=self.client.get_server(self.server_id)       
        self.assertEqual("ACTIVE",body['status'])
        
    @attr(type='positive')    
    def test_ping_server(self):
        """The sever should ping the Internet and other servers from the same subnet"""    
        resp, body=self.client.get_server(self.server_id)       
        # Find IP of server
        try:
            (_, network) = body['addresses'].popitem()
            ip = network[0]['addr']
        except KeyError:
            self.fail("Failed to retrieve IP address from server entity")
                
        params = {'status': 'active'}
        data,sbody=self.client.list_servers_with_detail(params)        
        servers=[]         
        
        # Get the list of active servers from the same subnet
        for i in sbody['servers']:            
            (_, network) = i['addresses'].popitem()
            iip = network[0]['addr']
            servers.append(iip)        
                
        # regexp
        exp=re.compile(r"0% packet loss")   
       
        #ssh into server     
        ssh=SSHClient()
        ssh.set_missing_host_key_policy(AutoAddPolicy())
        ssh.connect(ip,username=self.login_name,password=self.pswd)
        # Try to ping the internet
        stdin, stdout, stderr=ssh.exec_command("ping -c2 8.8.8.8")
        # Read the output
        bufferdata = stdout.read() 
        # Check if internet is available
        if exp.search(bufferdata):
            isping="0% packet loss"
        self.assertEqual("0% packet loss", isping)
        ping = ""       
        for j in servers:            
            stdin, stdout, stderr=ssh.exec_command("ping -c2 "+j)           
            buffer = stdout.read()
            if exp.search(buffer):
                ping="0% packet loss"
            self.assertEqual("0% packet loss", ping, "The severs with ip "+j+" is unavailable")
            
      
    
            



          
    
        
   
        
        
        
    
        