from checks import AgentCheck
import sys
sys.path.extend(['/nfs/tools/lib/netapp/sdk/lib/python/NetApp'])
from NaServer import *
from distutils.util import strtobool

import ssl

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Legacy Python that doesn't verify HTTPS certificates by default
    pass
else:
    # Handle target environment that doesn't support HTTPS verification
    ssl._create_default_https_context = _create_unverified_https_context

class NetappIntegrationCheck(AgentCheck):
    def __init__(self, name, init_config, agentConfig, instances=[]):
        super(NetappIntegrationCheck, self).__init__(name, init_config, agentConfig, instances)

        self.svms = {}

        for i in instances:
            if 'name' in i is False:
                raise Exception('Must specify a unique name for each instance.')

            if 'host' in i is False:
                raise Exception('Must specify a NetApp cluster head to connect to.')

            if 'username' in i is False:
                raise Exception('Must specify a username for ONTAP.')

            if 'password' in i and 'password_file' in i:
                raise Exception('Must specify either password or password_file, not both.')

            if ('password' in i or 'password_file' in i) is False:
                raise Exception('Must specify a password or password_file for ONTAP.')

            if 'apiVersionMajor' in i is False:
                raise Exception('Must specify an apiVersionMajor.')

            if 'apiVersionMinor' in i is False:
                raise Exception('Must specify an apiVersionMinor.')

            if 'password_file' in i:
                try:
                    with open(i.get('password_file'), 'r') as pf:
                        password = pf.read().strip()
                except Exception as e:
                    self.log.critical("Unable to open password_file %s, error %s" %(i.get('password_file'), repr(e)))
                    return
            else:
                password = i.get('password')

            api_version_major, api_version_minor = i.get('apiVersionMajor'), i.get('apiVersionMinor')

            try:
                api_version_major = int(api_version_major)
            except (TypeError, ValueError):
                raise Exception('Must specify an integer value for apiVersionMajor. Configured value is %s'
                                % repr(api_version_major))

            try:
                api_version_minor = int(api_version_minor)
            except (TypeError, ValueError):
                raise Exception('Must specify an integer value for apiVersionMinor. Configured value is %s'
                                % repr(api_version_minor))

            __svm__ = NaServer(i['host'], i['apiVersionMajor'], i['apiVersionMinor'])
            __svm__.set_style('LOGIN')
            __svm__.set_transport_type('HTTPS')
            __svm__.set_admin_user(i['username'], password)
            __svm__.set_port(int(i.get('port', 443)))
            __svm__.set_timeout(10)

            self.svms[i['name']] = __svm__

    def check(self, instance):
        """
        :param instance:
        :type instance:
        :return:
        :rtype:
        """

        name = instance.get('name', None)
        host = instance.get('host', None)
        tags = instance.get('tags', [])

        tags.append('netapp_host:%s' %(host))

        svm = self.svms[name]


        system_nodes_parent = svm.invoke('system-node-get-iter')

        # Can connect
        status = system_nodes_parent.attr_get('status')

        if status == "failed":
            self.log.critical('Query against NetApp %s failed with %s' %(host, repr(system_nodes_parent.toEncodedString())))
            self.service_check('netapp.can_connect_https', AgentCheck.CRITICAL, tags=tags, message=repr(system_nodes_parent.toEncodedString()))
            return
        else:
            self.service_check('netapp.can_connect_https', AgentCheck.OK, tags=tags)

        nodes = svm.invoke('system-node-get-iter').child_get('attributes-list').children_get()

        # Node health
        for n in nodes:
            node_name = n.child_get_string('node')
            _tags = tags + ['netapp_node:%s' % (node_name)]
            env_failed_fan_count = n.child_get_int('env-failed-fan-count')
            env_failed_power_supply_count = n.child_get_int('env-failed-power-supply-count')
            env_over_temperature_svc = strtobool(n.child_get_string('env-over-temperature'))
            env_is_healthy_svc = strtobool(n.child_get_string('is-node-healthy'))

            self.count('netapp.failed_fan_count', env_failed_fan_count, tags=_tags)
            self.count('netapp.failed_power_supply_counnt', env_failed_power_supply_count, tags=_tags)
            self.service_check('netapp.is_over_temperature', AgentCheck.OK if env_over_temperature_svc == False else AgentCheck.CRITICAL,
                               tags=_tags)
            self.service_check('netapp.is_healthy', AgentCheck.OK if env_is_healthy_svc else AgentCheck.CRITICAL)

        # Volume
        volume_list_iterator = svm.invoke('volume-space-get-iter')

        while True:
            for volume in volume_list_iterator.child_get('attributes-list').children_get():
                inodes = volume.child_get_int('inodes')
                inodes_percent = volume.child_get_int('inodes-percent')
                physical_used = volume.child_get_int('physical-used')
                physical_percent = volume.child_get_int('physical-used-percent')
                total_used = volume.child_get_int('total-used')
                total_used_percent = volume.child_get_int('total-used-percent')
                volume_name = volume.child_get_string('volume')
                svm_name = volume.child_get_string('vserver')

                _tags = tags + ['netapp_volume:%s' %(volume_name), 'netapp_svm:%s' %(svm_name)]

                self.gauge('netapp.inodes', inodes, tags=_tags)
                self.gauge('netapp.inodes_percent_used', inodes_percent, tags=_tags)
                self.gauge('netapp.physical_used', physical_used, tags=_tags)
                self.gauge('netapp.physical_percent', physical_percent, tags=_tags)
                self.gauge('netapp.total_used', total_used, tags=_tags)
                self.gauge('netapp.total_used_percent', total_used_percent, tags=_tags)

            next_tag = volume_list_iterator.child_get_string('next-tag')

            if next_tag is None:
                break

            volume_list_iterator = svm.invoke('volume-space-get-iter', 'tag', next_tag)


if __name__ == "__main__":
    check, instances = NetappCheck.from_yaml('./tests/test_config.yaml')
    for instance in instances:
        print "\nRunning the check against host: %s" % (instance['host'])
        check.check(instance)
        if check.has_events():
            print 'Events: %s' % (check.get_events())
        print 'Metrics: %s' % (check.get_metrics())
        print 'Service Checks: %s' % (check.get_service_checks())