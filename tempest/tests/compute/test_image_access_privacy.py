import unittest
from tempest.openstack import Manager, AdminManager

import tempest

from tempest.services.network.json.network_client import NetworkClient
from tempest.services.identity.json.admin_client import AdminClient, TokenClient
from tempest.tests.compute.base import BaseComputeTest

import json
import fabric.api

#Detailed test design.
# 1. Create tenant tenant1.
# 2. Create tenant tenant2.
# 3. Create network network1, ip range 10.0.2.0/24, vlan 101, project tenant1.
# 4. Create network network2, ip range 10.0.3.0/24, vlan 102, project tenant2.
# 5. Create user user1/password1, tenant tenant1.
# 6. Create user user2/password2, tenant tenant2.
# 7. Grant Member roles to the users.
# 8. Create and upload novarc_userX files.
# 9. Check cirros-0.3.0 image and upload it if not present.
# 10. As user user1: Create new glance image and retrieve its id.
# 11. As user user2: try to delete the image by id.
# 12. Verify that deletion error has occured.
# 13. As user user1: try to delete the image by id.
# 14. Verify that correct image was deleted.
# 15. Clean environment up - delete created tenants and users.

class TestImageAccessPrivacy(BaseComputeTest):
    
    @classmethod
    def setUpClass(cls):
        super(TestImageAccessPrivacy, cls).setUpClass()
        
        cls.config = tempest.config.TempestConfig()
        cls.username = cls.config.identity_admin.username

        cls.password = cls.config.identity_admin.password
        cls.tenant_name = 'openstack'
        cls.admin_client = AdminClient(cls.config, cls.username, cls.password, cls.config.identity.auth_url, cls.tenant_name)
        
        cls.TENANT1_NAME = "tenant1"
        cls.TENANT2_NAME = "tenant2"
        
        cls.USER1_NAME = "user1"
        cls.USER1_PSWD = "password1"
        
        cls.USER2_NAME = "user2"
        cls.USER2_PSWD = "password2"
        
        cls.image_ref = cls.config.compute.image_ref
        cls.flavor_ref = cls.config.compute.flavor_ref

    def tearDown(self):
        try:
            self.admin_client.delete_user(self.user1_id)
            self.admin_client.delete_user(self.user2_id)
            self.admin_client.delete_tenant(self.tenant1_id)
            self.admin_client.delete_tenant(self.tenant2_id)
        except:
            pass
    
    #@attr(type='positive')
    def test_case1(self):
        #1. Create two tenants.
        resp, body = self.admin_client.create_tenant(self.TENANT1_NAME)
        self.tenant1_id = body["id"]
        resp, body = self.admin_client.create_tenant(self.TENANT2_NAME)
        self.tenant2_id = body["id"]
        
        #2. Create and enable two users (one per each tenant).
        resp, body = self.admin_client.create_user(self.USER1_NAME, self.USER1_PSWD, self.tenant1_id, "example1@example.com")
        self.user1_id = body["id"]
        resp, body = self.admin_client.enable_disable_user(self.user1_id, True)
        resp, body = self.admin_client.create_user(self.USER2_NAME, self.USER2_PSWD, self.tenant2_id, "example2@example.com")
        self.user2_id = body["id"]
        resp, body = self.admin_client.enable_disable_user(self.user2_id, True)
        
        #3. Get ID of Member role from keystone.
        resp, body = self.admin_client.list_roles()
        for role in body:
            if role["name"] == "Member":
                self.member_role_id = role["id"]
        
        #4. Assign tenant-member role for each user in their tenants.
        resp, body = self.admin_client.assign_user_role(self.user1_id, self.member_role_id, self.tenant1_id)
        resp, body = self.admin_client.assign_user_role(self.user2_id, self.member_role_id, self.tenant2_id)
        
        #prepare fabric.
        
        fabric.api.env["host_string"] = "%s@%s:%s"%(self.config.identity_admin.host_user, self.config.identity.host, self.config.identity_admin.host_ssh_port)
        fabric.api.env["password"] = self.config.identity_admin.host_password
                
        #upload latest cirros image to a target machine.
        output = fabric.api.run("ls ~")
        if not "cirros-0.3.0-i386-disk.img" in output:
            fabric.api.run("wget -q https://launchpad.net/cirros/trunk/0.3.0/+download/cirros-0.3.0-i386-disk.img")
        
        f = file("/tmp/novarc_user1", "wt")
        f.writelines(["export OS_USERNAME=%s\n"%self.USER1_NAME, "export OS_PASSWORD=%s\n"%self.USER1_PSWD, \
                      "export OS_TENANT_NAME=%s\n"%self.TENANT1_NAME, "export OS_AUTH_URL=http://127.0.0.1:35357/v2.0/\n"])
        f.close()
        
        f = file("/tmp/novarc_user2", "wt")
        f.writelines(["export OS_USERNAME=%s\n"%self.USER2_NAME, "export OS_PASSWORD=%s\n"%self.USER2_PSWD, \
                      "export OS_TENANT_NAME=%s\n"%self.TENANT2_NAME, "export OS_AUTH_URL=http://127.0.0.1:35357/v2.0/\n"])
        f.close()
        
        output = fabric.api.run("ls /tmp")
        if not ("novarc_user1" in output) and ("novarc_user2" in output):
            fabric.api.put("~/novarc_user*", "/tmp")
        
        output = fabric.api.run('source /tmp/novarc_user1 && glance add name="Cirros_user1_private" disk_format=qcow2 '\
                                'container_format=ovf is_public=False < ~/cirros-0.3.0-i386-disk.img')
        image_id = ""
        image_id = output.split(': ')[-1]
        
        fabric.api.env["warn_only"] = True
        output = fabric.api.run('source /tmp/novarc_user2 && glance -f delete %s'%image_id)
        
        self.assertTrue('No image with ID %s was found'%image_id in output)
        
        output = fabric.api.run('source /tmp/novarc_user1 && glance -f delete %s'%image_id)
        
        self.assertTrue("Deleted image %s"%image_id in output)

if __name__ == "__main__":
    unittest.main()