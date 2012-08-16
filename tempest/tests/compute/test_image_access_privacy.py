from tempest.openstack import Manager, AdminManager

from tempest.services.network.json.network_client import NetworkClient
from tempest.services.identity.json.admin_client import AdminClient, TokenClient
from tempest.tests.compute.base import BaseComputeTest


import fabric.api

#Detailed test design.
# 1. Create tenant tenant1.
# 2. Create tenant tenant2.
# 3. Create network network1, ip range 10.0.2.0/24, vlan 101, project tenant1.
# 4. Create network network2, ip range 10.0.3.0/24, vlan 102, project tenant2.
# 5. Create user user1/password1, tenant tenant1.
# 6. Create user user2/password2, tenant tenant2.
# 7. As user user1: clone server image on tenant1 with x-image-meta-is-public = False.
# 8. Get a reference to the cloned image.
# 9. As user user2: try to retrieve the cloned image.
# 10. Verify that error 403 was thrown at this attempt.
# 11. As user user1: delete the cloned image.
# 12. Delete tenants tenant1 and tenant2.

class TestImageAccessSecurity(BaseComputeTest):
    
    @classmethod
    def setUpClass(cls):
        super(cls)
        cls.admin_mgr = AdminManager()
        cls.config = tempest.config.TempestConfig()
        cls.username = cls.config.identity_admin.username

        cls.password = cls.config.identity_admin.password
        cls.tenant_name = cls.config.identity_admin.tenant_name
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
            self.admin_client.delete_tenant(self.tenant2_id)
            self.admin_client.delete_tenant(self.tenant2_id)
        except:
            pass
        
    def testCase1(self):
        #1. Create two tenants.
        resp, body = self.admin_client.create_tenant(self.TENANT1_NAME)
        self.tenant1_id = body["id"]
        resp, body = self.admin_client.create_tenant(self.TENANT2_NAME)
        self.tenant2_id = body["id"]
        
        #2. Create two users (one per each tenant).
        resp, body = self.admin_client.create_user(self.USER1_NAME, self.USER1_PSWD, self.tenant1_id, "example1@example.com")
        self.user1_id = body["id"]
        resp, body = self.admin_client.create_user(self.USER2_NAME, self.USER2_PSWD, self.tenant2_id, "example2@example.com")
        self.user2_id = body["id"]
        
        #3. Get ID of Member role from keystone.
        resp, body = self.admin_client.list_roles()
        self.admin_role_id = body["Member"]["id"]
        
        #4. Assign tenant-admin role for each user in their tenants.
        resp, body = self.admin_client.assign_user_role(self.user1_id, self.admin_role_id, self.tenant1_id)
        resp, body = self.admin_client.assign_user_role(self.user2_id, self.admin_role_id, self.tenant2_id)
        
        #prepare fabric.
        fabric.api.env["host_string"] = "root@192.168.123.4"
        fabric.api.env["password"] = "ZofXB3AP"
        
        self.vm_ip = "192.168.122.3"
        self.vm_pass = "password"
        
        fabric.api.run("socat TCP4-LISTEN:2222 TCP4:192.168.123.4:22 &")
        fabric.api.env["host_string"] = "root@192.168.123.4:2222"
        fabric.api.env["password"] = self.vm_pass
        
        
        #upload latest cirros image to a target machine.
        fabric.api.run("wget -q https://launchpad.net/cirros/trunk/0.3.0/+download/cirros-0.3.0-i386-disk.img /tmp")
        
        f = file("/tmp/novarc_user1", "wt")
        f.writelines(["export OS_USERNAME=%s"%self.USER1_NAME, "export OS_PASSWORD=%s"%self.USER1_PSWD, \
                      "export OS_TENANT_NAME=%s"%self.TENANT1_NAME, "export OS_AUTH_URL=http://127.0.0.1:35357/v2.0/"])
        f.close()
        
        f = file("/tmp/novarc_user2", "wt")
        f.writelines(["export OS_USERNAME=%s"%self.USER2_NAME, "export OS_PASSWORD=%s"%self.USER2_PSWD, \
                      "export OS_TENANT_NAME=%s"%self.TENANT2_NAME, "export OS_AUTH_URL=http://127.0.0.1:35357/v2.0/"])
        f.close()
        
        fabric.api.put("/tmp/novarc_user*", "/tmp")
        
        output = fabric.api.run('source /tmp/novarc_user1 && glance add name="Cirros_user1_private" disk_format=qcow2 '\
                                'container_format=ovf is_public=False < /tmp/cirros-0.3.0-i386-disk.img')
        image_id = ""
        image_id = output[-1].split(': ')[-1]
        
        output = fabric.api.run('source /tmp/novarc_user2 && glance -f delete %s'%image_id)
        
        self.assertTrue(output[-1] == 'Not deleting image %s'%image_id)
        
        output = fabric.api.run('source /tmp/novarc_user2 && glance -f delete %s'%image_id)
        
        self.assertTrue(output[-1] == "Deleted image %s"%image_id)
        
        self.admin_client.delete_user(self.user1_id)
        self.admin_client.delete_user(self.user2_id)
        self.admin_client.delete_tenant(self.tenant2_id)
        self.admin_client.delete_tenant(self.tenant2_id)