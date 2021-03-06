# pylint: skip-file
# flake8: noqa


class PolicyUserException(Exception):
    ''' PolicyUser exception'''
    pass


class PolicyUserConfig(OpenShiftCLIConfig):
    ''' PolicyUserConfig is a DTO for user related policy.  '''
    def __init__(self, namespace, kubeconfig, policy_options):
        super(PolicyUserConfig, self).__init__(policy_options['name']['value'],
                                               namespace, kubeconfig, policy_options)
        self.kind = self.get_kind()
        self.namespace = namespace

    def get_kind(self):
        ''' return the kind we are working with '''
        if self.config_options['resource_kind']['value'] == 'role':
            return 'rolebinding'
        elif self.config_options['resource_kind']['value'] == 'cluster-role':
            return 'clusterrolebinding'
        elif self.config_options['resource_kind']['value'] == 'scc':
            return 'scc'

        return None


# pylint: disable=too-many-return-statements
class PolicyUser(OpenShiftCLI):
    ''' Class to handle attaching policies to users '''

    def __init__(self,
                 policy_config,
                 verbose=False):
        ''' Constructor for PolicyUser '''
        super(PolicyUser, self).__init__(policy_config.namespace, policy_config.kubeconfig, verbose)
        self.config = policy_config
        self.verbose = verbose
        self._rolebinding = None
        self._scc = None
        self._cluster_policy_bindings = None
        self._policy_bindings = None

    @property
    def policybindings(self):
        if self._policy_bindings is None:
            results = self._get('clusterpolicybindings', None)
            if results['returncode'] != 0:
                raise OpenShiftCLIError('Could not retrieve policybindings')
            self._policy_bindings = results['results'][0]['items'][0]

        return self._policy_bindings

    @property
    def clusterpolicybindings(self):
        if self._cluster_policy_bindings is None:
            results = self._get('clusterpolicybindings', None)
            if results['returncode'] != 0:
                raise OpenShiftCLIError('Could not retrieve clusterpolicybindings')
            self._cluster_policy_bindings = results['results'][0]['items'][0]

        return self._cluster_policy_bindings

    @property
    def role_binding(self):
        ''' role_binding property '''
        return self._rolebinding

    @role_binding.setter
    def role_binding(self, binding):
        ''' setter for role_binding property '''
        self._rolebinding = binding

    @property
    def security_context_constraint(self):
        ''' security_context_constraint property '''
        return self._scc

    @security_context_constraint.setter
    def security_context_constraint(self, scc):
        ''' setter for security_context_constraint property '''
        self._scc = scc

    def get(self):
        '''fetch the desired kind

           This is only used for scc objects.
           The {cluster}rolebindings happen in exists.
        '''
        resource_name = self.config.config_options['name']['value']
        if resource_name == 'cluster-reader':
            resource_name += 's'

        return self._get(self.config.kind, resource_name)

    def exists_role_binding(self):
        ''' return whether role_binding exists '''
        bindings = None
        if self.config.config_options['resource_kind']['value'] == 'cluster-role':
            bindings = self.clusterpolicybindings
        else:
            bindings = self.policybindings

        if bindings is None:
            return False

        for binding in bindings['roleBindings']:
            _rb = binding['roleBinding']
            if _rb['roleRef']['name'] == self.config.config_options['name']['value'] and \
                    _rb['userNames'] is not None and \
                    self.config.config_options['user']['value'] in _rb['userNames']:
                self.role_binding = binding
                return True

        return False

    def exists_scc(self):
        ''' return whether scc exists '''
        results = self.get()
        if results['returncode'] == 0:
            self.security_context_constraint = SecurityContextConstraints(results['results'][0])

            if self.security_context_constraint.find_user(self.config.config_options['user']['value']) != None:
                return True

            return False

        return results

    def exists(self):
        '''does the object exist?'''
        if self.config.config_options['resource_kind']['value'] == 'cluster-role':
            return self.exists_role_binding()

        elif self.config.config_options['resource_kind']['value'] == 'role':
            return self.exists_role_binding()

        elif self.config.config_options['resource_kind']['value'] == 'scc':
            return self.exists_scc()

        return False

    def perform(self):
        '''perform action on resource'''
        cmd = ['policy',
               self.config.config_options['action']['value'],
               self.config.config_options['name']['value'],
               self.config.config_options['user']['value']]

        return self.openshift_cmd(cmd, oadm=True)

    @staticmethod
    def run_ansible(params, check_mode):
        '''run the idempotent ansible code'''

        state = params['state']

        action = None
        if state == 'present':
            action = 'add-' + params['resource_kind'] + '-to-user'
        else:
            action = 'remove-' + params['resource_kind'] + '-from-user'

        nconfig = PolicyUserConfig(params['namespace'],
                                   params['kubeconfig'],
                                   {'action': {'value': action, 'include': False},
                                    'user': {'value': params['user'], 'include': False},
                                    'resource_kind': {'value': params['resource_kind'], 'include': False},
                                    'name': {'value': params['resource_name'], 'include': False},
                                   })

        policyuser = PolicyUser(nconfig, params['debug'])

        # Run the oc adm policy user related command

        ########
        # Delete
        ########
        if state == 'absent':
            if not policyuser.exists():
                return {'changed': False, 'state': 'absent'}

            if check_mode:
                return {'changed': False, 'msg': 'CHECK_MODE: would have performed a delete.'}

            api_rval = policyuser.perform()

            if api_rval['returncode'] != 0:
                return {'msg': api_rval}

            return {'changed': True, 'results' : api_rval, state:'absent'}

        if state == 'present':
            ########
            # Create
            ########
            results = policyuser.exists()
            if isinstance(results, dict) and 'returncode' in results and results['returncode'] != 0:
                return {'msg': results}

            if not results:

                if check_mode:
                    return {'changed': False, 'msg': 'CHECK_MODE: would have performed a create.'}

                api_rval = policyuser.perform()

                if api_rval['returncode'] != 0:
                    return {'msg': api_rval}

                return {'changed': True, 'results': api_rval, state: 'present'}

            return {'changed': False, state: 'present'}

        return {'failed': True, 'changed': False, 'results': 'Unknown state passed. %s' % state, state: 'unknown'}
